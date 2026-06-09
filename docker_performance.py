import time
import threading
import csv
import psutil
import docker
from datetime import datetime

# Initialize Docker client safely
try:
    client = docker.from_env()
except Exception as e:
    print(f"Error connecting to Docker: {e}")
    exit(1)

def calculate_container_raw_cpu(stats):
    """
    Calculates the raw core-based CPU usage (16 cores, 0-1600%).
    Matches exactly how Docker Desktop represents individual containers.
    """
    try:
        cpu_stats = stats['cpu_stats']
        precpu_stats = stats['precpu_stats']
        
        cpu_delta = cpu_stats['cpu_usage']['total_usage'] - precpu_stats['cpu_usage']['total_usage']
        system_delta = cpu_stats['system_cpu_usage'] - precpu_stats.get('system_cpu_usage', 0)
        
        # Get the number of system cores (e.g., 16)
        num_cores = cpu_stats.get('online_cpus', len(cpu_stats['cpu_usage'].get('percpu_usage', [1])))
        
        if system_delta > 0 and cpu_delta > 0:
            # Multiplying by num_cores scales it up to your raw max (e.g., 1600%)
            return (cpu_delta / system_delta) * num_cores * 100.0
    except KeyError:
        pass
    return 0.0

def get_all_pipeline_stats(project_name, target_containers):
    """
    Fetches raw stats across the entire stack in ONE API call sweep.
    Returns cumulative raw core metrics (0-1600%).
    """
    metrics = {
        "stack_cpu": 0.0, "stack_mem": 0.0,
        "container_breakdown": {name: {"cpu": 0.0, "mem": 0.0} for name in target_containers}
    }
    
    try:
        containers = client.containers.list()
        for container in containers:
            labels = container.attrs.get('Config', {}).get('Labels', {})
            container_project = labels.get('com.docker.compose.project')
            
            if container_project == project_name:
                stats = container.stats(stream=False)
                
                # Fetch raw core CPU usage (e.g., 400.0% means 4 full cores)
                container_cpu = calculate_container_raw_cpu(stats)
                
                # Fetch memory footprint
                mem_usage = stats['memory_stats'].get('usage', 0)
                container_mem_mb = mem_usage / (1024 * 1024)
                
                # Accumulate the totals for the entire stack
                metrics["stack_cpu"] += container_cpu
                metrics["stack_mem"] += container_mem_mb
                
                for target_name in target_containers:
                    if target_name in container.name:
                        metrics["container_breakdown"][target_name]["cpu"] = container_cpu
                        metrics["container_breakdown"][target_name]["mem"] = container_mem_mb

    except Exception as e:
        print(f"Error fetching engine telemetry: {e}")
        
    return metrics

def monitor_and_save(stop_event, filename="performance_log.csv", interval=1):
    stack_name = "continuous-software-traceability-thesis"
    focus_targets = ["ollama", "neo4j_knowledge_graph"]
    
    # Dynamically find your machine's total logical core count (16)
    total_cores = psutil.cpu_count()
    
    with open(filename, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([
            "Timestamp", 
            "Total_Host_CPU_%", "Total_Host_Mem_MB", 
            "Stack_Total_CPU_%", "Stack_Total_Mem_MB",
            "Ollama_CPU_%", "Ollama_Mem_MB", 
            "Neo4j_CPU_%", "Neo4j_Mem_MB"
        ])
        
        print(f"Logging raw performance data directly to {filename} (Max scale: {total_cores * 100}%)...")
        _ = psutil.cpu_percent(interval=None) # Initialize baseline
        
        while not stop_event.is_set():
            timestamp = datetime.now().isoformat()
            
            # 1. Fetch host CPU (0-100%) and instantly scale it to match the 16-core max (0-1600%)
            host_percent_normalized = psutil.cpu_percent(interval=0.1)
            total_host_raw_cpu = host_percent_normalized * total_cores
            
            total_host_mem_mb = psutil.virtual_memory().used / (1024 * 1024)
            
            # 2. Fetch raw stack components
            stack_data = get_all_pipeline_stats(stack_name, focus_targets)
            
            o_stats = stack_data["container_breakdown"]["ollama"]
            n_stats = stack_data["container_breakdown"]["neo4j_knowledge_graph"]
            
            # 3. Log everything directly to the CSV
            writer.writerow([
                timestamp, 
                round(total_host_raw_cpu, 1), round(total_host_mem_mb, 1),
                round(stack_data["stack_cpu"], 1), round(stack_data["stack_mem"], 1), 
                round(o_stats["cpu"], 1), round(o_stats["mem"], 1),
                round(n_stats["cpu"], 1), round(n_stats["mem"], 1)
            ])
            
            file.flush() 
            time.sleep(interval)

# --- APPLICATION WORKLOAD EXECUTION ---
if __name__ == "__main__":
    stop_monitoring = threading.Event()
    
    # Start background CSV logger thread
    monitor_thread = threading.Thread(
        target=monitor_and_save, 
        args=(stop_monitoring, "run_metrics.csv", 1) # Capture every 1 second
    )
    monitor_thread.daemon = True
    monitor_thread.start()

    try:
        print("\n>>> STARTING WORKLOAD <<<\n")
        while True:
            ans = input()
            if ans == "stop":
                break
        print("\n>>> WORKLOAD COMPLETE <<<\n")
        
    finally:
        stop_monitoring.set()
        monitor_thread.join()
        print("Data successfully logged and saved.")
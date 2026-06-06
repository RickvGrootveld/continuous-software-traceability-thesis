import time
import threading
import csv
import psutil
import docker

# Initialize Docker client safely
try:
    client = docker.from_env()
except Exception as e:
    print(f"Error connecting to Docker: {e}")
    exit(1)

def get_container_stats(container_name):
    """Fetches real-time CPU and Memory usage for a specific container."""
    try:
        container = client.containers.get(container_name)
        stats = container.stats(stream=False)
        
        # Memory Calculation
        mem_usage = stats['memory_stats']['usage']
        mem_mb = mem_usage / (1024 * 1024)
        
        # CPU Calculation
        cpu_stats = stats['cpu_stats']
        precpu_stats = stats['precpu_stats']
        cpu_delta = cpu_stats['cpu_usage']['total_usage'] - precpu_stats['cpu_usage']['total_usage']
        system_delta = cpu_stats['system_cpu_usage'] - precpu_stats.get('system_cpu_usage', 0)
        num_cores = cpu_stats.get('online_cpus', len(cpu_stats['cpu_usage'].get('percpu_usage', [1])))
        
        cpu_percent = (cpu_delta / system_delta) * num_cores * 100.0 if system_delta > 0 and cpu_delta > 0 else 0.0
        return cpu_percent, mem_mb
    except Exception:
        return None, None

def monitor_and_save(stop_event, filename="performance_log.csv", interval=2):
    """Background monitoring loop that streams data straight to a CSV file."""
    
    # Open the file and write the header column layout
    with open(filename, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([
            "Timestamp", 
            "Host_CPU_%", "Host_Mem_MB", 
            "Ollama_CPU_%", "Ollama_Mem_MB", 
            "Neo4j_CPU_%", "Neo4j_Mem_MB"
        ])
        
        print(f"Logging performance data directly to {filename}...")
        
        while not stop_event.is_set():
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            
            # 1. Fetch Host Metrics
            host_cpu = psutil.cpu_percent(interval=None)
            host_mem_mb = psutil.virtual_memory().used / (1024 * 1024)
            
            # 2. Fetch Container Metrics
            ollama_cpu, ollama_mem = get_container_stats("ollama")
            neo4j_cpu, neo4j_mem = get_container_stats("neo4j_knowledge_graph")
            
            # Fallback values if container is offline
            o_cpu, o_mem = (ollama_cpu, ollama_mem) if ollama_cpu is not None else (0.0, 0.0)
            n_cpu, n_mem = (neo4j_cpu, neo4j_mem) if neo4j_cpu is not None else (0.0, 0.0)
            
            # 3. Write row to CSV file instantly
            writer.writerow([
                timestamp, 
                round(host_cpu, 1), round(host_mem_mb, 1),
                round(o_cpu, 1), round(o_mem, 1),
                round(n_cpu, 1), round(n_mem, 1)
            ])
            
            # Flush internal buffer out to the storage drive instantly
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
        # -----------------------------------------------------------
        # YOUR ACTUAL PROGRAM CODE GOES HERE
        time.sleep(10) # Simulating program execution
        # -----------------------------------------------------------
        print("\n>>> WORKLOAD COMPLETE <<<\n")
        
    finally:
        stop_monitoring.set()
        monitor_thread.join()
        print("Data successfully logged and saved.")
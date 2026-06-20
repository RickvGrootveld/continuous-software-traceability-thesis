"""
LLM Graph Enrichment Service

This service:
1. Continuously polls Neo4j
2. Creates sliding windows of incoming nodes
3. Retrieves hybrid graph context
4. Calls the LLM for edge enrichment
5. Inserts inferred edges back into Neo4j
6. Signals the knowledge graph service via Redis pub/sub once enrichment
   and insertion are complete, so it can safely consume the next event
"""

import time
import threading
from threading import Lock
import csv
import os
import json
import logging
from datetime import datetime

import redis

from context_retriever import ContextRetriever
from llm import GPTClient, QwenClient
from shared_utils.neo4j import Neo4jClient


# Ensure the logs directory exists inside the container
os.makedirs("/app/logs", exist_ok=True)

# Configure logging to write to both the file and console if needed,
# or just the file to completely eliminate container memory usage.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("/app/logs/enrichment.log"),
        # logging.StreamHandler() # Uncomment this if you ever want standard prints back
    ]
)

# ============================================================
# SLIDING WINDOW
# ============================================================

# window_buffer = []
window_buffer_v2 = {
    "nodes": [],
    "edges": []
}
window_lock = Lock()
window_start_time = None
correct_inserted_edges = 0
metrics_window = {
    "time_window": [],
    "graph_nodes": [],
    "graph_edges": [],
    "db_hits": [],
}

WINDOW_SECONDS = 15 #1496
CSV_FILE = "/app/enrichment_service/log_run_results.csv"

REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
READY_CHANNEL = "enrichment_ready"

class EnrichmentService:

    def __init__(self):
        logging.info("Starting neo4j client...")
        self.neo4j = Neo4jClient()
        logging.info("starting context retriever...")
        self.retriever = ContextRetriever(
            self.neo4j,
        )
        logging.info("starting LLM client...")
        #self.llm = GPTClient()
        self.llm = QwenClient()

        logging.info(f"Connecting to Redis at {REDIS_HOST}:{REDIS_PORT}...")
        self.redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)

    def add_to_window(self, nodes, edges):
        global window_start_time

        with window_lock:
            for node in nodes:
                window_buffer_v2["nodes"].append(node)
            for edge in edges:
                window_buffer_v2["edges"].append(edge)
                
            if (len(window_buffer_v2["nodes"]) > 0 and window_start_time is None):
                window_start_time = time.time()
                #print(f"Started {WINDOW_SECONDS}s window")

    def poll_neo4j(self):
        while True:
            try:
                recent_nodes, recent_edges, total_nodes, total_edges, total_db_hits, time_window  = self.neo4j.get_recent_nodes()

                if len(recent_nodes) > 0:
                    logging.info("adding to window")
                    metrics_window["time_window"].append(time_window)
                    metrics_window["graph_nodes"].append(total_nodes)
                    metrics_window["graph_edges"].append(total_edges)
                    metrics_window["db_hits"].append(total_db_hits)
                    self.add_to_window(recent_nodes, recent_edges)

            except Exception as e:
                logging.info("Neo4j polling error:", e)
            time.sleep(1)
    
    def log_experiment_run(self, columns):
        # 3. Open the file in append mode ('a') with newline='' to prevent blank lines on Windows
        with open(CSV_FILE, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(columns)

    def process_windows(self):
        global window_start_time
        while True:
            time.sleep(1)
            #print(f"Current window buffer loop: {window_buffer_v2}")
            #print("looping to check window...")
            with window_lock:
                if window_start_time is None:
                    continue
                elapsed = time.time() - window_start_time
                if elapsed < WINDOW_SECONDS:
                    continue
                current_window = {
                    "nodes": list(window_buffer_v2["nodes"]),
                    "edges": list(window_buffer_v2["edges"])
                }
                time_window = 0
                time_window += (sum(metrics_window["time_window"]) / len(metrics_window["time_window"]))
                graph_nodes_window = 0
                graph_nodes_window += (sum(metrics_window["graph_nodes"]) / len(metrics_window["graph_nodes"]))
                graph_edges_window = 0
                graph_edges_window += (sum(metrics_window["graph_edges"]) / len(metrics_window["graph_edges"]))
                db_hits_window = 0
                db_hits_window += (sum(metrics_window["db_hits"]) / len(metrics_window["db_hits"]))
                metrics_window["time_window"] = []
                metrics_window["graph_nodes"] = []
                metrics_window["graph_edges"] = []
                metrics_window["db_hits"] = []

                window_buffer_v2["nodes"].clear()
                window_buffer_v2["edges"].clear()
                window_start_time = None

            try:
                # Retrieve nodes from the graph to get context for the LLM
                #context_nodes, context_edges = self.retriever.retrieve_context(current_window)
                logging.info("start retrieving ...")
                context, metrics_context = self.retriever.retrieve_context(current_window)

                # Enrich the graph with the LLM
                try:
                    inferred_edges, llm_duration, generated_edges, correct_edges = self.llm.call_llm(context)

                except Exception as e:
                    logging.info("LLM error:", e)
                    continue

                logging.info("LLM enrichment done.")

                try:
                    metrics_insertion = self.neo4j.insert_llm_edges(inferred_edges["new_edges"])
                except Exception as e:
                    logging.info("Neo4j insertion error:", e)

                metrics = [
                    datetime.now().isoformat(),
                    # LLM
                    llm_duration,
                    generated_edges,
                    correct_edges,
                    # Window
                    time_window,
                    graph_nodes_window,
                    graph_edges_window,
                    db_hits_window,
                    # neighbours
                    metrics_context["db_retrieval_time_ms_neighbour"],
                    metrics_context["total_nodes_neighbour"],
                    metrics_context["total_edges_neighbour"],
                    metrics_context["total_db_hits_neighbour"],
                    # vector
                    metrics_context["db_retrieval_time_ms_vector"],
                    metrics_context["graph_nodes_vector"],
                    metrics_context["graph_edges_vector"],
                    metrics_context["total_db_hits_vector"],
                    # enrichment insertion
                    metrics_insertion["db_insert_time_ms"],
                    metrics_insertion["graph_nodes"],
                    metrics_insertion["graph_edges"],
                ]

                # Write results to database            
                self.log_experiment_run(metrics)

            finally:
                # Always signal readiness, even if enrichment/insertion failed
                # above — otherwise a single bad window permanently deadlocks
                # the knowledge graph service, which is waiting on this signal
                # before it consumes the next Kafka event.
                self.redis_client.publish(
                    READY_CHANNEL,
                    json.dumps({"status": "ready", "timestamp": datetime.now().isoformat()})
                )
                logging.info("Published 'ready' signal to knowledge graph service.")

            # let the LLM rest for a little to prevent CPU overload
            #time.sleep(45)

    def run(self):
        logging.info("Starting LLM Enrichment Service")

        polling_thread = threading.Thread(
            target=self.poll_neo4j,
            daemon=True
        )

        with self.neo4j.driver.session() as session:
            pass 

        polling_thread.start()

        processing_thread = threading.Thread(
            target=self.process_windows,
            daemon=True
        )
        
        processing_thread.start()

        logging.info("Service running...")

        polling_thread.join()
        processing_thread.join()

print("Starting service...")
if __name__ == "__main__":
    service = EnrichmentService()
    service.run()
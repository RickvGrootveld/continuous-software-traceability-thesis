"""
LLM Graph Enrichment Service

This service:
1. Continuously polls Neo4j
2. Groups incoming nodes/edges into 15s collection windows
3. Once a window closes, it is queued for enrichment
4. A separate worker processes queued windows sequentially:
   retrieves hybrid graph context, calls the LLM for edge enrichment,
   and inserts inferred edges back into Neo4j
5. The next queued window starts enriching as soon as the previous
   enrichment call finishes (collection keeps running independently)

Architecture:

Neo4j <- LLM Enrichment Service
"""

import time
import threading
import queue
from threading import Lock
import csv
import os
import logging
from datetime import datetime

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
        logging.FileHandler("/app/logs/enrichment.log", encoding='utf-8')
        # logging.StreamHandler() # Uncomment this if you ever want standard prints back
    ]
)

# ============================================================
# COLLECTION WINDOW
# ============================================================

window_buffer_v2 = {
    "nodes": [],
    "edges": []
}
window_lock = Lock()
window_start_time = None
metrics_window = {
    "time_window": [],
    "graph_nodes": [],
    "graph_edges": [],
    "db_hits": [],
}

WINDOW_SECONDS = 15
CSV_FILE = "/app/enrichment_service/log_run_results.csv"


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

        self.batch_queue = queue.Queue()

    def add_to_window(self, nodes, edges):
        global window_start_time

        with window_lock:
            for node in nodes:
                window_buffer_v2["nodes"].append(node)
            for edge in edges:
                window_buffer_v2["edges"].append(edge)

            if (len(window_buffer_v2["nodes"]) > 0 and window_start_time is None):
                window_start_time = time.time()
                logging.info(f"Started {WINDOW_SECONDS}s collection window")

    def poll_neo4j(self):
        while True:
            try:
                recent_nodes, recent_edges, total_nodes, total_edges, total_db_hits, time_window = self.neo4j.get_recent_nodes()

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

    def close_windows(self):
        """Independently watches the collection window and, once it expires,
        snapshots it and pushes it onto the processing queue. Collection of
        the next window starts immediately after, regardless of whether the
        queued batch has been processed yet."""
        global window_start_time
        while True:
            time.sleep(1)
            with window_lock:
                if window_start_time is None:
                    continue
                elapsed = time.time() - window_start_time
                if elapsed < WINDOW_SECONDS:
                    continue

                batch = {
                    "nodes": list(window_buffer_v2["nodes"]),
                    "edges": list(window_buffer_v2["edges"]),
                    "time_window": sum(metrics_window["time_window"]) / len(metrics_window["time_window"]),
                    "graph_nodes": sum(metrics_window["graph_nodes"]) / len(metrics_window["graph_nodes"]),
                    "graph_edges": sum(metrics_window["graph_edges"]) / len(metrics_window["graph_edges"]),
                    "db_hits": sum(metrics_window["db_hits"]) / len(metrics_window["db_hits"]),
                }

                metrics_window["time_window"] = []
                metrics_window["graph_nodes"] = []
                metrics_window["graph_edges"] = []
                metrics_window["db_hits"] = []

                window_buffer_v2["nodes"].clear()
                window_buffer_v2["edges"].clear()
                window_start_time = None

            logging.info(f"Window closed with {len(batch['nodes'])} nodes, queuing for enrichment")
            print(f"batch nodes: {batch}")
            self.batch_queue.put(batch)

    def log_experiment_run(self, columns):
        with open(CSV_FILE, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(columns)

    def process_batch(self, batch):
        current_window = {
            "nodes": batch["nodes"],
            "edges": batch["edges"]
        }

        logging.info("start retrieving ...")
        context, metrics_context = self.retriever.retrieve_context(current_window)

        try:
            inferred_edges, llm_duration, generated_edges, correct_edges = self.llm.call_llm(context)
        except Exception as e:
            logging.info("LLM error:", e)
            return

        logging.info("LLM enrichment done.")

        try:
            metrics_insertion = self.neo4j.insert_llm_edges(inferred_edges["new_edges"])
        except Exception as e:
            logging.info("Neo4j insertion error:", e)
            return

        metrics = [
            datetime.now().isoformat(),
            # LLM
            llm_duration,
            generated_edges,
            correct_edges,
            # Window
            batch["time_window"],
            batch["graph_nodes"],
            batch["graph_edges"],
            batch["db_hits"],
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

        self.log_experiment_run(metrics)

    def process_queue(self):
        """Pulls finished windows off the queue strictly one at a time.
        The next enrichment call starts as soon as the previous one
        finishes, independent of how collection is progressing."""
        while True:
            batch = self.batch_queue.get()  # blocks until a closed window is available
            try:
                self.process_batch(batch)
            finally:
                self.batch_queue.task_done()

    def run(self):
        logging.info("Starting LLM Enrichment Service")

        polling_thread = threading.Thread(
            target=self.poll_neo4j,
            daemon=True
        )

        window_closer_thread = threading.Thread(
            target=self.close_windows,
            daemon=True
        )

        with self.neo4j.driver.session() as session:
            pass

        polling_thread.start()
        window_closer_thread.start()

        processing_thread = threading.Thread(
            target=self.process_queue,
            daemon=True
        )

        processing_thread.start()

        logging.info("Service running...")

        polling_thread.join()
        window_closer_thread.join()
        processing_thread.join()

print("Starting service...")
if __name__ == "__main__":
    service = EnrichmentService()
    service.run()
"""
LLM Graph Enrichment Service

This service:
1. Continuously polls Neo4j
2. Creates sliding windows of incoming nodes
3. Retrieves hybrid graph context
4. Calls the LLM for edge enrichment
5. Inserts inferred edges back into Neo4j

Architecture:

Neo4j <- LLM Enrichment Service
"""

import copy
import time
import threading
from threading import Lock

from context_retriever import ContextRetriever
from llm import GPTClient, QwenClient
from shared_utils.neo4j import Neo4jClient

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

WINDOW_SECONDS = 15


class EnrichmentService:

    def __init__(self):
        print("Starting neo4j client...")
        self.neo4j = Neo4jClient()
        print("starting context retriever...")
        self.retriever = ContextRetriever(
            self.neo4j,
        )
        print("starting LLM client...")
        #self.llm = GPTClient()
        self.llm = QwenClient()

    def add_to_window(self, nodes, edges):
        global window_start_time

        with window_lock:
            for node in nodes:
                window_buffer_v2["nodes"].append(node)
            for edge in edges:
                window_buffer_v2["edges"].append(edge)
                #print(f"Buffered node: {node}")
                
            if (len(window_buffer_v2["nodes"]) > 0 and window_start_time is None):
                window_start_time = time.time()
                print(f"Started {WINDOW_SECONDS}s window")

    def poll_neo4j(self):
        while True:
            try:
                recent_nodes, recent_edges = self.neo4j.get_recent_nodes()
                #print(f"Recent nodes: {recent_nodes}")
                if len(recent_nodes) > 0:
                    print("adding to window")
                    self.add_to_window(recent_nodes, recent_edges)

            except Exception as e:
                print("Neo4j polling error:", e)
            time.sleep(1)

    def process_windows(self):
        global window_start_time
        while True:
            time.sleep(1)
            #print(f"Current window buffer loop: {window_buffer_v2}")
            print("looping to check window...")
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
                window_buffer_v2["nodes"].clear()
                window_buffer_v2["edges"].clear()
                window_start_time = None

            #print(f"window_buffer_v2: {window_buffer_v2}")
            #print(f"current window: {current_window}")
            # Retrieve nodes from the graph to get context for the LLM
            #context_nodes, context_edges = self.retriever.retrieve_context(current_window)
            print("start retrieving ...")
            context = self.retriever.retrieve_context(current_window)

            #print(f"Retrieved {len(context_nodes)} nodes")

            # Enrich the graph with the LLM
            try:
                inferred_edges = self.llm.call_llm(context)

            except Exception as e:
                print("LLM error:", e)
                continue
            
            print("LLM enrichment done.")

            try:
                self.neo4j.insert_llm_edges(inferred_edges["new_edges"])
            except Exception as e:
                print("Neo4j insertion error:", e)

            # let the LLM rest for a little to prevent CPU overload
            time.sleep(60)

    def run(self):
        print("Starting LLM Enrichment Service")

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

        print("Service running...")

        polling_thread.join()
        processing_thread.join()
print("Starting service...")
if __name__ == "__main__":
    service = EnrichmentService()
    service.run()
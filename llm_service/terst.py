"""
LLM Graph Enrichment Service

This service:
1. Continuously polls Neo4j
2. Creates sliding windows of incoming nodes
3. Retrieves hybrid graph context
4. Calls the LLM for edge enrichment
5. Inserts inferred edges back into Neo4j

Architecture:

Neo4j
  ↑
LLM Enrichment Service
"""

import time
import threading
from threading import Lock

from context_retriever import ContextRetriever
from llm import GPTClient, QwenClient
from ..utils.neo4j import Neo4jClient
from ..utils.vector_similarity import VectorSimilarityRetriever

# ============================================================
# SLIDING WINDOW
# ============================================================

window_buffer = []
window_lock = Lock()
window_start_time = None

WINDOW_SECONDS = 10


class LLMEnrichmentService:

    def __init__(self):
        self.neo4j = Neo4jClient()
        self.vector = VectorSimilarityRetriever()
        self.retriever = ContextRetriever(
            self.neo4j,
            self.vector
        )
        #self.llm = GPTClient()
        self.llm = QwenClient()

    def add_to_window(self, nodes):
        global window_start_time

        with window_lock:
            for node in nodes:
                window_buffer.append(node)
                print(f"Buffered node: {node['id']}")
            if (
                len(window_buffer) > 0 and
                window_start_time is None
            ):
                window_start_time = time.time()
                print(
                    f"Started {WINDOW_SECONDS}s window"
                )

    def poll_neo4j(self):
        while True:
            try:
                recent_nodes = \
                    self.neo4j.get_recent_nodes()
                if len(recent_nodes) > 0:
                    self.add_to_window(recent_nodes)

            except Exception as e:
                print("Neo4j polling error:", e)
            time.sleep(1)

    # ========================================================
    # Process sliding windows
    # ========================================================

    def process_windows(self):
        global window_start_time
        while True:
            time.sleep(1)
            with window_lock:
                if window_start_time is None:
                    continue
                elapsed = \
                    time.time() - window_start_time
                if elapsed < WINDOW_SECONDS:
                    continue
                current_window = window_buffer.copy()
                window_buffer.clear()
                window_start_time = None

            print("\nProcessing window...")
            print(f"Window size: {len(current_window)}")

            # Retrieve nodes from the graph to get context for the LLM
            context_nodes, context_edges = \
                self.retriever.retrieve_context(current_window)

            print(f"Retrieved {len(context_nodes)} nodes")

            # Enrich the graph with the LLM
            try:

                inferred_edges = \
                    self.llm.infer_edges(
                        context_nodes,
                        context_edges
                    )

            except Exception as e:

                print("LLM error:", e)
                continue

            print(f"Inferred {len(inferred_edges)} edges")

            # Get the timestamp to store as property in the edges
            latest_timestamp = \
                current_window[-1]["properties"].get(
                    "created_at",
                    str(time.time())
                )

            # Insert the enriched edges back into the graph
            for edge in inferred_edges:
                llm_edge = {
                    "source": edge["source"],
                    "target": edge["target"],
                    "label": edge["label"],
                    "properties": {
                        "timestamp": latest_timestamp,
                        "system": "LLM",
                        "confidence": edge["confidence"],
                        "explanation": edge["explanation"]
                    }
                }

                try:
                    self.neo4j.insert_llm_edge(llm_edge)
                    print("Inserted edge:", llm_edge)

                except Exception as e:
                    print("Neo4j insertion error:", e)

            # TODO: remove this. don't focus on processing. it is just about the hybrid approach to enrich
            # =================================================
            # Mark processed
            # =================================================

            processed_ids = [
                node["id"]
                for node in current_window
            ]

            self.neo4j.mark_nodes_processed(
                processed_ids
            )

    def run(self):
        print("Starting LLM Enrichment Service")

        polling_thread = threading.Thread(
            target=self.poll_neo4j,
            daemon=True
        )

        polling_thread.start()

        processing_thread = threading.Thread(
            target=self.process_windows,
            daemon=True
        )
        
        processing_thread.start()

        print("Service running...")

        polling_thread.join()
        processing_thread.join()

if __name__ == "__main__":

    service = LLMEnrichmentService()

    service.run()
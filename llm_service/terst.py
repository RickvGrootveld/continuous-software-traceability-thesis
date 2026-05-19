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

import json
from platform import node
import time
import threading
from threading import Lock
from typing import List, Dict

from neo4j import GraphDatabase
from networkx import nodes

# ============================================================
# CONFIGURATION
# ============================================================

# ------------------------
# Neo4j
# ------------------------

NEO4J_URI = "bolt://neo4j:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password"

# ------------------------
# Sliding Window
# ------------------------

WINDOW_SECONDS = 10

# ------------------------
# Retrieval
# ------------------------

K_HOPS = 2
MAX_VECTOR_RESULTS = 20
MAX_CONTEXT_NODES = 50

# ============================================================
# MODEL SELECTION
# Uncomment ONE option
# ============================================================

USE_LOCAL_QWEN = True
# USE_LOCAL_QWEN = False

# USE_GPT = True
USE_GPT = False

# ============================================================
# GPT CONFIG
# ============================================================

OPENAI_API_KEY = "YOUR_OPENAI_API_KEY"
GPT_MODEL = "gpt-5.1"

# ============================================================
# QWEN CONFIG
# ============================================================

QWEN_MODEL_NAME = "Qwen/Qwen3-4B-Instruct-2507"

# ============================================================
# OPTIONAL IMPORTS
# ============================================================

if USE_GPT:
    from openai import OpenAI

if USE_LOCAL_QWEN:
    import torch
    from transformers import (
        AutoTokenizer,
        AutoModelForCausalLM
    )

# ============================================================
# HYBRID RETRIEVER
# ============================================================

class HybridRetriever:

    def __init__(
        self,
        neo4j_client,
        vector_retriever
    ):

        self.neo4j = neo4j_client
        self.vector = vector_retriever

    def retrieve_context(
        self,
        window_nodes: List[Dict],
        window_edges: List[Dict]
    ):

        # ====================================================
        # Get the IDs from each node in the window
        # ====================================================

        seed_ids = [
            node["id"]
            for node in window_nodes
        ]

        # ====================================================
        # k-hop retrieval
        # ====================================================

        neighbour_nodes, neighbour_edges = \
            self.neo4j.get_k_hop_neighbors(
                seed_ids,
                k=K_HOPS
            )

        # ====================================================
        # Vector retrieval
        # ====================================================

        vector_nodes = self.vector.find_similar_nodes(
            nodes=window_nodes + neighbour_nodes,
            top_k=MAX_VECTOR_RESULTS
        )

        # ====================================================
        # Merge
        # ====================================================

        merged = {}

        for node in (
            window_nodes +
            neighbour_nodes +
            vector_nodes
        ):
            # Make sure there are no duplicates in the combined dict
            if node["id"] not in merged:
                merged[node["id"]] = node

        # Convert to list to make it readable for LLMs
        merged_nodes = list(merged.values())

        merged_nodes = merged_nodes[:MAX_CONTEXT_NODES]

        # ====================================================
        # Shorten the context to make it fit for the LLM
        # ====================================================

        nodes = nodes[:MAX_CONTEXT_NODES]
        edges = window_edges + neighbour_edges

        return nodes, edges 

# ============================================================
# LLM CLIENT
# ============================================================

SYSTEM_PROMPT = """
You are an expert software traceability
knowledge graph enrichment system.

Infer meaningful missing relationships.

Allowed labels:
- BLOCKED_BY
- DEPENDS_ON
- RELATED_TO
- CAUSES
- AFFECTS

Return ONLY valid JSON.

Format:

[
    {
        "source": "...",
        "target": "...",
        "label": "...",
        "confidence": 0.92,
        "explanation": "..."
    }
]
"""

class LLMClient:

    def __init__(self):

        print("Loading LLM...")

        # ====================================================
        # GPT
        # ====================================================

        if USE_GPT:

            self.client = OpenAI(
                api_key=OPENAI_API_KEY
            )

            print("GPT-5.1 initialized")

        # ====================================================
        # Qwen
        # ====================================================

        elif USE_LOCAL_QWEN:

            self.tokenizer = \
                AutoTokenizer.from_pretrained(
                    QWEN_MODEL_NAME
                )

            self.model = \
                AutoModelForCausalLM.from_pretrained(
                    QWEN_MODEL_NAME,
                    torch_dtype=torch.float16,
                    device_map="auto"
                )

            print("Qwen initialized")

    def infer_edges(
        self,
        nodes,
        edges
    ):

        # Remove the embeddings from the nodes fed to the LLM to reduce input tokens
        for node in nodes:

            node["properties"].pop(
                "embedding",
                None
            )

        prompt = f"""
        NODES:
        {json.dumps(nodes, indent=2)}

        EDGES:
        {json.dumps(edges, indent=2)}

        Infer missing relationships.
        """

        # ====================================================
        # GPT
        # ====================================================

        if USE_GPT:

            response = self.client.chat.completions.create(
                model=GPT_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.0
            )

            content = response.choices[0].message.content

            return json.loads(content)

        # ====================================================
        # Qwen
        # ====================================================

        elif USE_LOCAL_QWEN:

            messages = [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]

            text = self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True
            )

            model_inputs = self.tokenizer(
                [text],
                return_tensors="pt"
            ).to(self.model.device)

            generated_ids = self.model.generate(
                **model_inputs,
                max_new_tokens=1024,
                temperature=0.1
            )

            output_ids = generated_ids[0][
                len(model_inputs.input_ids[0]):]

            response = self.tokenizer.decode(
                output_ids,
                skip_special_tokens=True
            )

            return json.loads(response)

# ============================================================
# SLIDING WINDOW
# ============================================================

window_buffer = []
window_lock = Lock()
window_start_time = None

# ============================================================
# SERVICE
# ============================================================

class LLMEnrichmentService:

    def __init__(self):

        # ====================================================
        # Create model
        # ====================================================

        self.neo4j = Neo4jClient()

        self.vector = VectorSimilarityRetriever()

        self.retriever = HybridRetriever(
            self.neo4j,
            self.vector
        )

        self.llm = LLMClient()

    # ========================================================
    # Add nodes into sliding window
    # ========================================================

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

    # ========================================================
    # Poll Neo4j continuously
    # ========================================================

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
            print(
                f"Window size: {len(current_window)}"
            )

            # =================================================
            # Hybrid retrieval
            # =================================================

            context_nodes, context_edges = \
                self.retriever.retrieve_context(
                    current_window
                )

            print(
                f"Retrieved {len(context_nodes)} nodes"
            )

            # =================================================
            # LLM enrichment
            # =================================================

            try:

                inferred_edges = \
                    self.llm.infer_edges(
                        context_nodes,
                        context_edges
                    )

            except Exception as e:

                print("LLM error:", e)
                continue

            print(
                f"Inferred {len(inferred_edges)} edges"
            )

            # =================================================
            # Latest timestamp
            # =================================================

            latest_timestamp = \
                current_window[-1]["properties"].get(
                    "created_at",
                    str(time.time())
                )

            # =================================================
            # Insert inferred edges
            # =================================================

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

                    self.neo4j.insert_llm_edge(
                        llm_edge
                    )

                    print(
                        "Inserted edge:",
                        llm_edge
                    )

                except Exception as e:

                    print(
                        "Neo4j insertion error:",
                        e
                    )

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

    # ========================================================
    # Main runtime
    # ========================================================

    def run(self):

        print("Starting LLM Enrichment Service")

        # ====================================================
        # Neo4j polling thread
        # ====================================================

        polling_thread = threading.Thread(
            target=self.poll_neo4j,
            daemon=True
        )

        polling_thread.start()

        # ====================================================
        # Sliding window processing thread
        # ====================================================

        processing_thread = threading.Thread(
            target=self.process_windows,
            daemon=True
        )

        processing_thread.start()

        print("Service running...")

        # ====================================================
        # Prevent the main function from terminating
        # ====================================================

        polling_thread.join()
        processing_thread.join()

# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    service = LLMEnrichmentService()

    service.run()
import ollama
import os
import json
from open_source_llm import (
    OLLAMA_URL,
    ensure_model
)
from llm import SYSTEM_PROMPT

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")

WINDOW_SECONDS = 10
K_HOPS = 2
MAX_VECTOR_RESULTS = 20
MAX_CONTEXT_NODES = 50

USE_LOCAL_QWEN = True
# USE_LOCAL_QWEN = False

# USE_GPT = True
USE_GPT = False

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GPT_MODEL = "gpt-5.1"
QWEN_MODEL_NAME = "Qwen/Qwen3-4B-Instruct-2507"


if USE_GPT:
    from openai import OpenAI

# =====================================
# Local Qwen
# =====================================

if USE_LOCAL_QWEN:
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM


class GPTClient:

    def __init__(self):
        self.client = OpenAI(api_key=OPENAI_API_KEY)

    def infer_edges(self, prompt: str):
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
            temperature=0.1
        )
        content = response.choices[0].message.content
        return json.loads(content)

class QwenClient:

    def __init__(self):
        self.tokenizer = AutoTokenizer.from_pretrained(
            QWEN_MODEL_NAME
        )
        self.model = AutoModelForCausalLM.from_pretrained(
            QWEN_MODEL_NAME,
            torch_dtype=torch.float16,
            device_map="auto"
        )
        
    def infer_edges(self, prompt: str):
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
        output_ids = generated_ids[0][len(model_inputs.input_ids[0]):]
        response = self.tokenizer.decode(
            output_ids,
            skip_special_tokens=True
        )
        return json.loads(response)

class HybridRetriever:

    def __init__(self, neo4j_client, vector_retriever):
        self.neo4j = neo4j_client
        self.vector = vector_retriever

    def retrieve_context(self, window_nodes: List[Dict]):

        # =========================================
        # Step 1 — Seed nodes
        # =========================================

        seed_node_ids = [node["id"] for node in window_nodes]

        # =========================================
        # Step 2 — k-hop retrieval
        # =========================================

        graph_nodes, graph_edges = self.neo4j.get_k_hop_neighbors(
            seed_node_ids,
            k=K_HOPS
        )

        # =========================================
        # Step 3 — Vector similarity retrieval
        # =========================================

        vector_nodes = self.vector.find_similar_nodes(
            nodes=window_nodes + graph_nodes,
            top_k=MAX_VECTOR_RESULTS
        )

        # =========================================
        # Step 4 — Merge nodes
        # =========================================

        merged = {}

        for node in window_nodes + graph_nodes + vector_nodes:
            merged[node["id"]] = node

        merged_nodes = list(merged.values())




    #------------------------------------------------------------------------------------------------------------------------------------------------------------------------

import time
import threading
from threading import Lock

from ..knowledge_graph_service.knowledge_graph import KnowledgeGraph
from graph_data_retrieval import VectorSimilarityRetriever
from llm import build_prompt


# =====================================================
# Sliding Window Buffer
# =====================================================

window_buffer = []
window_lock = Lock()
window_start_time = None


vector_retriever = VectorSimilarityRetriever()

llm = QwenClient()

#llm = GPTClient()


# =====================================================
# Event Ingestion
# =====================================================

def receive_event(node_event):
    global window_start_time

    with window_lock:

        # Push event into sliding window
        window_buffer.append(node_event)
        print(f"Received event: {node_event['id']}")

        # Start timer on first event
        if window_start_time is None:
            window_start_time = time.time()
            print(f"Started {WINDOW_SECONDS}-second sliding window")


# =====================================================
# Sliding Window Processor
# =====================================================

def process_window():
    global window_start_time

    while True:

        time.sleep(1)

        with window_lock:

            if window_start_time is None:
                continue

            elapsed = time.time() - window_start_time

            # Wait until timer expires
            if elapsed < WINDOW_SECONDS:
                continue

            # Freeze current window
            current_window = window_buffer.copy()

            print("\nProcessing sliding window")
            print(f"Window size: {len(current_window)}")

            # Reset window
            window_buffer.clear()
            window_start_time = None

        # Retrieve hybrid context
        print("Retrieving graph context...")

        context_nodes, context_edges = vector_retriever.retrieve_context(
            current_window
        )

        print(f"Retrieved {len(context_nodes)} nodes")
        print(f"Retrieved {len(context_edges)} edges")

        # Build prompt
        prompt = build_prompt(
            context_nodes,
            context_edges
        )

        # Call LLM
        print("Calling LLM for enrichment...")

        try:
            inferred_edges = llm.infer_edges(prompt)

            print(f"LLM inferred {len(inferred_edges)} edges")

        except Exception as e:
            print("LLM ERROR:", e)
            continue

        # Timestamp from latest incoming event
        latest_timestamp = current_window[-1]["properties"].get(
            "committed_date",
            str(time.time())
        )

        # Insert inferred edges into Neo4j
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
                neo4j_client.insert_llm_edge(llm_edge)
                print("Inserted edge:", llm_edge)

            except Exception as e:
                print("Neo4j insertion error:", e)


# =====================================================
# Event Engine Placeholder
# =====================================================

def wait_for_event():
    """
    Replace this function with your actual event engine.

    Examples:
    - Kafka consumer
    - RabbitMQ consumer
    - Redis streams
    - REST API
    - WebSocket stream
    """

    time.sleep(2)

    simulated_events = [
        {
            "type": "Commit",
            "id": "Commit:abc123",
            "properties": {
                "message": "Fix payment retry bug",
                "committed_date": "2026-05-15T10:00:00"
            }
        },
        {
            "type": "Bug",
            "id": "Bug:991",
            "properties": {
                "title": "Authorization token timeout",
                "committed_date": "2026-05-15T10:00:05"
            }
        },
        {
            "type": "Incident",
            "id": "Incident:22",
            "properties": {
                "title": "Checkout retries failing",
                "committed_date": "2026-05-15T10:00:07"
            }
        }
    ]

    if not hasattr(wait_for_event, "counter"):
        wait_for_event.counter = 0

    event = simulated_events[
        wait_for_event.counter % len(simulated_events)
    ]

    wait_for_event.counter += 1

    return event

#------------------------------------------------------------------------------------------------------------------------------------------------------
if __name__ == "__main__":
    print("Starting LLM Graph Enrichment Engine")

    # Start background sliding window processor
    processing_thread = threading.Thread(
        target=process_window,
        daemon=True
    )

    processing_thread.start()

    print(f"Sliding window active ({WINDOW_SECONDS} seconds)")
    print("Waiting for incoming events...")

    # Continuous event loop
    while True:

        new_nodes = neo4j.get_unprocessed_nodes()

        for node in new_nodes:
            sliding_window.add(node)

        if sliding_window.expired():

            context = retrieval.build_context()

            inferred_edges = llm.infer(context)

            neo4j.insert_edges(inferred_edges)

            neo4j.mark_processed(window_nodes)

        time.sleep(1)

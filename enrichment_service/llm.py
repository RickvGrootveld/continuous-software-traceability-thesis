import time
import re
import json
import os
import random

from prompt import SYSTEM_PROMPT, load_system_prompt, load_user_prompt_v1 #, load_user_prompt

# Determine to use Qwen or GPT to prevent everything to be loaded and running when building the project in Docker
# Qwen
USE_LOCAL_QWEN = True
#USE_LOCAL_QWEN = False

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
QWEN_MODEL_NAME = "qwen3.5:4b"

if USE_LOCAL_QWEN:
    import ollama

# GPT
#USE_GPT = True
USE_GPT = False

OPENAI_API_KEY = "<YOUR_API_KEY>"
GPT_MODEL = "gpt-5.1"

if USE_GPT:
    from openai import OpenAI

def extract_json(raw: str) -> tuple[dict, int, int]:
    """
    Extract JSON from messy LLM output.
    Returns:
        (extracted_dict, total_edges_processed, valid_edges_count)
    """
    # Helper to calculate metrics if a complete JSON object/block is parsed successfully
    def get_full_block_metrics(parsed_dict: dict) -> tuple[dict, int, int]:
        edges_list = parsed_dict.get("new_edges", [])
        if isinstance(edges_list, list):
            count = len(edges_list)
            return parsed_dict, count, count
        return parsed_dict, 0, 0

    # Try direct parse first
    try:
        data = json.loads(raw)
        return get_full_block_metrics(data)
    except json.JSONDecodeError:
        pass
    
    # Try to find JSON block via regex
    match = re.search(r'\{.*"new_edges".*\}', raw, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            return get_full_block_metrics(data)
        except json.JSONDecodeError:
            pass
        
    # Try extracting individual edge objects and rebuild
    edges = re.findall(r'\{[^{}]*"source_id"[^{}]*\}', raw, re.DOTALL)
    total_edges = len(edges)
    
    if edges:
        valid = []
        for e in edges:
            try:
                parsed = json.loads(e)
                # Only keep edges with required keys
                required = {"source_id", "target_id", "label", "confidence", "system", "explanation"}
                if required.issubset(parsed.keys()):
                    valid.append(parsed)
            except json.JSONDecodeError:
                continue
        if valid:
            return {"new_edges": valid}, total_edges, len(valid)

    return {"new_edges": []}, total_edges, 0

def messages_object(graph_content):

    user_prompt = load_user_prompt_v1(json.dumps(graph_content, separators=(',', ':'))[:85000], random.randint(0,999999))
    return [
        {"role": "system",    "content": load_system_prompt(random.randint(0,999999))},
        {"role": "user",      "content": user_prompt},
        {"role": "assistant", "content": "{\n  \"new_edges\": ["}
    ]

class GPTClient:

    def __init__(self):
        print("Loading GPT...")
        self.client = OpenAI(
            api_key=OPENAI_API_KEY,
            base_url="https://api.openai.com/v1",
        )
        print("GPT-5.1 initialized")

    def call_llm(self, graph_content: dict) -> dict:
        """
        Calls GPT-5.1 via the OpenAI API.
        """

        start_time = time.perf_counter()

        response = self.client.chat.completions.create(
            model="gpt-5.1",
            messages=messages_object(graph_content),
            reasoning_effort="low",
            response_format={"type": "json_object"},
            max_completion_tokens=38000
        )

        total_duration = (time.perf_counter() - start_time) * 1000 #convert to ms, same as neo4j time responses

        # Extract raw content using OpenAI's response format
        raw = response.choices[0].message.content 
        print(f"response: {raw}")

        # Process JSON data using your extraction function
        result, generated_edges, correct_edges = extract_json(raw)

        # Validate and filter edge objects (Exactly identical to your Qwen logic)
        valid_edges = []
        required_keys = {"source_id", "target_id", "label", "confidence", "system", "explanation"}

        for edge in result.get("new_edges", []):
            if required_keys.issubset(edge.keys()) and edge.get("confidence", 0) > 0.85:
                valid_edges.append(edge)

        # OpenAI equivalent token and finish reason logging
        print(f"prompt tokens: {response.usage.prompt_tokens}")
        print(f"eval count (output tokens): {response.usage.completion_tokens}")
        print(f"stop reason: {response.choices[0].finish_reason}")
        print(f"Valid edges extracted: {len(valid_edges)}")
        print(f"Valid edges extracted v2: {correct_edges}")

        return (result, total_duration, generated_edges, correct_edges)

class QwenClient:

    def __init__(self):
        print("Loading Qwen...")
        self.client = ollama.Client(host="http://ollama:11434")
        self.ensure_model()
        print("Qwen initialized")

    def ensure_model(self) -> None:
        available = [m["model"] for m in self.client.list()["models"]]
        if QWEN_MODEL_NAME not in available:
            print(f"Model '{QWEN_MODEL_NAME}' not found locally. Pulling — this may take a few minutes...")
            self.client.pull(QWEN_MODEL_NAME)
            print("Model ready.")
        else:
            print(f"Model '{QWEN_MODEL_NAME}' already available.")

    def call_llm(self, graph_content: dict) -> dict:
        print("starting Qwen call...")

        start_time = time.perf_counter()

        response = self.client.chat(
            model=QWEN_MODEL_NAME,
            messages=messages_object(graph_content),
            format="json",
            keep_alive=0,
            options={
                "temperature": 0.2,
                "num_ctx": 36864,
                "num_predict": 1200,
                "num_batch": 512,
                "seed": random.randint(1, 9999999),
                "num_thread": 6,
                "stop": ["]\n}"],
            },
        )

        total_duration = (time.perf_counter() - start_time) * 1000 #convert to ms, same as neo4j time responses
        #print(f"Qwen call duration: {response.total_duration} seconds")

        prefix = "{\n  \"new_edges\": ["
        raw = prefix + response.message.content 
        # Content will only contain what the LLM has generated after the prefix. So, concatenate them

        result, generated_edges, correct_edges = extract_json(raw)
        
        # Validate and filter edge objects
        valid_edges = []
        required_keys = {"source_id", "target_id", "label", "confidence", "system", "explanation"}
        for edge in result.get("new_edges", []):
            if required_keys.issubset(edge.keys()) and edge.get("confidence", 0) > 0.85:
                valid_edges.append(edge)

        return {"new_edges": valid_edges}, total_duration, generated_edges, correct_edges
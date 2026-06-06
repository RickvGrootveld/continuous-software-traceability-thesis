from datetime import datetime
import re
import json
import os
import random

from prompt import SYSTEM_PROMPT, load_user_prompt_v1 #, load_user_prompt

# Determine to use Qwen or GPT to prevent everything to be loaded and running when building the project in Docker
# Qwen
USE_LOCAL_QWEN = True
# USE_LOCAL_QWEN = False

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
QWEN_MODEL_NAME = "qwen3.5:4b"
#GEMMA_MODEL_NAME = "gemma4:e2b"

if USE_LOCAL_QWEN:
    import ollama

# GPT
# USE_GPT = True
USE_GPT = False

OPENAI_API_KEY = "<YOUR_OPENAI_API_KEY>"
GPT_MODEL = "gpt-5.1"

if USE_GPT:
    from openai import OpenAI


def messages_object(graph_content):
    few_shot_input = {
        "sliding_window_events": {
            "nodes": [
                {
                    "a3f9c12b": {
                        "type": ["TraceabilityNode", "Commit"],
                        "id": "a3f9c12b",
                        "message": "Fix null pointer in authentication session handler and add login unit tests",
                        "committed_date": "2026-05-30T15:00:00Z"
                    }
                }
            ],
            "edges": []
        },
        "k_hop_neighbourhood": {
            "nodes": [
                {
                    "tom baker": {
                        "type": ["TraceabilityNode", "Developer"],
                        "id": "tom baker",
                        "name": "tom baker"
                    }
                },
                {
                    "src/auth/SessionHandler.java": {
                        "type": ["TraceabilityNode", "Code"],
                        "id": "src/auth/SessionHandler.java",
                        "file_path": "src/auth/SessionHandler.java",
                        "is_deleted": False
                    }
                }
            ],
            "edges": []
        },
        "vector_similarity_retrieval": {
            "nodes": [
                {
                    "LUCENE-2847": {
                        "type": ["TraceabilityNode", "Issue", "Bug"],
                        "id": "LUCENE-2847",
                        "title": "NullPointerException during login session setup",
                        "type": "Bug",
                        "status": "Open",
                        "summary": "App crashes immediately when the authentication session handler is initialised.",
                        "priority": "High",
                        "created_date": "2026-05-28T09:00:00Z",
                        "updated_date": "2026-05-29T11:00:00Z",
                        "resolved_date": None
                    }
                }   
            ],
            "edges": []
        }
    }

    few_shot_output = {
        "new_edges": [
            {
                "source_id": "a3f9c12b",
                "target_id": "LUCENE-2847",
                "label": "solves",
                "confidence": 0.93,
                "system": "LLM",
                "explanation": "Commit a3f9c12b explicitly fixes a null pointer in the session handler, directly matching the crash described in bug LUCENE-2847."
            },
            {
                "source_id": "a3f9c12b",
                "target_id": "src/auth/SessionHandler.java",
                "label": "modify",
                "confidence": 0.91,
                "system": "LLM",
                "explanation": "Commit a3f9c12b patches authentication session logic, meaning SessionHandler.java was directly modified."
            }
        ]
    }

    return [
        {"role": "system",    "content": SYSTEM_PROMPT},
        #{"role": "user",      "content": load_user_prompt_v1(few_shot_input)},
        #{"role": "assistant", "content": json.dumps(few_shot_output)},
        {"role": "user",      "content": load_user_prompt_v1(graph_content)},
        {"role": "assistant", "content": "{\n  \"new_edges\": ["}
    ]

    #return [
    #        {"role": "system",    "content": SYSTEM_PROMPT},
#
    #        {"role": "user",      "content": f"Analyze these software artifacts and extract traceability edges:\n{few_shot_input}"},
    #        {"role": "assistant",  "content": json.dumps(few_shot_output, indent=2)},
#
    #        {"role": "user",      "content": load_user_prompt_v1(graph_content)},
    #        {"role": "assistant",  "content": "{\n  \"new_edges\": ["}
    #    ]

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
        
        start_timer = datetime.now().isoformat()

        response = self.client.chat.completions.create(
            model="gpt-5.1",
            messages=messages_object(graph_content),
            reasoning_effort="low",
            response_format={"type": "json_object"},
        )

        end_timer = datetime.now().isoformat()
        print(f"GPT call duration: {(end_timer - start_timer).total_seconds()} seconds")

        return json.loads(response.choices[0].message.content)

class QwenClient:
    valid_edges = 0
    total_edges = 0

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
    
    def extract_json(self, raw: str) -> dict:
        """Extract JSON from messy LLM output."""
        # Try direct parse first
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        
        # Try to find JSON block via regex
        match = re.search(r'\{.*"new_edges".*\}', raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        # Try extracting individual edge objects and rebuild
        edges = re.findall(r'\{[^{}]*"source_id"[^{}]*\}', raw, re.DOTALL)
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
                return {"new_edges": valid}

        return {"new_edges": []}

    def call_llm(self, graph_content: dict) -> dict:
        print("starting Qwen call...")
        start_timer = datetime.now()

        response = self.client.chat(
            model=QWEN_MODEL_NAME,
            messages=messages_object(graph_content),
            format="json",
            think="low",
            options={
                "temperature": 0.2,
                "num_ctx": 16384,   
                "num_predict": 1000,
                "seed": random.randint(1, 9999999),
                "stop": ["]\n}"],
                "keep_alive": 0,
            },
        )
        print(f"Qwen call duration: {response.total_duration} seconds")

        prefix = "{\n  \"new_edges\": ["
        raw = prefix + response.message.content 
        # Content will only contain what the LLM has generated after the prefix. So, concatenate them
        print(f"response: {raw}")

        result = self.extract_json(raw)
        
        # Validate and filter edge objects
        valid_edges = []
        required_keys = {"source_id", "target_id", "label", "confidence", "system", "explanation"}
        for edge in result.get("new_edges", []):
            if required_keys.issubset(edge.keys()) and edge.get("confidence", 0) > 0.85:
                valid_edges.append(edge)
                self.valid_edges += 1
            self.total_edges += 1

        print(f"prompt tokens: {response.prompt_eval_count}")
        print(f"eval count (output tokens): {response.eval_count}")
        print(f"stop reason: {response.done_reason}")
        print(f"Valid edges extracted: {valid_edges}")

        return {"new_edges": valid_edges}
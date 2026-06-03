from datetime import datetime
import json
import os
from sys import prefix

from prompt import SYSTEM_PROMPT, load_user_prompt, load_user_prompt_v1

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
                    "id": "commit_5a261565",
                    "type": ["TraceabilityNode", "Commit"],
                    "properties": {
                        "message": "Update authentication routing handlers and add login testing specs",
                        "timestamp": "2026-05-30T15:00:00Z"
                    }
                }
            ],
            "edges": []
        },
        "k_hop_neighbourhood": {
            "nodes": [
                {
                    "id": "src/java/org/apache/lucene/search/Query.java",
                    "type": ["TraceabilityNode", "File"],
                    "properties": {
                        "path": "src/java/org/apache/lucene/search/Query.java"
                    }
                }
            ],
            "edges": []
        },
        "vector_similarity_retrieval": {
            "nodes": [
                {
                    "id": "issue_BUG-942",
                    "type": ["TraceabilityNode", "Issue", "Bug"],
                    "properties": {
                        "title": "NullPointerException during login session setup",
                        "description": "App crashes immediately when hitting the authentication router link."
                    }
                }
            ],
            "edges": []
        }
    }

    # 2. Mock Output showing the model exactly how to map links using the input IDs
    few_shot_output = {
        "new_edges": [
            {
                "source_id": "commit_5a261565",
                "target_id": "issue_BUG-942",
                "label": "RESOLVES",
                "system": "LLM",
                "confidence": 0.92,
                "explanation": "Commit 5a261565 explicitly mentions fixing the authentication routing handlers, which matches the crash described in issue BUG-942."
            },
            {
                "source_id": "commit_5a261565",
                "target_id": "src/java/org/apache/lucene/search/Query.java",
                "label": "MODIFY",
                "system": "LLM",
                "confidence": 0.85,
                "explanation": "The commit modifies authentication logic which directly impacts query executions defined inside Query.java."
            }
        ]
    }

    return [
            {"role": "system",    "content": SYSTEM_PROMPT},

            #{"role": "user",      "content": f"Analyze these software artifacts and extract traceability edges:\n{few_shot_input}"},
            #{"role": "assistant",  "content": json.dumps(few_shot_output, indent=2)},

            {"role": "user",      "content": load_user_prompt_v1(graph_content)},
            {"role": "assistant",  "content": "{\n  \"new_edges\": ["}
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
        start_timer = datetime.now()

        response = self.client.chat(
            model=QWEN_MODEL_NAME,
            messages=messages_object(graph_content),
            #format="json",
            think="low",
            options={"temperature": 0.1},
        )

        end_timer = datetime.now()
        print(f"Qwen call duration: {(end_timer - start_timer).total_seconds()} seconds")

        prefix = "{\n  \"new_edges\": ["
        api_response = prefix + response.message.content 
        # Content will only contain what the LLM has generated after the prefix. So, concatenate them
        print(f"response: {api_response}")
        
        try:
            return json.loads(api_response)
        except json.JSONDecodeError:
            print("Fallback: JSON parsing failed. Returning empty graph edge payload.")
            return {"new_edges": []}
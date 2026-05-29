from datetime import datetime
import json
import os

from prompt import SYSTEM_PROMPT, load_user_prompt

# Determine to use Qwen or GPT to prevent everything to be loaded and running when building the project in Docker
# Qwen
USE_LOCAL_QWEN = True
# USE_LOCAL_QWEN = False

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
QWEN_MODEL_NAME = "qwen3.5:4b"

if USE_LOCAL_QWEN:
    import ollama

# GPT
# USE_GPT = True
USE_GPT = False

OPENAI_API_KEY = "<YOUR_OPENAI_API_KEY>"
GPT_MODEL = "gpt-5.1"

if USE_GPT:
    from openai import OpenAI


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

        messages = [
            {"role": "system",    "content": SYSTEM_PROMPT},
            {"role": "user",      "content": load_user_prompt(graph_content)},
            {"role": "assistant",  "content": "{\n  \"new_edges\": ["}
        ]
        
        start_timer = datetime.now().isoformat()

        response = self.client.chat.completions.create(
            model="gpt-5.1",
            messages=messages,
            reasoning_effort="low",
            response_format={"type": "json_object"},
        )

        end_timer = datetime.now().isoformat()
        print(f"GPT call duration: {(end_timer - start_timer).total_seconds()} seconds")

        return json.loads(response.choices[0].message.content)

    #def infer_edges(self, nodes, edges):
    #    
    #    # Remove the embeddings from the nodes fed to the LLM to reduce input tokens
    #    for node in nodes:
    #        node["properties"].pop("embedding", None)
    #
    #    prompt = f"""
    #    NODES:
    #    {json.dumps(nodes, indent=2)}
    #
    #    EDGES:
    #    {json.dumps(edges, indent=2)}
    #
    #    Infer missing relationships.
    #    """
    #
    #    response = self.client.chat.completions.create(
    #        model=GPT_MODEL,
    #        messages=[
    #            {
    #                "role": "system",
    #                "content": SYSTEM_PROMPT
    #            },
    #            {
    #                "role": "user",
    #                "content": prompt
    #            }
    #        ],
    #        temperature=0.0
    #    )
    #    content = response.choices[0].message.content
    #    return json.loads(content)

class QwenClient:

    def __init__(self):
        print("Loading QWEN...")
        #self.tokenizer = \
        #    AutoTokenizer.from_pretrained(
        #        QWEN_MODEL_NAME
        #    )
        #self.model = \
        #    AutoModelForCausalLM.from_pretrained(
        #        QWEN_MODEL_NAME,
        #        dtype=torch.float16,
        #        device_map="auto"
        #    )
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

    #def call_llm(self, messages: list) -> list[dict]:
    #    response = self.client.chat(
    #        model=QWEN_MODEL_NAME,
    #        messages=messages,
    #        options={"temperature": 0.0} # deterministic output
    #    )
    #    raw = response["message"]["content"].strip()
    #    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    #    return json.loads(raw)
    
    def call_llm(self, graph_content: dict) -> dict:
        messages = [
            {"role": "system",    "content": SYSTEM_PROMPT},
            {"role": "user",      "content": load_user_prompt(graph_content)},
            {"role": "assistant",  "content": "{\n  \"new_edges\": ["}
        ]

        start_timer = datetime.now()

        response = self.client.chat(
            model="qwen3.5:4b",
            messages=messages,
            format="json",
            think="low",
            options={"temperature": 0.0},
        )

        end_timer = datetime.now()
        print(f"Qwen call duration: {(end_timer - start_timer).total_seconds()} seconds")

        prefix = '{\n  "new_edges": ['

        api_response = response.message.content 
        # Content will only contain what the LLM has generated after the prefix. So, concatenate them
        full_json_string = prefix + api_response

        return json.loads(full_json_string)

    #def infer_edges(self, nodes, edges):
    #    # Remove the embeddings from the nodes fed to the LLM to reduce input tokens
    #    for node in nodes:
    #        node["properties"].pop("embedding", None)
    #
    #    prompt = f"""
    #    NODES:
    #    {json.dumps(nodes, indent=2)}
    #
    #    EDGES:
    #    {json.dumps(edges, indent=2)}
    #
    #    Infer missing relationships.
    #    """
    #
    #    messages = [
    #        {
    #            "role": "system",
    #            "content": SYSTEM_PROMPT
    #        },
    #        {
    #            "role": "user",
    #            "content": prompt
    #        }
    #    ]
    #
    #    response = self.call_llm(messages)
    #
    #    #text = self.tokenizer.apply_chat_template(
    #    #    messages,
    #    #    tokenize=False,
    #    #    add_generation_prompt=True
    #    #)
    #    #model_inputs = self.tokenizer(
    #    #    [text],
    #    #    return_tensors="pt"
    #    #).to(self.model.device)
    #    #generated_ids = self.model.generate(
    #    #    **model_inputs,
    #    #    max_new_tokens=1024,
    #    #    temperature=0.0
    #    #)
    #    #output_ids = generated_ids[0][
    #    #    len(model_inputs.input_ids[0]):]
    #    #response = self.tokenizer.decode(
    #    #    output_ids,
    #    #    skip_special_tokens=True
    #    #)
    #    return json.loads(response)
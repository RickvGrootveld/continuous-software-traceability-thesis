import json


#determine to use qwen to prevent everything to be loaded and running when building the project in Docker
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

class GPTClient:

    def __init__(self):
        print("Loading GPT...")
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        print("GPT-5.1 initialized")

    def infer_edges(self, nodes, edges):
        
        # Remove the embeddings from the nodes fed to the LLM to reduce input tokens
        for node in nodes:
            node["properties"].pop("embedding", None)

        prompt = f"""
        NODES:
        {json.dumps(nodes, indent=2)}

        EDGES:
        {json.dumps(edges, indent=2)}

        Infer missing relationships.
        """

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

class QwenClient:

    def __init__(self):
        print("Loading QWEN...")
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

    def infer_edges(self, nodes, edges):
        # Remove the embeddings from the nodes fed to the LLM to reduce input tokens
        for node in nodes:
            node["properties"].pop("embedding", None)

        prompt = f"""
        NODES:
        {json.dumps(nodes, indent=2)}

        EDGES:
        {json.dumps(edges, indent=2)}

        Infer missing relationships.
        """

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
            temperature=0.0
        )
        output_ids = generated_ids[0][
            len(model_inputs.input_ids[0]):]
        response = self.tokenizer.decode(
            output_ids,
            skip_special_tokens=True
        )
        return json.loads(response)
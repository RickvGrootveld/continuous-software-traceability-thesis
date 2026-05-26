import json
import os
import ollama
from openai import OpenAI

from prompt_v4 import SYSTEM_PROMPT, USER_PROMPT

API_KEY = "<YOUR_API_KEY>"

messages = [
    {"role": "system",    "content": SYSTEM_PROMPT},
    {"role": "user",      "content": USER_PROMPT},
    {"role": "assistant",  "content": "{\n  \"new_edges\": ["}
]

def call_gpt() -> dict:
    """
    Calls GPT-5.1 via the OpenAI API.
    """
    client = OpenAI(
        api_key=API_KEY,
        base_url="https://api.openai.com/v1",
    )

    response = client.chat.completions.create(
        model="gpt-5.1",
        messages=messages,
        reasoning_effort="low",
        response_format={"type": "json_object"},
    )

    return json.loads(response.choices[0].message.content)


def call_qwen() -> dict:
    client = ollama.Client(host="http://host.docker.internal:11434") #"http://localhost:11434/v1"    "http://ollama:11434"

    response = client.chat(
        model="qwen3.5:4b",
        messages=messages,
        format="json",
        think="low",
        options={"temperature": 0.0},
    )
    prefix = '{\n  "new_edges": ['

    api_response = response.message.content 
    # Content will only contain what the LLM has generated after the prefix. So, concatenate them
    full_json_string = prefix + api_response

    return json.loads(full_json_string)


if __name__ == "__main__":
    # result = call_gpt()
    result = call_qwen()

    with open("response_llm.json", "w") as f:
        json.dump(result, f, indent=2)
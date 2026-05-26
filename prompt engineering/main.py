import json
import os
import ollama
from openai import OpenAI

#from initial_prompt import SYSTEM_PROMPT, USER_PROMPT
#from final_prompt import FINAL_SYSTEM_PROMPT, FINAL_USER_PROMPT
from initial_prompt_better import BETTER_SYSTEM_PROMPT, BETTER_USER_PROMPT


messages = [
    {"role": "system",    "content": BETTER_SYSTEM_PROMPT},
    {"role": "user",      "content": BETTER_USER_PROMPT},
]

def call_gpt() -> dict:
    """
    Calls GPT-5.1 via the OpenAI API.
    """
    client = OpenAI(
        api_key="YOUR_API_KEY",
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
    print(f"response = {response}")
    return json.loads(response.message.content)


if __name__ == "__main__":
    # result = call_gpt()
    result = call_qwen()

    with open("response_llm.json", "w") as f:
        json.dump(result, f, indent=2)
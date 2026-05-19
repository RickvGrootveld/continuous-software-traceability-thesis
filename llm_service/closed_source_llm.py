import time
import sys
import argparse
from pathlib import Path
from openai import OpenAI

API_KEY = "[API KEY HERE]"   # <-- put your API key here
MODEL   = "gpt-5"                      # or "gpt-5-mini" / "gpt-5-nano"
CONFIDENCE_THRESHOLD = 0.8

INSTRUCTIONS = """You, a software developer, need to insert code documentation to make the Python code more 
readable and comprehensible. This code documentation should be done on all functions and classes to explain
what they do. The documentation of a function should be written underneath the function header and the
documentation of a class should be written underneath the class header. To improve the readability of a
function, comments between the lines in functions might also be needed but don’t make it redundant if not
necessary. As an input, you will get a Python file that doesn't contain any comments and only consists of a
class and functions. You will then insert the comments into that file to complement the code. The output
should be the same Python file with the same code but with the added documentation for functions and classes.
Also, the output file should only be the Python file and nothing else."""

#llm_edge = {
#    "source": ?,
#    "target": ?,
#    "label": ?,
#    "properties": {
#        "timestamp": ?,
#        "system": "LLM",
#        "confidence": ?,
#        "explanation": ?
#    }
#}


def build_prompt(edge: dict) -> str:
    return f"""
    You are enriching a knowledge graph edge. Given this relationship:

    Source : {edge['source']} ({edge['source_label']})
    Relation: {edge['rel_type']}
    Target : {edge['target']} ({edge['target_label']})

    Return a JSON object with these fields:
    - "description"  : a 1–2 sentence explanation of why this relationship exists
    - "confidence"   : a float 0.0–1.0 indicating how confident you are
    - "keywords"     : a list of 3–5 relevant keyword strings
    - "relation_subtype" : a more specific label for this edge (e.g. CAUSES → DIRECTLY_CAUSES)

    Respond with ONLY valid JSON, no markdown, no extra text.
    """

def closed_llm_enrichment():
    parser = argparse.ArgumentParser(
        description="Add comments/docstrings to a Python file using GPT-5."
    )
    parser.add_argument("--mode", choices=["zero", "few"], default="zero",
                        help="zero: no examples; few: include example files to learn style.")
    parser.add_argument("target", help="Path to the Python file to comment.")
    parser.add_argument("examples", nargs="*", help="(few-shot only) One or more commented example .py files.")
    args = parser.parse_args()

    target_path = Path(args.target)
    if not target_path.exists():
        raise SystemExit(f"Target not found: {target_path}")

    target_code = read_text(target_path)

    prompt = build_prompt()

    client = OpenAI(api_key=API_KEY)

    t0 = time.perf_counter()
    resp = client.responses.create(
        model=MODEL,
        input=prompt,
        reasoning={"effort": "minimal"},   # GPT-5: keep output concise; no temperature on reasoning models
    )
    elapsed = time.perf_counter() - t0

    print(strip_code_fences(resp.output_text))  # ONLY the new Python code
    print(f"[timing] total_seconds={elapsed:.3f}", file=sys.stderr)
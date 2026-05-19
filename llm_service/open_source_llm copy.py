import ollama
import json
import os

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
NEO4J_URI  = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD", "yourpassword")
MODEL      = "llama3.1:8b"
CONFIDENCE_THRESHOLD = 0.8

#llm_edge = {
#    "source": f"Commit:{commit_hash}",
#    "target": f"Code:{cc['file_path']}",
#    "label": cc["change_type"],
#    "properties": {
#        "timestamp": timestamp,
#        "system": "LLM",
#        "confidence": 0.85,
#        "explanation": ""
#    }
#}

# ── 1. Fetch graph data ────────────────────────────────────────────────────────

def fetch_graph_context(driver) -> list[dict]:
    """
    Fetch commits and their associated code files from Neo4j.
    Returns a flat list of context records for the LLM.
    """
    query = """
        MATCH (commit:Commit)-[r]->(code:Code)
        WHERE r.system <> 'LLM' OR r.system IS NULL
        RETURN
            commit.hash        AS commit_hash,
            commit.message     AS commit_message,
            commit.author      AS author,
            commit.timestamp   AS commit_timestamp,
            code.file_path     AS file_path,
            code.language      AS language,
            code.content       AS content,
            type(r)            AS existing_relation
        LIMIT 100
    """
    with driver.session() as session:
        return session.run(query).data()

# ── 2. Build the prompt ────────────────────────────────────────────────────────

def build_prompt(records: list[dict]) -> str:
    """
    Serialize graph context into a prompt that instructs the LLM
    to infer new typed edges between Commit and Code nodes.
    """
    context_lines = []
    for r in records:
        context_lines.append(
            f"- Commit {r['commit_hash'][:8]} by {r['author']}: "
            f"\"{r['commit_message']}\" → file: {r['file_path']} ({r['language']})"
        )

    context_block = "\n".join(context_lines)

    return f"""
    You are analyzing a software knowledge graph containing Commit nodes and Code nodes.

    Here is the current graph data:
    {context_block}

    Your task:
    For each Commit → Code pair above, infer the most semantically accurate relationship label
    and explain your reasoning. Valid labels include but are not limited to:
      MODIFIES, REFACTORS, FIXES, INTRODUCES, DELETES, TESTS, DOCUMENTS

    Return ONLY a JSON array. Each element must follow this exact schema:
    {{
      "source": "Commit:<full_commit_hash>",
      "target": "Code:<file_path>",
      "label": "<RELATIONSHIP_LABEL>",
      "properties": {{
        "confidence": <float 0.0-1.0>,
        "explanation": "<one sentence justification>"
      }}
    }}

    No markdown. No extra text. Only the JSON array.
    """

# ── 3. Call the LLM ───────────────────────────────────────────────────────────

def call_llm(prompt: str) -> list[dict]:
    """Send the prompt to Llama and parse the returned JSON array."""
    client = ollama.Client(host=OLLAMA_URL)
    response = client.chat(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": 0.0} # deterministic output
    )

    raw = response["message"]["content"].strip()
    # Strip accidental markdown fences
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    return json.loads(raw)

# ── 4. Entrypoint ─────────────────────────────────────────────────────────────

def run_llm_enrichment(kg_driver) -> list[dict]:
    try:
        print("Fetching graph context...")
        records = fetch_graph_context(kg_driver)

        if not records:
            print("No unenriched edges found. Exiting.")
            return

        print(f"Building prompt from {len(records)} records...")
        prompt = build_prompt(records)

        print("Calling LLM...")
        raw_edges = call_llm(prompt)
    finally:
        kg_driver.close()
        
    return raw_edges
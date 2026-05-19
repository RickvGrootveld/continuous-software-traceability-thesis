#import ollama
#import json
#import os
#from datetime import datetime, timezone
#from neo4j import GraphDatabase
#from knowledge_graph import link_nodes
#from schema import SCHEMA
#
#OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
#NEO4J_URI  = os.getenv("NEO4J_URI",  "bolt://neo4j:7687")
#NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
#NEO4J_PASS = os.getenv("NEO4J_PASSWORD", "yourpassword")
#MODEL      = "qwen3.5:4b-thinking" 
#
#
## ── 1. Find which schema entries apply to a given node label ──────────────────
#
#def get_relevant_schema(node_label: str) -> list[tuple[str, dict, str]]:
#    """
#    Returns a list of (rel_key, rel_def, role) tuples where role is
#    'source' or 'target', indicating how the known node participates.
#    """
#    relevant = []
#    for rel_key, rel_def in SCHEMA.items():
#        if rel_def["source"]["label"] == node_label:
#            relevant.append((rel_key, rel_def, "source"))
#        if rel_def["target"]["label"] == node_label:
#            relevant.append((rel_key, rel_def, "target"))
#    return relevant
#
#
## ── 2. Fetch candidate pairs anchored to the known node ───────────────────────
#
#def fetch_pairs(driver, rel_key: str, rel_def: dict, role: str,
#                known_id_prop: str, known_id_val: str) -> list[dict]:
#    """
#    Fetch candidate pairs where one side is the known node.
#    Role indicates whether the known node is 'source' or 'target'.
#    """
#    src = rel_def["source"]
#    tgt = rel_def["target"]
#
#    src_props = ", ".join(f"a.{p} AS src_{p}" for p in src["fetch_props"])
#    tgt_props = ", ".join(f"b.{p} AS tgt_{p}" for p in tgt["fetch_props"])
#
#    self_ref_guard = (
#        "AND elementId(a) <> elementId(b)"
#        if src["label"] == tgt["label"] else ""
#    )
#
#    if role == "source":
#        # Known node is the source — fix 'a', iterate over 'b'
#        anchor_clause = f"MATCH (a:{src['label']} {{{known_id_prop}: $known_val}}), (b:{tgt['label']})"
#    else:
#        # Known node is the target — fix 'b', iterate over 'a'
#        anchor_clause = f"MATCH (a:{src['label']}), (b:{tgt['label']} {{{known_id_prop}: $known_val}})"
#
#    query = f"""
#        {anchor_clause}
#        WHERE NOT (a)-[:{rel_key} {{system: 'LLM'}}]->(b)
#        {self_ref_guard}
#        RETURN
#            elementId(a)        AS src_eid,
#            a.{src['id_prop']}  AS src_id,
#            elementId(b)        AS tgt_eid,
#            b.{tgt['id_prop']}  AS tgt_id,
#            {src_props},
#            {tgt_props}
#        LIMIT 50
#    """
#
#    with driver.session() as session:
#        return session.run(query, known_val=known_id_val).data()
#
#
## ── 3. Build prompt ───────────────────────────────────────────────────────────
#
#def build_prompt(rel_key: str, rel_def: dict, pairs: list[dict]) -> str:
#    src    = rel_def["source"]
#    tgt    = rel_def["target"]
#    labels = rel_def["valid_labels"]
#    hint   = rel_def["prompt_hint"]
#
#    pair_lines = []
#    for p in pairs:
#        src_details = " | ".join(
#            f"{prop}: {p.get(f'src_{prop}', 'N/A')}"
#            for prop in src["fetch_props"]
#        )
#        tgt_details = " | ".join(
#            f"{prop}: {p.get(f'tgt_{prop}', 'N/A')}"
#            for prop in tgt["fetch_props"]
#        )
#        pair_lines.append(
#            f"- source ({src['label']}) id={p['src_id']} [{src_details}]"
#            f" → target ({tgt['label']}) id={p['tgt_id']} [{tgt_details}]"
#        )
#
#    return f"""
#    You are enriching a software knowledge graph.
#    Task: {hint}
#    
#    Node pairs to analyze:
#    {chr(10).join(pair_lines)}
#    
#    For each pair, choose the single best relationship label from: {", ".join(labels)}
#    
#    Return ONLY a JSON array. Each element must follow this exact schema:
#    {{
#      "source": "{src['label']}:<src_id_value>",
#      "target": "{tgt['label']}:<tgt_id_value>",
#      "label":  "<CHOSEN_LABEL>",
#      "properties": {{
#        "confidence":  <float 0.0-1.0>,
#        "explanation": "<one sentence justification>"
#      }}
#    }}
#    
#    No markdown, no extra text. Only the JSON array.
#    """
#
#
## ── 4. Call the LLM ───────────────────────────────────────────────────────────
#
#def call_llm(prompt: str) -> list[dict]:
#    client   = ollama.Client(host=OLLAMA_URL)
#    response = client.chat(
#        model=MODEL,
#        messages=[{"role": "user", "content": prompt}],
#        options={"temperature": 0.0} # deterministic output
#    )
#    raw = response["message"]["content"].strip()
#    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
#    return json.loads(raw)
#
#
## ── 5. Assemble edge ──────────────────────────────────────────────────────────
#
#def assemble_edge(raw: dict) -> dict:
#    return {
#        "source": raw["source"],
#        "target": raw["target"],
#        "label":  raw["label"],
#        "properties": {
#            "timestamp":   datetime.now(timezone.utc).isoformat(),
#            "system":      "LLM",
#            "confidence":  float(raw["properties"].get("confidence", 0.0)),
#            "explanation": raw["properties"].get("explanation", ""),
#        }
#    }
#
#
## ── 6. Write edges ────────────────────────────────────────────────────────────
#
#def resolve_node(session, label: str, id_prop: str, id_val: str):
#    result = session.run(
#        f"MATCH (n:{label}) WHERE n.{id_prop} = $val RETURN elementId(n) AS eid LIMIT 1",
#        val=id_val
#    ).single()
#    return result["eid"] if result else None
#
#
#def write_edges(driver, edges: list[dict], rel_def: dict) -> None:
#    src_label   = rel_def["source"]["label"]
#    tgt_label   = rel_def["target"]["label"]
#    src_id_prop = rel_def["source"]["id_prop"]
#    tgt_id_prop = rel_def["target"]["id_prop"]
#
#    with driver.session() as session:
#        for edge in edges:
#            _, src_val = edge["source"].split(":", 1)
#            _, tgt_val = edge["target"].split(":", 1)
#
#            src_eid = resolve_node(session, src_label, src_id_prop, src_val)
#            tgt_eid = resolve_node(session, tgt_label, tgt_id_prop, tgt_val)
#
#            if not src_eid or not tgt_eid:
#                print(f"Node not found: {edge['source']} or {edge['target']} — skipping")
#                continue
#
#            session.run(
#                """
#                MATCH (a) WHERE elementId(a) = $src_eid
#                MATCH (b) WHERE elementId(b) = $tgt_eid
#                CALL apoc.merge.relationship(a, $label, {system: 'LLM'}, $props, b)
#                YIELD rel RETURN rel
#                """,
#                src_eid=src_eid,
#                tgt_eid=tgt_eid,
#                label=edge["label"],
#                props=edge["properties"]
#            )
#            print(
#                f"  {edge['source']} -[{edge['label']}]-> {edge['target']} "
#                f"(confidence: {edge['properties']['confidence']:.2f})"
#            )
#
#
## ── 7. Entrypoint ─────────────────────────────────────────────────────────────
#
#def ensure_model(client: ollama.Client) -> None:
#    available = [m["model"] for m in client.list()["models"]]
#    if MODEL not in available:
#        print(f"Model '{MODEL}' not found locally. Pulling — this may take a few minutes...")
#        client.pull(MODEL)
#        print("Model ready.")
#    else:
#        print(f"Model '{MODEL}' already available.")
#
#
#def call_llm(client: ollama.Client, prompt: str) -> list[dict]:
#    response = client.chat(
#        model=MODEL,
#        messages=[{"role": "user", "content": prompt}],
#        options={"temperature": 0.1}
#    )
#    raw = response["message"]["content"].strip()
#    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
#    return json.loads(raw)
#
#
#def run_llm_enrichment(llm_client, driver, incoming_nodes: list[dict]) -> None:
#    try:
#        for node in incoming_nodes:
#            node_label = node["type"]
#            id_val     = node["id"]
#
#            print(f"\n══ Processing node: {node_label} (id={id_val}) ══")
#
#            relevant = get_relevant_schema(node_label)
#            if not relevant:
#                print(f"  No schema entries found for label '{node_label}', skipping.")
#                continue
#
#            for rel_key, rel_def, role in relevant:
#                print(f"\n  ── Checking: {rel_key} (node is {role}) ──")
#
#                id_prop = rel_def[role]["id_prop"]
#                pairs   = fetch_pairs(driver, rel_key, rel_def, role, id_prop, id_val)
#
#                if not pairs:
#                    print("    No unenriched pairs found, skipping.")
#                    continue
#
#                print(f"    Found {len(pairs)} candidate pairs.")
#                prompt    = build_prompt(rel_key, rel_def, pairs)
#                raw_edges = call_llm(llm_client, prompt)
#                edges     = [assemble_edge(e) for e in raw_edges]
#                print(f"enriched edges: {edges[0]}")
#                with driver.session() as session:
#                    try:
#                        session.execute_write(link_nodes, edges)
#                    except Exception as e:
#                        print(f"Error occurred while inserting enrichment record: {e}")
#
#
#        print("\nEnrichment complete.")
#    finally:
#        driver.close()
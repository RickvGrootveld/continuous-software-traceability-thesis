"""
Change Impact Analysis (CIA) query runner for software traceability knowledge graph.

Usage:
    python cia_query.py <commit_hash> [--output <file>] [--max-hops <n>]

Examples:
    python cia_query.py abc123def456
    python cia_query.py abc123def456 --output results/cia_abc123.json
    python cia_query.py abc123def456 --max-hops 4 --output results/cia_abc123.json

The script:
  1. Looks up the source commit node and its insertion timestamp.
  2. Traverses all edges whose timestamp <= commit insertion time (temporal filter).
  3. Collects all reachable nodes, their types, hop distance, and the edge path taken.
  4. Saves structured JSON output for downstream analysis.
"""

import json
import os
import sys
from datetime import datetime, timezone

from neo4j import GraphDatabase

# ---------------------------------------------------------------------------
# Configuration — override via environment variables or edit defaults below
# ---------------------------------------------------------------------------
NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
DEFAULT_MAX_HOPS = 4


# ---------------------------------------------------------------------------
# Neo4j helpers
# ---------------------------------------------------------------------------

def get_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def fetch_source_node(tx, commit_hash: str) -> dict | None:
    """
    Retrieve the source commit node and its insertion timestamp.
    Returns None if the commit is not found in the graph.
    """
    result = tx.run(
        """
        MATCH (c:TraceabilityNode:Commit {id: $commit_hash})
        RETURN
            c.id           AS id,
            c.timestamp    AS timestamp,
            labels(c)      AS labels,
            properties(c)  AS props
        LIMIT 1
        """,
        commit_hash=commit_hash,
    )
    record = result.single()
    if record is None:
        return None
    return {
        "id":        record["id"],
        "timestamp": record["timestamp"],
        "labels":    record["labels"],
        "props":     dict(record["props"]),
    }


def run_cia_traversal(tx, commit_hash: str, cutoff_ts: str, max_hops: int) -> list[dict]:
    """
    Traverse the graph from the source commit with three constraints:

    1. TEMPORAL: every edge in the path must have timestamp < cutoff_ts
       (strictly less than, so same-batch edges such as commit->codefile are excluded).
    2. NODE EXCLUSION: CodeFile nodes are never traversed into. The commit->codefile
       edges share the same batch timestamp as the commit itself, so strict < already
       excludes them from hop 1. This label filter acts as an explicit safeguard and
       also prevents re-entry via indirect paths at deeper hops.
    3. ALL-EDGES checked: the ALL() predicate applies the temporal filter to every
       relationship in the path, not just the last one, preventing traversal through
       future-timestamped intermediate edges.

    Returns a list of reached nodes with metadata.
    """
    query = """
    MATCH (source:TraceabilityNode:Commit {id: $commit_hash})

    // Variable-length traversal, both directions, depth 1..max_hops
    MATCH path = (source)-[rels*1..{max_hops}]-(reached)

    // 1. Every edge in the path must be strictly before the commit's batch timestamp
    WHERE ALL(r IN relationships(path) WHERE r.timestamp < $cutoff_ts)

    // 2. Block direct source->codefile hop only, not codefiles reached via other nodes
    AND NOT (length(path) = 1 AND reached:CodeFile)

    // 3. Do not return the source node itself
    AND reached <> source

    WITH
        reached,
        length(path)                          AS hops,
        last(relationships(path))             AS last_rel,
        [n IN nodes(path) | n.id]             AS path_node_ids,
        [r IN relationships(path) | type(r)]  AS path_edge_types

    // Keep shortest path per reached node (BFS equivalent)
    WITH reached, min(hops) AS hops, last_rel, path_node_ids, path_edge_types

    RETURN DISTINCT
        reached.id                        AS node_id,
        labels(reached)                   AS node_labels,
        reached.timestamp                 AS node_timestamp,
        hops                              AS hop_distance,
        last_rel.timestamp                AS edge_timestamp,
        type(last_rel)                    AS edge_type,
        last_rel.system                   AS edge_system,
        path_node_ids                     AS path_node_ids,
        path_edge_types                   AS path_edge_types

    ORDER BY hops ASC, node_id ASC
    """
    # Inject max_hops into the query string (Cypher does not support
    # parameters inside relationship length syntax *1..n)
    query = query.replace("{max_hops}", str(max_hops))

    results = tx.run(
        query,
        commit_hash=commit_hash,
        cutoff_ts=cutoff_ts,
        max_hops=max_hops,
    )

    rows = []
    for record in results:
        rows.append({
            "node_id":        record["node_id"],
            "node_labels":    record["node_labels"],
            "node_timestamp": record["node_timestamp"],
            "hop_distance":   record["hop_distance"],
            "edge_type":      record["edge_type"],
            "edge_system":    record["edge_system"],   # 'dataset' | 'LLM' | None
            "edge_timestamp": record["edge_timestamp"],
            "path_node_ids":  record["path_node_ids"],
            "path_edge_types":record["path_edge_types"],
        })
    return rows


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------

def summarise(source: dict, reached: list[dict]) -> dict:
    """Build a summary dict for easy inspection and downstream analysis."""

    # Separate node types (strip 'TraceabilityNode' label which is on everything)
    def primary_label(labels: list[str]) -> str:
        filtered = [l for l in labels if l != "TraceabilityNode"]
        return filtered[0] if filtered else "Unknown"

    by_type: dict[str, list] = {}
    by_hop:  dict[int, list] = {}
    llm_only_nodes = []   # nodes reachable ONLY via at least one LLM edge in their path
    dataset_nodes  = []

    for node in reached:
        ptype = primary_label(node["node_labels"])
        by_type.setdefault(ptype, []).append(node["node_id"])
        by_hop.setdefault(node["hop_distance"], []).append(node["node_id"])

        if node["edge_system"] == "LLM":
            llm_only_nodes.append(node["node_id"])
        else:
            dataset_nodes.append(node["node_id"])

    return {
        "total_reached":        len(reached),
        "by_node_type":         {k: len(v) for k, v in by_type.items()},
        "by_hop_distance":      {k: len(v) for k, v in by_hop.items()},
        "llm_edge_reached":     len(llm_only_nodes),   # last edge into node was LLM
        "dataset_edge_reached": len(dataset_nodes),
        "node_types_reached":   sorted(by_type.keys()),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    # ---------------------------------------------------------------------------
    # Configure your run here
    # ---------------------------------------------------------------------------
    commit_hashes = [
        "e9e7d0a287ad95e71f02eef61a190b2c02e3b21b "   # replace with your 7 commit hashes
    ]
    max_hops   = DEFAULT_MAX_HOPS   # Maximum traversal depth (default: 4)
    output_dir = "cia_results"      # Directory where all result files are saved
    # ---------------------------------------------------------------------------

    print(f"[CIA] Graph      : {NEO4J_URI}")
    print(f"[CIA] Max hops   : {max_hops}")
    print(f"[CIA] Commits    : {len(commit_hashes)}")
    print(f"[CIA] Output dir : {output_dir}/")
    print()

    os.makedirs(output_dir, exist_ok=True)
    driver = get_driver()

    succeeded = []
    failed    = []

    try:
        with driver.session() as session:
            for i, commit_hash in enumerate(commit_hashes, start=1):
                print(f"[{i}/{len(commit_hashes)}] Commit: {commit_hash}")

                # 1. Fetch source node + its insertion timestamp
                source = session.execute_read(fetch_source_node, commit_hash)
                if source is None:
                    print(f"         ERROR — commit not found in graph, skipping.\n")
                    failed.append({"commit_hash": commit_hash, "reason": "not found in graph"})
                    continue

                cutoff_ts = source["timestamp"]
                if cutoff_ts is None:
                    print(f"         ERROR — commit has no timestamp property, skipping.\n")
                    failed.append({"commit_hash": commit_hash, "reason": "missing timestamp"})
                    continue

                print(f"         Cutoff timestamp : {cutoff_ts}")

                # 2. Run CIA traversal
                reached = session.execute_read(
                    run_cia_traversal,
                    commit_hash,
                    cutoff_ts,
                    max_hops,
                )

                print(f"         Nodes reached    : {len(reached)}")

                # 3. Build output payload
                summary = summarise(source, reached)

                output = {
                    "meta": {
                        "commit_hash":      commit_hash,
                        "cutoff_timestamp": cutoff_ts,
                        "max_hops":         max_hops,
                        "neo4j_uri":        NEO4J_URI,
                        "run_at":           datetime.now(timezone.utc).isoformat(),
                    },
                    "source_node":   source,
                    "summary":       summary,
                    "reached_nodes": reached,
                }

                # 4. Save individual result file
                output_path = os.path.join(output_dir, f"cia_{commit_hash[:12]}.json")
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(output, f, indent=2, default=str)

                print(f"Saved to    : {output_path}")
                print(f"By node type: {summary['by_node_type']}")
                print()

                succeeded.append({"commit_hash": commit_hash, "output_path": output_path})

    finally:
        driver.close()

    # 5. Print run summary
    print("=" * 60)
    print(f"[CIA] Done — {len(succeeded)}/{len(commit_hashes)} commits processed successfully.")
    if failed:
        print(f"[CIA] Failed ({len(failed)}):")
        for entry in failed:
            print(f"      {entry['commit_hash']} — {entry['reason']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
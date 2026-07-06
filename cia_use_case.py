"""
Change Impact Analysis (CIA) query runner for software traceability knowledge graph.

Usage:
    python cia_use_case.py

Configure commit_hashes, max_hops, and output_dir at the top of main() before running.

The script:
  1. Looks up each source commit node and reads its insertion timestamp as the cutoff.
  2. Traverses edges where edge.timestamp < cutoff (strict), excluding same-batch
     edges such as commit->codefile and commit->developer at hop 1.
  3. Returns a flat list of reached node IDs (the CIA impact set).
  4. Saves one JSON file per commit to output_dir.
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
    Retrieve the source commit node. Returns id only — the cutoff timestamp
    is supplied separately via commit_cutoffs in main() to avoid drift between
    node.timestamp and edge.timestamp caused by batch insertion timing.
    """
    result = tx.run(
        """
        MATCH (c:TraceabilityNode:Commit {id: $commit_hash})
        RETURN c.id AS id
        LIMIT 1
        """,
        commit_hash=commit_hash,
    )
    record = result.single()
    if record is None:
        return None
    return {"id": record["id"]}


def run_cia_traversal(tx, commit_hash: str, cutoff_ts: str, max_hops: int) -> list[str]:
    """
    Traverse the graph from the source commit with one constraint:

    TEMPORAL: every edge in the path must have timestamp < cutoff_ts (strictly
    less than). This excludes all same-batch edges at hop 1: commit->codefile
    and commit->developer share the commit batch timestamp and are therefore
    excluded. The commit->issue edge is older (the issue existed before the
    commit batch) and is the only valid hop-1 traversal.

    Nodes excluded at hop 1 by the temporal filter can still be reached
    indirectly via older edges at deeper hops (e.g. issue->other_commit->developer),
    which is valid CIA signal.

    Returns a flat list of reached node IDs (impact set).
    """
    query = """
    MATCH (source:TraceabilityNode:Commit {id: $commit_hash})

    // Step 1: unconditionally hop to the parent issue.
    // This edge shares the commit batch timestamp so it cannot pass the
    // temporal filter — we allow it explicitly as the entry point.
    MATCH (source)-[*1..1]-(issue:Issue)

    // Step 2: from the issue, traverse the rest of the graph up to (max_hops - 1)
    // further hops, applying the temporal filter to every edge from here on.
    MATCH path = (issue)-[*0..{remaining_hops}]-(reached)

    WHERE ALL(r IN relationships(path) WHERE r.timestamp < $cutoff_ts)
    AND reached <> source

    RETURN DISTINCT reached.id AS node_id
    ORDER BY node_id ASC
    """
    query = query.replace("{max_hops}", str(max_hops))
    query = query.replace("{remaining_hops}", str(max(0, max_hops - 1)))

    results = tx.run(
        query,
        commit_hash=commit_hash,
        cutoff_ts=cutoff_ts,
    )

    return [record["node_id"] for record in results]


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------

def fetch_impacted_nodes(tx, commit_hash: str, cutoff_ts: str) -> list[str]:
    """
    Retrieve the nodes that are directly connected to the source commit with
    edge.timestamp = cutoff_ts. These are the same-batch nodes (codefiles,
    developer) that the temporal filter blocks at hop 1 during traversal.

    Saving these allows downstream analysis to check whether the enriched
    graph's reachable set eventually reaches any of these directly changed nodes
    via indirect paths — which is the core CIA signal.
    """
    result = tx.run(
        """
        MATCH (source:TraceabilityNode:Commit {id: $commit_hash})-[r]-(impacted)
        WHERE r.timestamp = $cutoff_ts
        RETURN DISTINCT impacted.id AS node_id
        ORDER BY node_id ASC
        """,
        commit_hash=commit_hash,
        cutoff_ts=cutoff_ts,
    )
    return [record["node_id"] for record in result]


def summarise(reached: list[str]) -> dict:
    """Build a minimal summary: total count and flat ID list."""
    return {
        "total_reached": len(reached),
        "reached_ids":   reached,
    }


def analyse(impacted: list[str], reached: list[str]) -> dict:
    """
    Compare the impacted (directly impacted same-batch) nodes against the
    reachable set to compute CIA effectiveness metrics.

    - true_positives  : impacted nodes that were also reached via traversal
    - false_negatives : impacted nodes that were NOT reached (missed impact)
    - false_positives : reached nodes that are not in the impacted set
                        (indirectly reachable but not directly changed)
    - precision : TP / (TP + FP)  — of all reached nodes, how many were directly impacted
    - recall    : TP / (TP + FN)  — of all directly impacted nodes, how many were reached
    - f1        : harmonic mean of precision and recall
    """
    impacted_set = set(impacted)
    reached_set = set(reached)

    tp = impacted_set & reached_set          # directly impacted AND reached
    fn = impacted_set - reached_set          # directly impacted but NOT reached
    fp = reached_set - impacted_set          # reached but not directly impacted

    precision = len(tp) / (len(tp) + len(fp)) if (len(tp) + len(fp)) > 0 else 0.0
    recall    = len(tp) / (len(tp) + len(fn)) if (len(tp) + len(fn)) > 0 else 0.0
    f1        = (2 * precision * recall / (precision + recall)
                 if (precision + recall) > 0 else 0.0)

    return {
        "true_positives":       sorted(tp),
        "false_negatives":      sorted(fn),
        "false_positives":      sorted(fp),
        "true_positive_count":  len(tp),
        "false_negative_count": len(fn),
        "false_positive_count": len(fp),
        "precision":            round(precision, 4),
        "recall":               round(recall, 4),
        "f1_score":             round(f1, 4),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    # ---------------------------------------------------------------------------
    # Configure your run here
    # ---------------------------------------------------------------------------
    # Map each commit hash to its cutoff timestamp.
    # Use the timestamp of the commit->issue edge (the oldest edge in the
    # commit's batch), not the commit node's own timestamp, to avoid
    # node/edge insertion drift.
    # Format: "YYYY-MM-DDTHH:MM:SS.ffffff"
    commit_cutoffs = {                                                                         #non                        qwen                               gpt
        "e9e7d0a287ad95e71f02eef61a190b2c02e3b21b": "2026-06-11T05:28:26.616966", #"2026-06-09T13:30:48.973606", #"2026-06-11T05:28:26.616966", #"2026-06-10T17:34:02.011630",
        "95c7e6d716ae5e96a9fff3b68bbbb2a383f4c073": "2026-06-11T14:49:46.893876", #"2026-06-09T13:35:36.854569", #"2026-06-11T14:49:46.893876", #"2026-06-10T18:28:40.953277",
        "1e2ba9fe9be84f0b5defe4965735eae892fabf7b": "2026-06-11T03:54:53.457032", #"2026-06-09T13:29:44.291513", #"2026-06-11T03:54:53.457032", #"2026-06-10T17:24:39.774887",
        "6ffd1ba9787e4c8ae881663a93cb7958e84e3891": "2026-06-11T05:50:02.372220", #"2026-06-09T13:31:03.876865", #"2026-06-11T05:50:02.372220", #"2026-06-10T17:36:11.797279",
        "7e86ba8c7327f99ca8708494b6d402af4cd0b4ec": "2026-06-11T10:46:02.906379", #"2026-06-09T13:33:13.222182", #"2026-06-11T10:46:02.906379", #"2026-06-10T18:04:42.882924",
        "87016b5f0ce7a895447ee19d3f567f4135cae2a6": "2026-06-11T17:10:02.017657", #"2026-06-09T13:37:12.657278", #"2026-06-11T17:10:02.017657", #"2026-06-10T18:42:37.936939",
        "bd7ddb8fbfedd29711c8f5e466022ecb3810b70a": "2026-06-11T16:12:32.829394", #"2026-06-09T13:36:33.157168", #"2026-06-11T16:12:32.829394", #"2026-06-10T18:36:53.460173"
    }
    commit_hashes = list(commit_cutoffs.keys())
    max_hops   = DEFAULT_MAX_HOPS   # Maximum traversal depth (default: 4)
    output_dir = f"cia_results/qwen{max_hops}"      # Directory where all result files are saved
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

                cutoff_ts = commit_cutoffs.get(commit_hash, "").strip()
                if not cutoff_ts:
                    print(f"         ERROR — no cutoff timestamp configured for this commit, skipping.\n")
                    failed.append({"commit_hash": commit_hash, "reason": "missing cutoff timestamp in commit_cutoffs"})
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

                # 3. Fetch directly impacted (same-batch) nodes
                impacted = session.execute_read(
                    fetch_impacted_nodes,
                    commit_hash,
                    cutoff_ts,
                )
                print(f"         Impacted (same-batch) : {len(impacted)}")

                # 3.5 Analyse: compare impacted nodes against reachable set
                analysis = analyse(impacted, reached)
                print(f"         Precision : {analysis['precision']}  "
                      f"Recall : {analysis['recall']}  "
                      f"F1 : {analysis['f1_score']}")

                # 4. Build output payload
                summary = summarise(reached)

                output = {
                    "meta": {
                        "commit_hash":      commit_hash,
                        "cutoff_timestamp": cutoff_ts,
                        "max_hops":         max_hops,
                        "neo4j_uri":        NEO4J_URI,
                        "run_at":           datetime.now(timezone.utc).isoformat(),
                    },
                    "source_node_id":  commit_hash,
                    "cutoff_source":   "commit_cutoffs (manual)",
                    "total_impacted":    len(impacted),
                    "impacted_node_ids": impacted,
                    "total_reached":    summary["total_reached"],
                    "reached_ids":      summary["reached_ids"],
                    "analysis":         analysis,
                }

                # 4. Save individual result file
                output_path = os.path.join(output_dir, f"cia_{commit_hash[:12]}.json")
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(output, f, indent=2, default=str)

                print(f"         Saved to         : {output_path}")
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
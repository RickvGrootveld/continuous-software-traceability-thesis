"""
Schema validation for LLM-enriched edges.

Fetches every edge in the Neo4j graph where system='LLM' and checks whether
the (source node labels, target node labels) pair is permitted by the
conceptual schema. The relationship type itself is not checked — any label
is accepted as long as the endpoint node types match a valid schema entry.

A valid schema entry is matched when:
  source node labels ⊇ required source labels for that entry
  target node labels ⊇ required target labels for that entry

An edge is valid if it matches at least one schema entry.

Schema (relationship label is variable, node label sets must be supersets):
  (:Issue)         -[*]-> (:Release)
  (:Issue)         -[*]-> (:Issue)
  (:Issue:Feature) -[*]-> (:Issue:Feature)
  (:Issue:Bug)     -[*]-> (:Issue:Feature)
  (:Commit)        -[*]-> (:Issue:Feature)
  (:Commit)        -[*]-> (:Issue:Bug)
  (:Developer)     -[*]-> (:Commit)
  (:Issue)         -[*]-> (:Developer)
  (:Commit)        -[*]-> (:Code)
"""

from neo4j import GraphDatabase
from collections import defaultdict

NEO4J_URI      = "bolt://localhost:7687"
NEO4J_USER     = "neo4j"
NEO4J_PASSWORD = "password"

# ---------------------------------------------------------------------------
# Schema definition
# Each entry is (required_source_labels, required_target_labels, description).
# Node label sets on both sides are treated as supersets:
#   a node with labels {Issue, Bug, TraceabilityNode} satisfies {Issue, Bug}.
# ---------------------------------------------------------------------------

SCHEMA = [
    ({"Issue"},          {"Release"},           "Issue -> Release"),
    ({"Issue"},          {"Issue"},             "Issue -> Issue"),
    ({"Issue", "Feature"},{"Issue", "Feature"}, "Issue:Feature -> Issue:Feature"),
    ({"Issue", "Bug"},   {"Issue", "Feature"},  "Issue:Bug -> Issue:Feature"),
    ({"Commit"},         {"Issue", "Feature"},  "Commit -> Issue:Feature"),
    ({"Commit"},         {"Issue", "Bug"},      "Commit -> Issue:Bug"),
    ({"Developer"},      {"Commit"},            "Developer -> Commit"),
    ({"Issue"},          {"Developer"},         "Issue -> Developer"),
    ({"Commit"},         {"Code"},              "Commit -> Code"),
]


def matches_schema(src_labels, tgt_labels):
    """Returns the list of schema entries that this (src, tgt) label pair
    satisfies. Empty list means the edge violates the schema."""
    src = set(src_labels)
    tgt = set(tgt_labels)
    return [
        desc
        for req_src, req_tgt, desc in SCHEMA
        if req_src <= src and req_tgt <= tgt
    ]


def validate_llm_edges(session):
    result = session.run("""
        MATCH (a)-[r]->(b)
        WHERE r.system = 'LLM'
        RETURN
            a.id          AS src_id,
            labels(a)     AS src_labels,
            type(r)       AS rel_type,
            b.id          AS tgt_id,
            labels(b)     AS tgt_labels,
            r.timestamp   AS timestamp
        ORDER BY src_id, tgt_id
    """)

    valid   = []
    invalid = []

    for r in result:
        src_id     = r["src_id"]
        tgt_id     = r["tgt_id"]
        src_labels = list(r["src_labels"])
        tgt_labels = list(r["tgt_labels"])
        rel_type   = r["rel_type"]
        timestamp  = r["timestamp"]

        matched = matches_schema(src_labels, tgt_labels)
        entry = {
            "src_id":     src_id,
            "src_labels": src_labels,
            "rel_type":   rel_type,
            "tgt_id":     tgt_id,
            "tgt_labels": tgt_labels,
            "timestamp":  timestamp,
            "matched":    matched,
        }
        if matched:
            valid.append(entry)
        else:
            invalid.append(entry)

    return valid, invalid

def print_report(valid, invalid, max_examples=10):
    total = len(valid) + len(invalid)

    precision = len(valid) / total if total > 0 else float("nan")

    print(f"\n{'=' * 60}")
    print(f"  LLM EDGE SCHEMA VALIDATION")
    print(f"{'=' * 60}")
    print(f"  total LLM edges   : {total}")
    print(f"  valid (schema OK) : {len(valid)}")
    print(f"  invalid           : {len(invalid)}")
    print(f"  schema adherence  : {precision:.4f}"
          f"  ({len(valid)}/{total})")

    # --- invalid edges ---
    if invalid:
        print(f"\n  INVALID EDGES ({len(invalid)} total)")
        print(f"  These edges have no matching schema entry for their endpoint types.")
        for edge in invalid[:max_examples]:
            print(f"\n    ({edge['src_id']} {sorted(edge['src_labels'])})"
                  f" -[{edge['rel_type']}]->"
                  f" ({edge['tgt_id']} {sorted(edge['tgt_labels'])})")
        if len(invalid) > max_examples:
            print(f"\n    ... and {len(invalid) - max_examples} more")

    # --- breakdown of invalid edges by (src label set, tgt label set) ---
    if invalid:
        print(f"\n  INVALID EDGE TYPE BREAKDOWN")
        buckets = defaultdict(list)
        for edge in invalid:
            key = (
                tuple(sorted(edge["src_labels"])),
                edge["rel_type"],
                tuple(sorted(edge["tgt_labels"])),
            )
            buckets[key].append(edge)
        for (src_lbls, rel, tgt_lbls), edges in sorted(buckets.items(),
                                                         key=lambda x: -len(x[1])):
            print(f"    {list(src_lbls)} -[{rel}]-> {list(tgt_lbls)} : {len(edges)} edge(s)")

    # --- breakdown of valid edges by matched schema entry ---
    if valid:
        print(f"\n  VALID EDGE BREAKDOWN BY MATCHED SCHEMA ENTRY")
        matched_counts = defaultdict(int)
        for edge in valid:
            for m in edge["matched"]:
                matched_counts[m] += 1
        for desc, cnt in sorted(matched_counts.items(), key=lambda x: -x[1]):
            print(f"    {desc} : {cnt}")

def main():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:
        valid, invalid = validate_llm_edges(session)
        print_report(valid, invalid)
    driver.close()


if __name__ == "__main__":
    main()
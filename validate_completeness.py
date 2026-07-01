"""
Completeness and schema validation: sqlite3 source vs Neo4j knowledge graph,
scoped to records in validate_schema_completeness.

Two full reports are produced:
  ALL            — all nodes/edges in the graph regardless of labels
  TRACEABILITY   — only nodes that also carry the TraceabilityNode label

Node categories:
  TP      ID exists in graph AND required properties present AND mapped values correct
  FN      ID missing from graph entirely
  FP      ID in graph but no matching scoped source record
  INVALID ID found in graph, but required properties missing OR mapped values wrong

Precision      = TP / (TP + FP)
Strict recall  = TP / (TP + FN + INVALID)   [INVALID nodes are not correctly represented]

Schema constraint checks (graph-wide, independent of sqlite source):
  1. Required properties present on all nodes of each type
  2. Commit must have exactly 1 CreatedBy -> Developer  (cardinality: 1)
  3. Commit must change 1..* Code files                 (cardinality: 1..*)
  4. Commit must link to at least 1 Issue via BelongsTo (XOR solves/implements)
  5. Dataset edges must carry a non-null timestamp property

Note: label names and property types are not validated (per requirements).
Note: Code.is_deleted is excluded from value comparison — it is last-write-wins
      via apoc.merge.node across multiple commits, making the expected value ambiguous.
"""

import sqlite3
from neo4j import GraphDatabase

SQLITE_PATH    = "./datasets/validate/lucene.sqlite3"
NEO4J_URI      = "bolt://localhost:7687"
NEO4J_USER     = "neo4j"
NEO4J_PASSWORD = "password"

SOURCE_TABLE_ISSUE      = "issue"
SOURCE_TABLE_CHANGE_SET = "change_set"

# Properties that must be present and non-null on every node of the given type.
# Property types are not checked (per requirements).
REQUIRED_PROPERTIES = {
    "Issue":     ["id", "title", "issue_type", "created_date"],
    "Commit":    ["id", "message", "committed_date"],
    "Developer": ["id", "name"],
    "Code":      ["id", "file_path"],
    "Release":   ["id", "name"],
}


# ---------------------------------------------------------------------------
# Connection / scope
# ---------------------------------------------------------------------------

def get_sqlite_conn():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def build_scope(conn):
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS temp._scope_issue")
    cursor.execute("DROP TABLE IF EXISTS temp._scope_change_set")
    cursor.execute("""
        CREATE TEMP TABLE _scope_issue AS
        SELECT DISTINCT id FROM validate_schema_completeness
        WHERE source_table = ?
    """, (SOURCE_TABLE_ISSUE,))
    cursor.execute("""
        CREATE TEMP TABLE _scope_change_set AS
        SELECT DISTINCT id FROM validate_schema_completeness
        WHERE source_table = ?
    """, (SOURCE_TABLE_CHANGE_SET,))
    conn.commit()
    n_issue = cursor.execute("SELECT COUNT(*) FROM _scope_issue").fetchone()[0]
    n_cs    = cursor.execute("SELECT COUNT(*) FROM _scope_change_set").fetchone()[0]
    print(f"simulation scope: {n_issue} issue records, {n_cs} change_set records")
    if n_issue == 0 and n_cs == 0:
        print("WARNING: scope is empty — check SOURCE_TABLE_ISSUE / SOURCE_TABLE_CHANGE_SET values")


# ---------------------------------------------------------------------------
# Neo4j helpers
# ---------------------------------------------------------------------------

def neo4j_nodes_with_props(session, label, traceability_only):
    """Returns (node_dict, duplicate_ids) for all nodes of the given label.

    node_dict     : {id: props}  — first-seen node for each id value
    duplicate_ids : set of id values that appear on more than one node in the graph

    Duplicates represent incorrect graph state (two physical nodes sharing the
    same logical id) and are flagged as INVALID regardless of property values.
    The first-seen props are kept so normal property validation can still run.
    """
    if traceability_only:
        query = f"MATCH (n:TraceabilityNode:{label}) RETURN n"
    else:
        query = f"MATCH (n:{label}) RETURN n"
    node_dict     = {}
    duplicate_ids = set()
    for r in session.run(query):
        props = dict(r["n"])
        nid   = props.get("id")
        if nid in node_dict:
            duplicate_ids.add(nid)
        else:
            node_dict[nid] = props
    return node_dict, duplicate_ids


def neo4j_edge_pairs(session, rel_type, traceability_only):
    if traceability_only:
        query = (f"MATCH (a:TraceabilityNode)-[r:`{rel_type}`]->(b:TraceabilityNode) "
                 f"RETURN a.id AS src, b.id AS tgt")
    else:
        query = f"MATCH (a)-[r:`{rel_type}`]->(b) RETURN a.id AS src, b.id AS tgt"
    return {(r["src"], r["tgt"]) for r in session.run(query)}


def neo4j_edge_triples(session, rel_types, traceability_only):
    """Returns (src_id, tgt_id, rel_type) triples. None rel_types are skipped —
    they cannot exist as relationship types and are unconditional FNs."""
    triples = set()
    for rel_type in rel_types:
        if rel_type is None:
            continue
        if traceability_only:
            query = (f"MATCH (a:TraceabilityNode)-[r:`{rel_type}`]->(b:TraceabilityNode) "
                     f"RETURN a.id AS src, b.id AS tgt, type(r) AS t")
        else:
            query = (f"MATCH (a)-[r:`{rel_type}`]->(b) "
                     f"RETURN a.id AS src, b.id AS tgt, type(r) AS t")
        for r in session.run(query):
            triples.add((r["src"], r["tgt"], r["t"]))
    return triples


# ---------------------------------------------------------------------------
# Node validation helper
# ---------------------------------------------------------------------------

def validate_node(graph_props, expected_props, required_props):
    """
    Validates a graph node against its expected source values and required
    property list. Property types are not checked.

    Returns:
      missing_required   list of property names that are None or absent
      value_mismatches   list of {property, expected, actual} where values differ
    """
    missing_required = [p for p in required_props if graph_props.get(p) is None]
    value_mismatches = [
        {"property": prop, "expected": exp, "actual": graph_props.get(prop)}
        for prop, exp in expected_props.items()
        if graph_props.get(prop) != exp
    ]
    return missing_required, value_mismatches


# ---------------------------------------------------------------------------
# Per-table checks
# ---------------------------------------------------------------------------

def check_issue(conn, session, traceability_only):
    rows = conn.execute("""
        SELECT i.* FROM issue i JOIN _scope_issue s ON i.issue_id = s.id
    """).fetchall()

    graph_nodes, duplicate_ids = neo4j_nodes_with_props(session, "Issue", traceability_only)
    node_tp = set(); node_fn = set(); node_invalid = []
    source_ids = set()

    for row in rows:
        iid = row["issue_id"]
        source_ids.add(iid)
        if iid not in graph_nodes:
            node_fn.add(iid)
        elif iid in duplicate_ids:
            node_invalid.append({"id": iid, "duplicate": True,
                                 "missing_required": [], "value_mismatches": []})
        else:
            missing, mismatches = validate_node(
                graph_nodes[iid],
                {
                    "title":         row["summary"],
                    "issue_type":    row["type"],
                    "status":        row["status"],
                    "summary":       row["description"],
                    "priority":      row["priority"],
                    "created_date":  row["created_date"],
                    "updated_date":  row["updated_date"],
                    "resolved_date": row["resolved_date"],
                },
                REQUIRED_PROPERTIES["Issue"],
            )
            if missing or mismatches:
                node_invalid.append({"id": iid, "missing_required": missing,
                                     "value_mismatches": mismatches})
            else:
                node_tp.add(iid)

    node_fp = set(graph_nodes.keys()) - source_ids

    expected_edges = {(r["issue_id"], r["assignee"]) for r in rows if r["assignee"] is not None}
    graph_edges    = neo4j_edge_pairs(session, "AssignedTo", traceability_only)

    return {
        "node_tp": node_tp, "node_fn": node_fn, "node_fp": node_fp,
        "node_invalid": node_invalid,
        "edge_tp": expected_edges & graph_edges,
        "edge_fn": expected_edges - graph_edges,
        "edge_fp": graph_edges - expected_edges,
    }


def check_change_set(conn, session, traceability_only):
    rows = conn.execute("""
        SELECT cs.* FROM change_set cs JOIN _scope_change_set s ON cs.commit_hash = s.id
    """).fetchall()

    graph_nodes, duplicate_ids = neo4j_nodes_with_props(session, "Commit", traceability_only)
    node_tp = set(); node_fn = set(); node_invalid = []
    source_ids = set()

    for row in rows:
        chash = row["commit_hash"]
        source_ids.add(chash)
        if chash not in graph_nodes:
            node_fn.add(chash)
        elif chash in duplicate_ids:
            node_invalid.append({"id": chash, "duplicate": True,
                                 "missing_required": [], "value_mismatches": []})
        else:
            missing, mismatches = validate_node(
                graph_nodes[chash],
                {"message": row["message"], "committed_date": row["committed_date"]},
                REQUIRED_PROPERTIES["Commit"],
            )
            if missing or mismatches:
                node_invalid.append({"id": chash, "missing_required": missing,
                                     "value_mismatches": mismatches})
            else:
                node_tp.add(chash)

    node_fp = set(graph_nodes.keys()) - source_ids

    expected_edges = {(r["commit_hash"], r["author"]) for r in rows}
    graph_edges    = neo4j_edge_pairs(session, "CreatedBy", traceability_only)

    return {
        "node_tp": node_tp, "node_fn": node_fn, "node_fp": node_fp,
        "node_invalid": node_invalid,
        "edge_tp": expected_edges & graph_edges,
        "edge_fn": expected_edges - graph_edges,
        "edge_fp": graph_edges - expected_edges,
    }


def check_developer(conn, session, traceability_only):
    # Developer nodes are created from two sources (assignee + author).
    # id == name in both cases, so expected name is the id itself.
    dev_names = {}
    for r in conn.execute("""
        SELECT DISTINCT i.assignee FROM issue i
        JOIN _scope_issue s ON i.issue_id = s.id
        WHERE i.assignee IS NOT NULL
    """).fetchall():
        dev_names[r["assignee"]] = r["assignee"]
    for r in conn.execute("""
        SELECT DISTINCT cs.author FROM change_set cs
        JOIN _scope_change_set s ON cs.commit_hash = s.id
    """).fetchall():
        dev_names[r["author"]] = r["author"]

    graph_nodes, duplicate_ids = neo4j_nodes_with_props(session, "Developer", traceability_only)
    node_tp = set(); node_fn = set(); node_invalid = []

    for dev_id, dev_name in dev_names.items():
        if dev_id not in graph_nodes:
            node_fn.add(dev_id)
        elif dev_id in duplicate_ids:
            node_invalid.append({"id": dev_id, "duplicate": True,
                                 "missing_required": [], "value_mismatches": []})
        else:
            missing, mismatches = validate_node(
                graph_nodes[dev_id],
                {"name": dev_name},
                REQUIRED_PROPERTIES["Developer"],
            )
            if missing or mismatches:
                node_invalid.append({"id": dev_id, "missing_required": missing,
                                     "value_mismatches": mismatches})
            else:
                node_tp.add(dev_id)

    return {
        "node_tp": node_tp, "node_fn": node_fn,
        "node_fp": set(graph_nodes.keys()) - set(dev_names.keys()),
        "node_invalid": node_invalid,
    }


def check_code_change(conn, session, traceability_only):
    rows = conn.execute("""
        SELECT cc.* FROM code_change cc
        JOIN _scope_change_set s ON cc.commit_hash = s.id
    """).fetchall()

    # is_deleted is intentionally excluded from value comparison: a file may
    # appear in multiple commits and the final value depends on processing order
    # (last-write-wins via apoc.merge.node), making the expected value ambiguous.
    source_ids  = {r["file_path"] for r in rows}
    graph_nodes, duplicate_ids = neo4j_nodes_with_props(session, "Code", traceability_only)
    node_tp = set(); node_fn = set(); node_invalid = []

    for fp in source_ids:
        if fp not in graph_nodes:
            node_fn.add(fp)
        elif fp in duplicate_ids:
            node_invalid.append({"id": fp, "duplicate": True,
                                 "missing_required": [], "value_mismatches": []})
        else:
            missing, mismatches = validate_node(
                graph_nodes[fp],
                {"file_path": fp},
                REQUIRED_PROPERTIES["Code"],
            )
            if missing or mismatches:
                node_invalid.append({"id": fp, "missing_required": missing,
                                     "value_mismatches": mismatches})
            else:
                node_tp.add(fp)

    node_fp = set(graph_nodes.keys()) - source_ids

    change_types   = {r["change_type"] for r in rows}
    expected_edges = {(r["commit_hash"], r["file_path"], r["change_type"]) for r in rows}
    graph_edges    = neo4j_edge_triples(session, change_types, traceability_only)

    return {
        "node_tp": node_tp, "node_fn": node_fn, "node_fp": node_fp,
        "node_invalid": node_invalid,
        "edge_tp": expected_edges & graph_edges,
        "edge_fn": expected_edges - graph_edges,
        "edge_fp": graph_edges - expected_edges,
    }


def check_issue_link(conn, session, traceability_only):
    rows = conn.execute("""
        SELECT il.* FROM issue_link il
        JOIN _scope_issue s ON il.source_issue_id = s.id
    """).fetchall()

    outward_labels = {r["outward_label"] for r in rows}
    expected_edges = {(r["source_issue_id"], r["target_issue_id"], r["outward_label"])
                      for r in rows}
    graph_edges = neo4j_edge_triples(session, outward_labels, traceability_only)

    return {
        "total_source_rows": len(rows),
        "edge_tp": expected_edges & graph_edges,
        "edge_fn": expected_edges - graph_edges,
        "edge_fp": graph_edges - expected_edges,
    }


def check_fix_version(conn, session, traceability_only):
    rows = conn.execute("""
        SELECT ifv.* FROM issue_fix_version ifv
        JOIN _scope_issue s ON ifv.issue_id = s.id
    """).fetchall()

    release_ids = {r["fix_version"] for r in rows}
    graph_nodes, duplicate_ids = neo4j_nodes_with_props(session, "Release", traceability_only)
    node_tp = set(); node_fn = set(); node_invalid = []

    for rv in release_ids:
        if rv not in graph_nodes:
            node_fn.add(rv)
        elif rv in duplicate_ids:
            node_invalid.append({"id": rv, "duplicate": True,
                                 "missing_required": [], "value_mismatches": []})
        else:
            missing, mismatches = validate_node(
                graph_nodes[rv],
                {"name": rv},
                REQUIRED_PROPERTIES["Release"],
            )
            if missing or mismatches:
                node_invalid.append({"id": rv, "missing_required": missing,
                                     "value_mismatches": mismatches})
            else:
                node_tp.add(rv)

    node_fp = set(graph_nodes.keys()) - release_ids

    expected_edges = {(r["issue_id"], r["fix_version"]) for r in rows}
    graph_edges    = neo4j_edge_pairs(session, "FixedIn", traceability_only)

    return {
        "node_tp": node_tp, "node_fn": node_fn, "node_fp": node_fp,
        "node_invalid": node_invalid,
        "edge_tp": expected_edges & graph_edges,
        "edge_fn": expected_edges - graph_edges,
        "edge_fp": graph_edges - expected_edges,
    }


def check_change_set_link(conn, session, traceability_only):
    rows = conn.execute("""
        SELECT csl.* FROM change_set_link csl
        JOIN _scope_change_set s ON csl.commit_hash = s.id
    """).fetchall()

    expected_edges = {(r["commit_hash"], r["issue_id"]) for r in rows}
    graph_edges    = neo4j_edge_pairs(session, "BelongsTo", traceability_only)

    return {
        "total_source_rows": len(rows),
        "edge_tp": expected_edges & graph_edges,
        "edge_fn": expected_edges - graph_edges,
        "edge_fp": graph_edges - expected_edges,
    }


# ---------------------------------------------------------------------------
# Schema constraint check (graph-wide, independent of sqlite source)
# ---------------------------------------------------------------------------

def check_schema_constraints(session, traceability_only):
    """
    Validates structural constraints from the conceptual schema against the
    full graph. These checks are independent of the sqlite source — they test
    whether the graph itself is internally consistent with the schema.

    Structural rules checked (from the schema diagram):
      - Every node of each type must have its required properties non-null
      - Commit -[CreatedBy]-> Developer : exactly 1  (cardinality: 1)
      - Commit -[*]-> Code              : 1 or more  (cardinality: 1..*)
      - Commit -[BelongsTo]-> Issue     : 1 or more  (XOR solves Bug / implements Feature)
      - All dataset edges must carry a non-null timestamp property
    """
    tn = ":TraceabilityNode" if traceability_only else ""
    violations = {}

    # 0. Duplicate nodes — multiple physical nodes sharing the same id property
    for label in REQUIRED_PROPERTIES:
        result = session.run(f"""
            MATCH (n{tn}:{label})
            WITH n.id AS id, count(*) AS cnt
            WHERE cnt > 1
            RETURN id, cnt
        """)
        dups = [{"id": r["id"], "count": r["cnt"]} for r in result]
        if dups:
            violations[f"{label.lower()}_duplicate_ids"] = dups

    # 1. Required property violations across all nodes in the graph
    for label, req_props in REQUIRED_PROPERTIES.items():
        null_checks  = " OR ".join([f"n.{p} IS NULL" for p in req_props])
        prop_returns = ", ".join([f"n.{p} AS {p}" for p in req_props])
        result = session.run(f"""
            MATCH (n{tn}:{label})
            WHERE {null_checks}
            RETURN {prop_returns}
        """)
        bad = []
        for r in result:
            null_props = [p for p in req_props if r[p] is None]
            bad.append({"id": r["id"], "missing": null_props})
        if bad:
            violations[f"{label.lower()}_missing_required_props"] = bad

    # 2. Commit -> Developer cardinality: exactly 1
    result = session.run(f"""
        MATCH (c{tn}:Commit)
        WITH c, size([(c)-[:CreatedBy]->() | 1]) AS cnt
        WHERE cnt <> 1
        RETURN c.id AS id, cnt AS createdby_count
    """)
    bad = [{"id": r["id"], "CreatedBy_count": r["createdby_count"]} for r in result]
    if bad:
        violations["commit_createdby_not_exactly_1"] = bad

    # 3. Commit -> Code cardinality: 1..*
    result = session.run(f"""
        MATCH (c{tn}:Commit)
        WITH c, size([(c)-->(:Code) | 1]) AS cnt
        WHERE cnt = 0
        RETURN c.id AS id
    """)
    bad = [r["id"] for r in result]
    if bad:
        violations["commit_no_code_changes"] = bad

    # 4. Commit -> Issue cardinality: at least 1 (XOR solves Bug / implements Feature,
    #    mapped as BelongsTo in the graph)
    result = session.run(f"""
        MATCH (c{tn}:Commit)
        WITH c, size([(c)-[:BelongsTo]->() | 1]) AS cnt
        WHERE cnt = 0
        RETURN c.id AS id
    """)
    bad = [r["id"] for r in result]
    if bad:
        violations["commit_no_issue_link"] = bad

    # 5. All dataset edges must carry a non-null timestamp
    result = session.run(f"""
        MATCH (a{tn})-[r]->(b)
        WHERE r.system = 'dataset' AND r.timestamp IS NULL
        RETURN a.id AS src, b.id AS tgt, type(r) AS rel_type
        LIMIT 200
    """)
    bad = [{"src": r["src"], "tgt": r["tgt"], "rel_type": r["rel_type"]} for r in result]
    if bad:
        violations["dataset_edges_missing_timestamp"] = bad

    return violations


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _pr(tp, fp, fn, invalid=None):
    """Computes precision and strict recall.
    Strict recall treats INVALID nodes as FN (they are not correctly represented)."""
    n_tp  = len(tp)
    n_fp  = len(fp)
    n_fn  = len(fn)
    n_inv = len(invalid) if invalid is not None else 0
    precision     = n_tp / (n_tp + n_fp)           if (n_tp + n_fp) > 0           else float("nan")
    strict_recall = n_tp / (n_tp + n_fn + n_inv)   if (n_tp + n_fn + n_inv) > 0   else float("nan")
    return n_tp, n_fp, n_fn, n_inv, precision, strict_recall


def print_report(label, results, schema_violations, max_examples=5):
    print(f"\n{'=' * 60}")
    print(f"  REPORT — {label}")
    print(f"{'=' * 60}")

    for name, result in results.items():
        print(f"\n  [{name}]")
        inv = result.get("node_invalid", [])

        if "node_tp" in result:
            tp, fp, fn, n_inv, prec, rec = _pr(
                result["node_tp"], result["node_fp"], result["node_fn"], inv)
            print(f"    nodes  TP={tp}  FN={fn}  FP={fp}  INVALID={n_inv}"
                  f"  |  precision={prec:.4f}  strict_recall={rec:.4f}")
            if result["node_fn"]:
                print(f"      FN examples: {list(result['node_fn'])[:max_examples]}")
            if result["node_fp"]:
                print(f"      FP examples: {list(result['node_fp'])[:max_examples]}")
            if inv:
                print(f"      INVALID ({len(inv)} total):")
                for entry in inv[:max_examples]:
                    print(f"        id={entry['id']}")
                    if entry.get("duplicate"):
                        print(f"          reason                  : duplicate nodes share this id in the graph")
                    if entry["missing_required"]:
                        print(f"          missing required props  : {entry['missing_required']}")
                    for m in entry["value_mismatches"][:5]:
                        print(f"          value mismatch          : {m['property']}: "
                              f"expected={repr(m['expected'])}  actual={repr(m['actual'])}")
                if len(inv) > max_examples:
                    print(f"        ... and {len(inv) - max_examples} more")

        if "edge_tp" in result:
            tp, fp, fn, _, prec, rec = _pr(
                result["edge_tp"], result["edge_fp"], result["edge_fn"])
            print(f"    edges  TP={tp}  FN={fn}  FP={fp}"
                  f"  |  precision={prec:.4f}  recall={rec:.4f}")
            if result["edge_fn"]:
                print(f"      FN examples: {list(result['edge_fn'])[:max_examples]}")
            if result["edge_fp"]:
                print(f"      FP examples: {list(result['edge_fp'])[:max_examples]}")

    # Aggregate across all checks
    agg = {k: set() for k in ["node_tp", "node_fn", "node_fp",
                               "edge_tp", "edge_fn", "edge_fp"]}
    agg_invalid = []
    for result in results.values():
        for k in agg:
            if k in result:
                agg[k] |= result[k]
        agg_invalid.extend(result.get("node_invalid", []))

    print(f"\n  [AGGREGATE]")
    tp, fp, fn, n_inv, prec, rec = _pr(
        agg["node_tp"], agg["node_fp"], agg["node_fn"], agg_invalid)
    print(f"    nodes  TP={tp}  FN={fn}  FP={fp}  INVALID={n_inv}"
          f"  |  precision={prec:.4f}  strict_recall={rec:.4f}")
    tp, fp, fn, _, prec, rec = _pr(agg["edge_tp"], agg["edge_fp"], agg["edge_fn"])
    print(f"    edges  TP={tp}  FN={fn}  FP={fp}"
          f"  |  precision={prec:.4f}  recall={rec:.4f}")

    # Schema constraint violations
    print(f"\n  [SCHEMA CONSTRAINT VIOLATIONS]")
    if schema_violations:
        for vtype, items in schema_violations.items():
            print(f"    {vtype}: {len(items)} violation(s)")
            for item in items[:max_examples]:
                print(f"      {item}")
            if len(items) > max_examples:
                print(f"      ... and {len(items) - max_examples} more")
    else:
        print(f"    none")


def run_all_checks(conn, session, traceability_only):
    return {
        "issue":           check_issue(conn, session, traceability_only),
        "change_set":      check_change_set(conn, session, traceability_only),
        "developer":       check_developer(conn, session, traceability_only),
        "code_change":     check_code_change(conn, session, traceability_only),
        "issue_link":      check_issue_link(conn, session, traceability_only),
        "fix_version":     check_fix_version(conn, session, traceability_only),
        "change_set_link": check_change_set_link(conn, session, traceability_only),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    conn = get_sqlite_conn()
    build_scope(conn)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:
        print_report(
            "ALL NODES (including non-TraceabilityNode)",
            run_all_checks(conn, session, traceability_only=False),
            check_schema_constraints(session, traceability_only=False),
        )
        print_report(
            "TRACEABILITY NODES ONLY (TraceabilityNode label required)",
            run_all_checks(conn, session, traceability_only=True),
            check_schema_constraints(session, traceability_only=True),
        )

    driver.close()
    conn.close()


if __name__ == "__main__":
    main()
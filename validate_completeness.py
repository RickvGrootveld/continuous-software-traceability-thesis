"""
Completeness validation: compares sqlite3 source rows against the Neo4j
knowledge graph they were mapped into, using the mapping logic from
process_issue / process_change_set.

Scope: process_issue/process_change_set are only ever called for records
selected by the simulation (issue_commit_events_simulation). So completeness
here means "every record the simulation fed into the pipeline made it into
the graph correctly" - not "every row in issue/change_set is in the graph".
Secondary tables (issue_link, issue_fix_version, code_change, change_set_link)
are scoped the same way, since the mapping code only pulls those rows for
the specific issue_id/commit_hash being processed.

Adjust SOURCE_TABLE_ISSUE / SOURCE_TABLE_CHANGE_SET below if the literal
values stored in issue_commit_events_simulation.source_table differ.
"""

import sqlite3
from neo4j import GraphDatabase

SQLITE_PATH = "./datasets/validate/lucene.sqlite3"
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password"

SOURCE_TABLE_ISSUE = "issue"
SOURCE_TABLE_CHANGE_SET = "change_set"


def get_sqlite_conn():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def build_scope(conn):
    """Materializes the simulation scope as temp tables, so every later
    query can join against it instead of passing large IN (...) lists."""
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS temp._scope_issue")
    cursor.execute("DROP TABLE IF EXISTS temp._scope_change_set")
    cursor.execute("""
        CREATE TEMP TABLE _scope_issue AS
        SELECT DISTINCT id FROM issue_commit_events_simulation
        WHERE source_table = ?
    """, (SOURCE_TABLE_ISSUE,))
    cursor.execute("""
        CREATE TEMP TABLE _scope_change_set AS
        SELECT DISTINCT id FROM issue_commit_events_simulation
        WHERE source_table = ?
    """, (SOURCE_TABLE_CHANGE_SET,))
    conn.commit()

    n_issue = cursor.execute("SELECT COUNT(*) FROM _scope_issue").fetchone()[0]
    n_cs = cursor.execute("SELECT COUNT(*) FROM _scope_change_set").fetchone()[0]
    print(f"simulation scope: {n_issue} issue records, {n_cs} change_set records")
    if n_issue == 0 and n_cs == 0:
        print("WARNING: scope is empty - check SOURCE_TABLE_ISSUE/SOURCE_TABLE_CHANGE_SET values")


def check_issue_completeness(conn, session):
    rows = conn.execute("""
        SELECT i.* FROM issue i
        JOIN _scope_issue s ON i.issue_id = s.id
    """).fetchall()

    missing_nodes = []
    mismatches = []
    missing_assignee_edges = []

    for issue in rows:
        result = session.run(
            "MATCH (n:Issue {id: $id}) RETURN n", id=issue["issue_id"]
        ).single()

        if result is None:
            missing_nodes.append(issue["issue_id"])
            continue

        node = result["n"]
        expected = {
            "title": issue["summary"],
            "issue_type": issue["type"],
            "status": issue["status"],
            "summary": issue["description"],
            "priority": issue["priority"],
            "created_date": issue["created_date"],
            "updated_date": issue["updated_date"],
            "resolved_date": issue["resolved_date"],
        }
        for prop, expected_val in expected.items():
            if node.get(prop) != expected_val:
                mismatches.append({
                    "issue_id": issue["issue_id"],
                    "property": prop,
                    "expected": expected_val,
                    "actual": node.get(prop),
                })

        if issue["assignee"] is not None:
            edge = session.run(
                """MATCH (i:Issue {id: $iid})-[r:AssignedTo]->(d:Developer {id: $did})
                   RETURN r""",
                iid=issue["issue_id"], did=issue["assignee"],
            ).single()
            if edge is None:
                missing_assignee_edges.append(issue["issue_id"])

    return {
        "total_source_rows": len(rows),
        "missing_nodes": missing_nodes,
        "property_mismatches": mismatches,
        "missing_assignee_edges": missing_assignee_edges,
    }


def check_change_set_completeness(conn, session):
    rows = conn.execute("""
        SELECT cs.* FROM change_set cs
        JOIN _scope_change_set s ON cs.commit_hash = s.id
    """).fetchall()

    missing_nodes = []
    mismatches = []
    missing_author_edges = []

    for cs in rows:
        result = session.run(
            "MATCH (n:Commit {id: $id}) RETURN n", id=cs["commit_hash"]
        ).single()

        if result is None:
            missing_nodes.append(cs["commit_hash"])
            continue

        node = result["n"]
        expected = {
            "message": cs["message"],
            "committed_date": cs["committed_date"],
        }
        for prop, expected_val in expected.items():
            if node.get(prop) != expected_val:
                mismatches.append({
                    "commit_hash": cs["commit_hash"],
                    "property": prop,
                    "expected": expected_val,
                    "actual": node.get(prop),
                })

        edge = session.run(
            """MATCH (c:Commit {id: $cid})-[r:CreatedBy]->(d:Developer {id: $did})
               RETURN r""",
            cid=cs["commit_hash"], did=cs["author"],
        ).single()
        if edge is None:
            missing_author_edges.append(cs["commit_hash"])

    return {
        "total_source_rows": len(rows),
        "missing_nodes": missing_nodes,
        "property_mismatches": mismatches,
        "missing_author_edges": missing_author_edges,
    }


def check_code_change_completeness(conn, session):
    # scoped via change_set, since process_change_set only pulls code_change
    # rows for the commit_hash currently being processed
    rows = conn.execute("""
        SELECT cc.* FROM code_change cc
        JOIN _scope_change_set s ON cc.commit_hash = s.id
    """).fetchall()

    missing_nodes = []
    missing_edges = []

    for cc in rows:
        node_result = session.run(
            "MATCH (n:Code {id: $id}) RETURN n", id=cc["file_path"]
        ).single()
        if node_result is None:
            missing_nodes.append(cc["file_path"])

        edge_result = session.run(
            f"""MATCH (c:Commit {{id: $cid}})-[r:`{cc['change_type']}`]->(f:Code {{id: $fid}})
                RETURN r""",
            cid=cc["commit_hash"], fid=cc["file_path"],
        ).single()
        if edge_result is None:
            missing_edges.append((cc["commit_hash"], cc["file_path"], cc["change_type"]))

    return {
        "total_source_rows": len(rows),
        "missing_nodes": missing_nodes,
        "missing_edges": missing_edges,
    }


def check_issue_link_completeness(conn, session):
    # scoped via issue, since process_issue only pulls issue_link rows
    # WHERE source_issue_id = the issue currently being processed
    rows = conn.execute("""
        SELECT il.* FROM issue_link il
        JOIN _scope_issue s ON il.source_issue_id = s.id
    """).fetchall()

    missing_edges = []
    for link in rows:
        result = session.run(
            f"""MATCH (s:Issue {{id: $sid}})-[r:`{link['outward_label']}`]->(t:Issue {{id: $tid}})
                RETURN r""",
            sid=link["source_issue_id"], tid=link["target_issue_id"],
        ).single()
        if result is None:
            missing_edges.append((link["source_issue_id"], link["target_issue_id"], link["outward_label"]))

    return {
        "total_source_rows": len(rows),
        "missing_edges": missing_edges,
    }


def check_fix_version_completeness(conn, session):
    # scoped via issue, same reasoning as issue_link
    rows = conn.execute("""
        SELECT ifv.* FROM issue_fix_version ifv
        JOIN _scope_issue s ON ifv.issue_id = s.id
    """).fetchall()

    missing_nodes = []
    missing_edges = []
    for ifv in rows:
        node_result = session.run(
            "MATCH (n:Release {id: $id}) RETURN n", id=ifv["fix_version"]
        ).single()
        if node_result is None:
            missing_nodes.append(ifv["fix_version"])

        edge_result = session.run(
            """MATCH (i:Issue {id: $iid})-[r:FixedIn]->(rel:Release {id: $rid})
               RETURN r""",
            iid=ifv["issue_id"], rid=ifv["fix_version"],
        ).single()
        if edge_result is None:
            missing_edges.append((ifv["issue_id"], ifv["fix_version"]))

    return {
        "total_source_rows": len(rows),
        "missing_nodes": missing_nodes,
        "missing_edges": missing_edges,
    }


def check_change_set_link_completeness(conn, session):
    # scoped via change_set, since process_change_set only pulls
    # change_set_link rows for the commit_hash being processed
    rows = conn.execute("""
        SELECT csl.* FROM change_set_link csl
        JOIN _scope_change_set s ON csl.commit_hash = s.id
    """).fetchall()

    missing_edges = []
    for link in rows:
        result = session.run(
            """MATCH (c:Commit {id: $cid})-[r:BelongsTo]->(i:Issue {id: $iid})
               RETURN r""",
            cid=link["commit_hash"], iid=link["issue_id"],
        ).single()
        if result is None:
            missing_edges.append((link["commit_hash"], link["issue_id"]))

    return {
        "total_source_rows": len(rows),
        "missing_edges": missing_edges,
    }


def print_report(name, result, max_examples=10):
    print(f"\n=== {name} ===")
    print(f"source rows in scope: {result['total_source_rows']}")
    for key, value in result.items():
        if key == "total_source_rows":
            continue
        print(f"{key}: {len(value)}")
        if 0 < len(value) <= max_examples:
            for item in value:
                print(f"  {item}")
        elif len(value) > max_examples:
            print(f"  (showing first {max_examples})")
            for item in value[:max_examples]:
                print(f"  {item}")


def main():
    conn = get_sqlite_conn()
    build_scope(conn)

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:
        print_report("issue", check_issue_completeness(conn, session))
        print_report("change_set", check_change_set_completeness(conn, session))
        print_report("code_change", check_code_change_completeness(conn, session))
        print_report("issue_link", check_issue_link_completeness(conn, session))
        print_report("issue_fix_version", check_fix_version_completeness(conn, session))
        print_report("change_set_link", check_change_set_link_completeness(conn, session))
    driver.close()
    conn.close()


if __name__ == "__main__":
    main()

"""
This file converts the dataset entities into the entities of the schema in the graph.
"""

def process_issue(conn, issue_id, timestamp):
    """
    Converts the issues into the right specialization according to the schema. 
    Also the developer and release entities are created.
    """
    cursor = conn.cursor()
    nodes = []
    edges = []

    # --- issue ---
    cursor.execute("""
        SELECT * FROM issue WHERE issue_id = ?
    """, (issue_id,))
    issue = cursor.fetchone()
    issue_type = issue["type"]
    if issue_type == "Bug": 
        schema_issue_type = ["TraceabilityNode", "Issue", "Bug"] 
    else: 
        schema_issue_type = ["TraceabilityNode", "Issue", "Feature"]

    
    nodes.append({
        "type": schema_issue_type,
        "id": issue["issue_id"],
        "properties": {
            "id": issue["issue_id"],
            "embedding": None,
            "title": issue["summary"],
            "type": issue_type,
            "status": issue["status"],
            "summary": issue["description"],
            "priority": issue["priority"],
            "created_date": issue["created_date"],
            "updated_date": issue["updated_date"],
            "resolved_date": issue["resolved_date"]
        }
    })

    # Only create and link the developer if it is in the table
    if issue["assignee"] is not None:
        nodes.append({
            "type": ["TraceabilityNode", "Developer"],
            "id": issue["assignee"],
            "properties": {
                "id": issue["assignee"],
                "embedding": None,
                "name": issue["assignee"]
            }
        })
        edges.append({
            "source_type": schema_issue_type,
            "source_id": issue["issue_id"],
            "target_type": ["TraceabilityNode", "Developer"],
            "target_id": issue["assignee"],
            "label": "AssignedTo",
            "properties": {
                "timestamp": timestamp,
                "system": "dataset"
            }
        })

    # --- issue_link ---
    cursor.execute("""
        SELECT 
            il.source_issue_id,
            il.target_issue_id,
            il.outward_label,
            i.type AS target_issue_type
        FROM issue_link il
        JOIN issue i ON il.target_issue_id = i.issue_id
        WHERE il.source_issue_id = ?
    """, (issue_id,))

    for link in cursor.fetchall():
        target_id = link["target_issue_id"]

        # Extract the dynamic type
        target_type = ["TraceabilityNode", "Issue", "Bug"] if link["issue_type"] == "Bug" else ["TraceabilityNode", "Issue", "Feature"]

        edges.append({
            "source_type": schema_issue_type,
            "source_id": link['source_issue_id'],
            "target_type": target_type,  # Dynamically assigned via JOIN!
            "target_id": target_id,
            "label": link["outward_label"],
            "properties": {
                "timestamp": timestamp,
                "system": "dataset"
            }
        })

    # --- issue_fix_version ---
    cursor.execute("""
        SELECT * FROM issue_fix_version 
        WHERE issue_id = ?
    """, (issue_id,))
    for ifv in cursor.fetchall():
        nodes.append({
            "type": ["TraceabilityNode", "Release"],
            "id": ifv["fix_version"],
            "properties": {
                "id": ifv["fix_version"],
                "embedding": None,
                "name": ifv["fix_version"]
            }
        })
        edges.append({
            "source_type": schema_issue_type,
            "source_id": issue["issue_id"],
            "target_type": ["TraceabilityNode", "Release"],
            "target_id": ifv['fix_version'],
            "label": "FixedIn",
            "properties": {
                "timestamp": timestamp,
                "system": "dataset"
            }
        })

    return {
        "nodes": nodes,
        "edges": edges
    }

def process_change_set(conn, commit_hash, timestamp):
    """
    Converts the change_set records in the dataset into commits.
    Also creates the developers and files that are connected to the change set.
    """
    cursor = conn.cursor()

    nodes = []
    edges = []

    # --- change_set ---
    cursor.execute("""
        SELECT * FROM change_set 
        WHERE commit_hash = ?
    """, (commit_hash,))
    cs = cursor.fetchone()

    nodes.append({
        "type": ["TraceabilityNode", "Commit"],
        "id": cs["commit_hash"],
        "properties": {
            "id": cs["commit_hash"],
            "embedding": None,
            "message": cs["message"],
            "committed_date": cs["committed_date"]
        }
    })

    nodes.append({
        "type": ["TraceabilityNode", "Developer"],
        "id": cs["author"],
        "properties": {
            "id": cs["author"],
            "embedding": None,
            "name": cs["author"]
        }
    })
    edges.append({
        "source_type": ["TraceabilityNode", "Commit"],
        "source_id": commit_hash,
        "target_type": ["TraceabilityNode", "Developer"],
        "target_id": cs['author'],
        "label": "CreatedBy",
        "properties": {
            "timestamp": timestamp,
            "system": "dataset"
        }
    })

    # --- change_set_link ---
    cursor.execute("""
        SELECT 
            csl.issue_id,
            i.type AS issue_type
        FROM change_set_link csl
        JOIN issue i ON csl.issue_id = i.issue_id
        WHERE csl.commit_hash = ?
    """, (commit_hash,))
    for link in cursor.fetchall():
        issue_id = link["issue_id"]

        # 2. Grab the dynamic type
        target_type = ["TraceabilityNode", "Issue", "Bug"] if link["issue_type"] == "Bug" else ["TraceabilityNode", "Issue", "Feature"]

        edges.append({
            "source_type": ["TraceabilityNode", "Commit"],
            "source_id": commit_hash,
            "target_type": target_type,  # Dynamically assigned now!
            "target_id": issue_id,
            "label": "BelongsTo",
            "properties": {
                "timestamp": timestamp,
                "system": "dataset"
            }
        })

    # --- code_change ---
    cursor.execute("""
        SELECT * FROM code_change 
        WHERE commit_hash = ?
    """, (commit_hash,))
    for cc in cursor.fetchall():
        nodes.append({
            "type": ["TraceabilityNode", "Code"],
            "id": cc["file_path"],
            "properties": {
                "id": cc["file_path"],
                "embedding": None,
                "file_path": cc["file_path"],
                "is_deleted": cc["is_deleted"]
            }
        })

        # Save the link between the code and commit
        edges.append({
            "source_type": ["TraceabilityNode", "Commit"],
            "source_id": commit_hash,
            "target_type": ["TraceabilityNode", "Code"],
            "target_id": cc['file_path'],
            "label": cc["change_type"],
            "properties": {
                "timestamp": timestamp,
                "system": "dataset"
            }
        })

    return {
        "nodes": nodes,
        "edges": edges
    }
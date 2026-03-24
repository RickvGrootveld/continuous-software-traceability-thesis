# -------------------------------
# Extract events from the database
# -------------------------------


def get_timeline(conn):
    """
    Applies ASC ordering to make sure all the events in the dataset are
    in chronological order.
    """
    cursor = conn.cursor()

    cursor.execute("""
        SELECT source_table, id, created_date
        FROM issue_commit_chronological
        ORDER BY created_date ASC
    """)

    return cursor.fetchall()

def process_issue(conn, issue_id, timestamp):
    cursor = conn.cursor()
    nodes = []
    edges = []

    # --- issue ---
    cursor.execute("""
        SELECT * FROM issue WHERE issue_id = ?
    """, (issue_id,))
    issue = cursor.fetchone()

    #case issue["type"]:
    #    1: issue_type = "Bug"
    #    2: issue_type = "Improvement"
    #    3: issue_type = "New Feature"
    #    4: issue_type = "Task"
    #    5: issue_type = "Sub-task"
    #    6: issue_type = "Epic"
    #    7: issue_type = "Story"
    #    _ : issue_type = "Unknown"
    nodes.append({
        "type": "Issue",
        "id": issue["issue_id"],
        "properties": {
            "title": issue["summary"],
            "status": issue["status"],
            "description": issue["description"],
            "created_date": issue["created_date"],
            "updated_date": issue["updated_date"],
            "resolved_date": issue["resolved_date"]
        }
    })

    # Only create and link the developer if it is in the table
    if issue["assignee"] is not None:
        nodes.append({
            "type": "Developer",
            "id": issue["assignee"],
            "properties": {
                "name": issue["assignee"]
            }
        })
        edges.append({
            "source": f"Issue:{issue_id}",
            "target": f"Developer:{issue['assignee']}",
            "label": "AssignedTo",
            "properties": {
                "timestamp": timestamp
            }
        })

    # --- issue_link ---
    cursor.execute("""
        SELECT * FROM issue_link 
        WHERE source_issue_id = ?
    """, (issue_id,))
    for link in cursor.fetchall():
        edges.append({
            "source": f"Issue:{link['source_issue_id']}",
            "target": f"Issue:{link['target_issue_id']}",
            "label": link["outward_label"],
            "properties": {
                "timestamp": timestamp
            }
        })

    # --- issue_fix_version ---
    cursor.execute("""
        SELECT * FROM issue_fix_version 
        WHERE issue_id = ?
    """, (issue_id,))
    for ifv in cursor.fetchall():
        nodes.append({
            "type": "Release",
            "id": ifv["fix_version"],
            "properties": {
                "name": ifv["fix_version"]
            }
        })
        edges.append({
            "source": f"Issue:{issue_id}",
            "target": f"Release:{ifv['fix_version']}",
            "label": "FixedIn",
            "properties": {
                "timestamp": timestamp
            }
        })

    events = {
        "nodes": nodes,
        "edges": edges
    }

    return events

def process_change_set(conn, commit_hash, timestamp):
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
        "type": "Commit",
        "id": cs["commit_hash"],
        "properties": {
            "message": cs["message"],
            "committed_date": cs["committed_date"]
        }
    })

    nodes.append({
        "type": "Developer",
        "id": cs["author"],
        "properties": {
            "name": cs["author"]
        }
    })
    edges.append({
        "source": f"Commit:{commit_hash}",
        "target": f"Developer:{cs['author']}",
        "label": "CreatedBy",
        "properties": {
            "timestamp": timestamp
        }
    })

    # --- change_set_link ---
    cursor.execute("""
        SELECT * FROM change_set_link 
        WHERE commit_hash = ?
    """, (commit_hash,))
    for link in cursor.fetchall():
        issue_id = link["issue_id"]

        edges.append({
            "source": f"Commit:{commit_hash}",
            "target": f"Issue:{issue_id}",
            "label": "BelongsTo",
            "properties": {
                "timestamp": timestamp
            }
        })

    # --- code_change ---
    cursor.execute("""
        SELECT * FROM code_change 
        WHERE commit_hash = ?
    """, (commit_hash,))
    for cc in cursor.fetchall():
        nodes.append({
            "type": "Code",
            "id": cc["file_path"],
            "properties": {
                "file_path": cc["file_path"],
                "is_deleted": cc["is_deleted"]
            }
        })

        # Save the link between the code and commit
        edges.append({
            "source": f"Commit:{commit_hash}",
            "target": f"Code:{cc['file_path']}",
            "label": cc["change_type"],
            "properties": {
                "timestamp": timestamp
            }
        })

    events = {
        "nodes": nodes,
        "edges": edges
    }

    return events
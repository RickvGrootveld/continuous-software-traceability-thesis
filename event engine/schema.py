


# -------------------------------
# Knowledge graph schema
# -------------------------------
requirement = {
    "id": None,
    "description": None,
}

commit = {
    "title": None,
    "summary": None,
    "commit_hash": None,
}

issue = {
    "title": None,
    "status": None,  
    "description": None,
    "created": None,
    "updated": None,
    "resolved": None,
}

developer = {
    "id": None,
    "name": None,
}



# -------------------------------
# Translation function 
# -------------------------------
def map_issue_type(issue_type: str) -> str:
    """"
    Helper function for translate_issue_aggregate to map issue types to the
    correct schema entity (bug, feature, or task).
    """
    if issue_type.lower() == "bug":
        return "bug"
    elif issue_type.lower() == "feature":
        return "feature"
    elif issue_type.lower() == "task":
        return "task"
    return "issue"

def translate_issue_aggregate(agg: dict) -> dict:
    issue = agg["issue"]

    # --- 1. Issue Node ---
    issue_node = {
        "type": map_issue_type(issue["type"]),  # Bug / Feature / Task
        "id": issue["issue_id"],
        "title": issue["summary"],
        "status": issue["status"],
        "description": issue["description"],
        "created": issue["created_date"],
        "updated": issue["updated_date"],
        "resolved": issue["resolved_date"],
        #"priority": issue["priority"]
    }

    # --- 2. Developer Nodes ---
    developers = []
    if issue["assignee_username"]:
        developers.append({
            "id": issue["author_email"],
            "name": issue["assignee_username"]
        })
        # Save the relationship from issue assignee to issue
        relationships = [{
            "from": issue_node["id"],
            "to": developers[-1]["name"],
            "type": "assigned_to"
        }]

    # --- 3. Commits ---
    commits = []
    code_files = []

    for row in agg["commits"]:
        commit = {
            "type": "Commit",
            "hash": row["commit_hash"],
            "message": row["message"],
            "date": row["committed_date"]
        }
        commits.append(commit)

        if row["file_path"]:
            code_files.append({
                "type": "Code",
                "file_name": extract_filename(row["file_path"]),
                "file_path": row["file_path"]
            })

    # --- 4. Relationships ---
    relationships = []

    # Issue ↔ Commit
    for c in commits:
        relationships.append({
            "from": issue_node["id"],
            "to": c["hash"],
            "type": "related_to"
        })

    # Commit ↔ Code
    for c in commits:
        for f in code_files:
            relationships.append({
                "from": c["hash"],
                "to": f["file_path"],
                "type": "changes"
            })

    # Issue links (issue ↔ issue)
    for link in agg["links"]:
        relationships.append({
            "from": link["source_issue_id"],
            "to": link["target_issue_id"],
            "type": link["name"] or "related_to"
        })

    # --- 5. Release mapping ---
    releases = []
    for v in agg["fix_versions"]:
        releases.append({
            "type": "Release",
            "version": v
        })

        relationships.append({
            "from": issue_node["id"],
            "to": v,
            "type": "included_in"
        })

    return {
        "nodes": [issue_node] + developers + commits + code_files + releases,
        "edges": relationships
    }

# --------------------------------
# new Version
# --------------------------------
def translate_issue_aggregate(agg: dict) -> dict:
    issue = agg["issue"]

    # --- Issue Node ---
    issue_node = {
        "type": map_issue_type(issue["type"]),
        "id": issue["issue_id"],
        "title": issue["summary"],
        "description": issue["description"],
        "status": issue["status"],
        "created": issue["created_date"],
        "updated": issue["updated_date"],
        "resolved": issue["resolved_date"]
    }

    nodes = [issue_node]
    edges = []

    # --- Developers (from issue table) ---
    if issue["assignee_username"]:
        nodes.append({
            "type": "Developer",
            "name": issue["assignee_username"]
        })

        edges.append({
            "from": issue["issue_id"],
            "to": issue["assignee_username"],
            "type": "assigned_to"
        })

    # --- change_set → Commit ---
    for cs in agg["change_set"]:
        commit_node = {
            "type": "Commit",
            "hash": cs["commit_hash"],
            "message": cs["message"],
            "date": cs["committed_date"]
        }
        nodes.append(commit_node)

        edges.append({
            "from": issue["issue_id"],
            "to": cs["commit_hash"],
            "type": "related_to"
        })

        # Developer (author)
        if cs["author"]:
            nodes.append({
                "type": "Developer",
                "name": cs["author"]
            })

            edges.append({
                "from": cs["commit_hash"],
                "to": cs["author"],
                "type": "created_by"
            })

    # --- code_change → Code ---
    for cc in agg["code_change"]:
        code_node = {
            "type": "Code",
            "file_name": extract_filename(cc["file_path"]),
            "file_path": cc["file_path"]
        }
        nodes.append(code_node)

        edges.append({
            "from": cc["commit_hash"],
            "to": cc["file_path"],
            "type": "changes"
        })

    # --- issue_fix_version → Release ---
    for ifv in agg["issue_fix_version"]:
        release_node = {
            "type": "Release",
            "version": ifv["fix_version"]
        }
        nodes.append(release_node)

        edges.append({
            "from": issue["issue_id"],
            "to": ifv["fix_version"],
            "type": "included_in"
        })

    # --- issue_component → (map to Feature/Module) ---
    for ic in agg["issue_component"]:
        component_node = {
            "type": "Component",
            "name": ic["component"]
        }
        nodes.append(component_node)

        edges.append({
            "from": issue["issue_id"],
            "to": ic["component"],
            "type": "has_component"
        })

    # --- issue_link → Issue relationships ---
    for il in agg["issue_link"]:
        edges.append({
            "from": il["source_issue_id"],
            "to": il["target_issue_id"],
            "type": il["name"] or "related_to"
        })

    return {
        "nodes": deduplicate(nodes),
        "edges": edges
    }
"""
Goes through the records to find the moment when the graph has reached the first time over the milestones

Result:
Target Nodes   | Chronological ID   | Timestamp               | Actual Unique Nodes
---------------------------------------------------------------------------
10             | 5a2615650e104c0713407637d65ae0ce7c2b257a | 2001-09-11T21:44:36Z    | 32
100            | bd3948c539ec1065db8b05b433ea55dbf844ff27 | 2001-09-18T16:29:48Z    | 174
1000           | 15bbd8def83fd3908a931a8342eef0b76a526e4d | 2002-07-18T14:39:58Z    | 1002
5000           | 944af6f61c6d4e03f6afed695f1febccc37f81a8 | 2006-06-16T13:46:11Z    | 5000
10000          | 9ecfd1a8a6808c4cec481592506c37f298e99505 | 2008-01-07T17:42:42Z    | 10000
"""

import sqlite3
from schema_converter import process_issue, process_change_set

# TODO: Update this path to where your local SQLite database file is located
DB_PATH = "./datasets/validate/lucene.sqlite3" 

def dict_factory(cursor, row):
    """Ensures row fetches behave like dictionaries, matching your converter's setup."""
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

def find_milestones():
    # Connect to the database
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = dict_factory
    cursor = conn.cursor()

    # Target node thresholds we want to catch
    targets = [10, 100, 1000, 5000, 10000]
    target_idx = 0
    
    # Track unique nodes globally using a set of their unique identifiers
    # Unique format combo: (primary_type, node_id)
    unique_nodes = set()

    print(f"{'Target Nodes':<14} | {'Chronological ID':<18} | {'Timestamp':<23} | {'Actual Unique Nodes'}")
    print("-" * 75)

    # 1. Fetch using your actual schema columns
    try:
        cursor.execute("""
            SELECT id, source_table, created_date 
            FROM issue_commit_chronological 
            ORDER BY created_date ASC, id ASC
        """)
        events = cursor.fetchall()
    except sqlite3.OperationalError as e:
        print(f"Database Error: {e}")
        return

    # 2. Iterate through the stream using your precise mapping
    for event in events:
        entity_id = event["id"]
        source_table = event["source_table"]
        timestamp = event["created_date"]

        # Route dynamically based on the source table string
        if source_table.lower() == "issue":
            result = process_issue(conn, entity_id, timestamp)
        elif source_table.lower() in ["change_set", "commit", "code_change"]:
            # Adjust the string array above if your commit table uses a different identifier
            result = process_change_set(conn, entity_id, timestamp)
        else:
            # Skip any unhandled source tables
            continue

        # Extract nodes and add them to our unique tracker set
        for node in result["nodes"]:
            specific_type = node["type"][-1]
            node_key = (specific_type, node["id"])
            unique_nodes.add(node_key)

        # 3. Check if we crossed the current threshold target
        current_node_count = len(unique_nodes)
        
        while target_idx < len(targets) and current_node_count >= targets[target_idx]:
            print(f"{targets[target_idx]:<14} | {entity_id:<18} | {str(timestamp):<23} | {current_node_count}")
            target_idx += 1

        # Break early if all milestone limits are discovered
        if target_idx >= len(targets):
            break

    if target_idx < len(targets):
        print("-" * 75)
        print(f"Note: Stream ended. Only reached a maximum of {len(unique_nodes)} unique nodes.")

    conn.close()

if __name__ == "__main__":
    find_milestones()
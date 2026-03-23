import sqlite3
import json
import time
import threading
from datetime import datetime
from kafka import KafkaProducer

DB_PATH = "test.sqlite3"
TOPIC = "events"

producer = KafkaProducer(
    bootstrap_servers="kafka:9092",
    value_serializer=lambda v: json.dumps(v).encode("utf-8")
)


# -------------------------------
# STEP 1 — Extract events from the database
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

def process_issue(conn, issue_id):
    cursor = conn.cursor()

    events = []

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
    events.append({
        "event_type": "Issue", # TODO: Include? or at least solve
        "issue_id": issue["issue_id"],
        "title": issue["summary"],
        "status": issue["status"],
        "description": issue["description"],
        "created_date": issue["created_date"],
        "updated_date": issue["updated_date"],
        "resolved_date": issue["resolved_date"]
    })

    events.append({
        "event_type": "Developer",
        "name": issue["assignee"],
    })

    # --- issue_link ---
    cursor.execute("""
        SELECT * FROM issue_link 
        WHERE source_issue_id = ?
    """, (issue_id,))
    for link in cursor.fetchall():
        events.append({
            "event_type": "IssueLink",
            "from_issue": link["source_issue_id"],
            "to_issue": link["target_issue_id"],
            "label": link["outward_label"]
        })

    # --- issue_fix_version ---
    cursor.execute("""
        SELECT * FROM issue_fix_version 
        WHERE issue_id = ?
    """, (issue_id,))
    for ifv in cursor.fetchall():
        events.append({
            "event_type": "Release",
            "issue_id": issue_id,
            "release": ifv["fix_version"]
        })

    return events

def process_change_set(conn, commit_hash, known_issues):
    cursor = conn.cursor()

    events = []

    # --- change_set ---
    cursor.execute("""
        SELECT * FROM change_set 
        WHERE commit_hash = ?
    """, (commit_hash,))
    cs = cursor.fetchone()

    events.append({
        "event_type": "Commit",
        "commit_hash": cs["commit_hash"],
        "message": cs["message"],
        "timestamp": cs["committed_date"]
    })

    events.append({
        "event_type": "Developer",
        "name": cs["author"],
    })

    # --- change_set_link ---
    cursor.execute("""
        SELECT * FROM change_set_link 
        WHERE commit_hash = ?
    """, (commit_hash,))
    for link in cursor.fetchall():
        issue_id = link["issue_id"]

        # Only link when issue already appeared to prevent errors
        if issue_id in known_issues:
            events.append({
                "event_type": "CommitLinkedToIssue",
                "commit_hash": commit_hash,
                "issue_id": issue_id
            })

    # --- code_change ---
    cursor.execute("""
        SELECT * FROM code_change 
        WHERE commit_hash = ?
    """, (commit_hash,))
    for cc in cursor.fetchall():
        events.append({
            "event_type": "Code",
            "file_path": cc["file_path"],
            "is_deleted": cc["is_deleted"]
        })

        # Save the link between the code and commit
        events.append({
            "event_type": "CommitToCode",
            "code_file": cc["file_path"],
            "commit_hash": commit_hash,
            "label": cc["change_type"]
        })

    return events

# -------------------------------
# Automatic replay mode
# -------------------------------

def process_timeline_auto(conn, interval=5):
    print("Starting streaming replay...")

    timeline = get_timeline(conn)

    #known_issues = set()

    for row in timeline:
        source_table = row["source_table"]
        entity_id = row["id"]

        if source_table == "issue":
            events = process_issue(conn, entity_id)
            #known_issues.add(entity_id)

        elif source_table == "change_set":
            events = process_change_set(conn, entity_id) #, known_issues)

        else:
            continue  # safety

        for event in events:
            send_event(event)
        
        time.sleep(interval)

# -------------------------------
# Manual replay mode
# -------------------------------

def process_timeline_manual(conn):
    print("\nManual mode:")
    print("Commands: send_next, exit")

    timeline = get_timeline(conn)

    for row in timeline:
        cmd = input("> ")

        if cmd == "send_next":
            source_table = row["source_table"]
            entity_id = row["id"]

            if source_table == "issue":
                events = process_issue(conn, entity_id)
                #known_issues.add(entity_id)

            elif source_table == "change_set":
                events = process_change_set(conn, entity_id) #, known_issues)

            else:
                continue  # safety

            for event in events:
                send_event(event)

        elif cmd == "exit":
            break

        else:
            print("Unknown command")



# -------------------------------
# STEP 2 — Send event to Kafka
# -------------------------------

def send_event(event):
    producer.send(TOPIC, event)
    producer.flush()
    print(f"Sent: {event}")


# -------------------------------
# Automatic replay mode
# -------------------------------

#def replay_events(interval=5):
#    print("Starting streaming replay...")
#
#    for event in stream_events():
#        send_event(event)
#        time.sleep(interval)


# -------------------------------
# Manual mode
# -------------------------------

#def manual_mode():
#    print("\nManual mode:")
#    print("Commands: send_next, exit")
#
#    event_generator = stream_events()
#
#    while True:
#        cmd = input("> ")
#
#        if cmd == "send_next":
#            try:
#                event = next(event_generator)
#                send_event(event)
#            except StopIteration:
#                print("No more events.")
#
#        elif cmd == "exit":
#            break
#
#        else:
#            print("Unknown command")


# -------------------------------
# MAIN
# -------------------------------

if __name__ == "__main__":
    time.sleep(10)  # wait for Kafka

    print("Select mode:")
    print("1 - Automatic replay (5 sec interval)")
    print("2 - Manual mode")

    mode = input("> ")

    if mode == "1":
        process_timeline_auto(sqlite3.connect(DB_PATH))
    elif mode == "2":
        process_timeline_manual(sqlite3.connect(DB_PATH))
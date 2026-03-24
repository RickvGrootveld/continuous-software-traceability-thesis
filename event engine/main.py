import sqlite3
import json
import time
import threading
from datetime import datetime
from kafka import KafkaProducer

from schema import get_timeline, process_issue, process_change_set

DB_PATH = "cassandra.db"
TOPIC = "events"

producer = KafkaProducer(
    bootstrap_servers="kafka:9092",
    value_serializer=lambda v: json.dumps(v).encode("utf-8")
)

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

        timestamp = datetime.now().isoformat()

        if source_table == "issue":
            event = process_issue(conn, entity_id, timestamp)
            #known_issues.add(entity_id)

        elif source_table == "change_set":
            event = process_change_set(conn, entity_id, timestamp) #, known_issues)

        else:
            continue  # safety

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

            timestamp = datetime.now().isoformat()

            if source_table == "issue":
                event = process_issue(conn, entity_id, timestamp)
                #known_issues.add(entity_id)

            elif source_table == "change_set":
                event = process_change_set(conn, entity_id, timestamp) #, known_issues)

            else:
                continue  # safety

            send_event(event)

        elif cmd == "exit":
            break

        else:
            print("Unknown command")



# -------------------------------
# Send event to Kafka
# -------------------------------

def send_event(event):
    producer.send(TOPIC, event)
    producer.flush()
    print(f"Sent: {event}")

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
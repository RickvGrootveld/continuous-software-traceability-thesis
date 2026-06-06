import sqlite3
import json
import time
from datetime import datetime

from kafka import KafkaProducer

from schema_converter import process_issue, process_change_set

DB_PATH = "lucene.sqlite3" #cassandra.db
TOPIC = "events"

producer = KafkaProducer(
    bootstrap_servers=["kafka:9092"],
    value_serializer=lambda v: json.dumps(v).encode("utf-8")
)

def get_timeline(conn, query):
    """
    Applies ASC ordering to make sure all the events in the dataset are
    in chronological order.
    """
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(query)

    return cursor.fetchall()

def process_preload_data(conn):
    """
    Loads all of the data to the point in time that will be streamed to simulate
    the project's historical data. This is needed to make sure the LLM enrichment 
    service has enough data in the graph to work with when the streaming starts (
    regarding neighbourhood retrieval and vector similarity).
    """
    print("Start preloading data ...")

    query = """
        SELECT source_table, id, created_date
        FROM issue_commit_events_preload
        ORDER BY created_date ASC
    """

    timeline = get_timeline(conn, query)

    for row in timeline:

        source_table = row["source_table"]
        entity_id = row["id"]

        timestamp = datetime.now().isoformat()
        
        if source_table == "issue":
            event = process_issue(conn, entity_id, timestamp)

        elif source_table == "change_set":
            event = process_change_set(conn, entity_id, timestamp)

        else:
            continue  # safety

        send_event(event)

# Automatic replay mode
def process_simulation_data(conn, interval=10):
    print("Starting streaming replay...")
    
    query = """
        SELECT source_table, id, created_date
        FROM issue_commit_events_simulation
        ORDER BY created_date ASC
    """

    timeline = get_timeline(conn, query)

    for row in timeline:

        source_table = row["source_table"]
        entity_id = row["id"]

        timestamp = datetime.now().isoformat()

        if source_table == "issue":
            event = process_issue(conn, entity_id, timestamp)

        elif source_table == "change_set":
            event = process_change_set(conn, entity_id, timestamp)

        else:
            continue  # safety

        send_event(event)

        time.sleep(interval)

# Send event to Kafka
def send_event(event):
    producer.send(TOPIC, event)
    producer.flush()
    print(f"Sent: {event}")

# MAIN
if __name__ == "__main__":
    # Wait for the knowledge graph to be ready 
    # (KG service needs to load the weights of the models) which takes around 20 seconds
    time.sleep(20)
    process_preload_data(sqlite3.connect(DB_PATH))
    #time.sleep(30) # wait 30 seconds to start the simulation
    #process_simulation_data(sqlite3.connect(DB_PATH))
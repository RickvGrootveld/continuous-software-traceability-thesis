import json
import time
from kafka import KafkaConsumer
from neo4j import GraphDatabase

TOPIC = "events"

consumer = KafkaConsumer(
    TOPIC,
    bootstrap_servers='kafka:9092',
    value_deserializer=lambda m: json.loads(m.decode('utf-8')),
    auto_offset_reset='earliest',
    group_id='kg-group'
)

driver = GraphDatabase.driver(
    "bolt://neo4j:7687",
    auth=("neo4j", "password")
)

def insert_into_neo4j(tx, record):
    query = """
    MERGE (n:Record {id: $id})
    SET n += $props
    """
    tx.run(query, id=record.get("id"), props=record)

def consume():
    for message in consumer:
        record = message.value
        print(f"Received: {record}")

        with driver.session() as session:
            session.write_transaction(insert_into_neo4j, record)

if __name__ == "__main__":
    time.sleep(15)  # wait for services
    consume()
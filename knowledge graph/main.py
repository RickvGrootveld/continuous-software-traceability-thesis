import json
import time
from kafka import KafkaConsumer

from knowledge_graph import KnowledgeGraph, insert_into_neo4j, insert_events, link_nodes

TOPIC = "events"


consumer = KafkaConsumer(
    TOPIC,
    bootstrap_servers='kafka:9092',
    value_deserializer=lambda m: json.loads(m.decode('utf-8')),
    auto_offset_reset='earliest',
    group_id='kg-group'
)

def consume(kg: KnowledgeGraph):
    for message in consumer:
        record = message.value
        print(f"Received: {record}")

        nodes = record["nodes"]
        edges = record["edges"]

        with kg.driver.session() as session:
            try:
                # execute_write() automatically retries the unit of work by an error
                session.execute_write(insert_events, nodes)
                session.execute_write(link_nodes, edges)
            except Exception as e:
                print(f"Error occurred while inserting record: {e}")

if __name__ == "__main__":
    time.sleep(10)  # wait for services
    kg = KnowledgeGraph()
    consume(kg)
    kg.close()
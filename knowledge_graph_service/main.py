import json
from datetime import datetime, timezone
from kafka import KafkaConsumer

from shared_utils.embedding_service import EmbeddingService
from shared_utils.neo4j import Neo4jClient

TOPIC = "events"

consumer = KafkaConsumer(
    TOPIC,
    bootstrap_servers='kafka:9092',
    value_deserializer=lambda m: json.loads(m.decode('utf-8')),
    auto_offset_reset='earliest',
    group_id='kg-group'
)


def assemble_edge(raw: dict) -> dict:
    """Ensure every edge conforms to the required schema before writing."""
    return {
        "source": raw["source"],
        "target": raw["target"],
        "label":  raw["label"],
        "properties": {
            "timestamp":   datetime.now(timezone.utc).isoformat(),
            "system":      "LLM",
            "confidence":  float(raw["properties"].get("confidence", 0.0)),
            "explanation": raw["properties"].get("explanation", "")
        }
    }

def consume(kg: Neo4jClient, embedding_model: EmbeddingService):

    for message in consumer:
        record = message.value
        print(f"Received: {record}")

        nodes = record["nodes"]
        edges = record["edges"]

        with kg.driver.session() as session:
            try:
                nodes = embedding_model.generate_embeddings(nodes)

                for n in nodes:
                    n["properties"]["timestamp"] = datetime.now().isoformat()

                kg.insert_nodes(nodes)
                kg.insert_edges(edges)

            except Exception as e:
                print(f"Error occurred while inserting record: {e}")


if __name__ == "__main__":
    kg = Neo4jClient()
    embedding_model = EmbeddingService()
    print("Starting to consume Kafka messages...")
    consume(kg, embedding_model)
    kg.close()
import json
import threading
from datetime import datetime, timezone
from kafka import KafkaConsumer
import csv
import os
import redis

from shared_utils.embedding_service import EmbeddingService
from shared_utils.neo4j import Neo4jClient

TOPIC = "events"
CSV_FILE = "/app/knowledge_graph_service/log_db_results.csv"

REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
READY_CHANNEL = "enrichment_ready"
GATE_TIMEOUT_SECONDS = 3600  # safety valve, after 60 minutes

consumer = KafkaConsumer(
    TOPIC,
    bootstrap_servers='kafka:9092',
    value_deserializer=lambda m: json.loads(m.decode('utf-8')),
    auto_offset_reset='earliest',
    group_id='kg-group'
)


class EnrichmentGate:
    """
    Blocks the consume loop until the enrichment service confirms (via Redis
    pub/sub) that it has finished enriching and inserting the previous batch.
    Subscribes immediately on construction so no 'ready' message can be
    missed once the consume loop actually starts waiting.
    """

    def __init__(self, host=REDIS_HOST, port=REDIS_PORT):
        self.client = redis.Redis(host=host, port=port, db=0)
        self.pubsub = self.client.pubsub()
        self.pubsub.subscribe(READY_CHANNEL)
        self.ready_event = threading.Event()
        self._listener_thread = threading.Thread(target=self._listen, daemon=True)
        self._listener_thread.start()
        print(f"Subscribed to Redis channel '{READY_CHANNEL}' on {host}:{port}")

    def _listen(self):
        for message in self.pubsub.listen():
            if message["type"] == "message":
                self.ready_event.set()

    def wait_for_ready(self):
        self.ready_event.wait()
        self.ready_event.clear()


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

def log_experiment_run(columns):
        with open(CSV_FILE, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(columns)

def consume(kg: Neo4jClient, embedding_model: EmbeddingService):
    gate = EnrichmentGate()

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

                nodes_metric = kg.insert_nodes(nodes)
                edges_metric = kg.insert_edges(edges)

                metrics = [
                    datetime.now().isoformat(),
                    nodes_metric["graph_nodes"],
                    nodes_metric["graph_edges"],
                    nodes_metric["db_insert_time_ms"],
                    edges_metric["db_insert_time_ms"],
                ]

                log_experiment_run(metrics)

            except Exception as e:
                print(f"Error occurred while inserting record: {e}")

        # Block here until the enrichment service confirms it has finished
        # enriching (and inserting) this batch — this is what guarantees
        # enrichment never sees events that haven't been "released" yet.
        print("Waiting for enrichment service to finish before consuming next event...")
        gate.wait_for_ready()


if __name__ == "__main__":
    kg = Neo4jClient()
    embedding_model = EmbeddingService()
    print("Starting to consume Kafka messages...")
    consume(kg, embedding_model)
    kg.close()
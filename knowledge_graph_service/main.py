import json
from datetime import datetime, timezone
from kafka import KafkaConsumer
import ollama

from knowledge_graph import KnowledgeGraph, insert_nodes, link_nodes
from open_source_llm import (
    assemble_edge, 
    run_llm_enrichment, 
    write_edges,
    OLLAMA_URL, 
    ensure_model
)

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

def consume(kg: KnowledgeGraph, client: ollama.Client):
    for message in consumer:
        record = message.value
        print(f"Received: {record}")

        nodes = record["nodes"]
        edges = record["edges"]

        with kg.driver.session() as session:
            try:
                # execute_write() automatically retries the unit of work by an error
                session.execute_write(insert_nodes, nodes)
                session.execute_write(link_nodes, edges)

            except Exception as e:
                print(f"Error occurred while inserting record: {e}")

        #async def enrich():
        run_llm_enrichment(client, kg.driver, nodes)
        #with kg.driver.session() as session:
        #        try:
        #            print(f"LLM returned {len(llm_edges)} edges. Validating and writing...")
        #            edges = [assemble_edge(e) for e in llm_edges]
        #            # write LLM enrichment to the graph
        #            session.execute_write(link_nodes, edges)
        #
        #        except Exception as e:
        #            print(f"Error occurred while inserting enrichment record: {e}")


if __name__ == "__main__":
    kg = KnowledgeGraph()
    client = ollama.Client(host=OLLAMA_URL)
    ensure_model(client)
    consume(kg, client)
    kg.close()
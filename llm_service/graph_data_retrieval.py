from neo4j import GraphDatabase
from typing import List, Dict


class Neo4jClient:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    # ====================================
    # Retrieve k-hop neighborhood
    # ====================================

    def get_k_hop_neighbors(self, node_ids: List[str], k: int = 2):
        query = f"""
        MATCH (n)
        WHERE n.uid IN $node_ids
        MATCH p=(n)-[*1..{k}]-(m)
        RETURN DISTINCT nodes(p) as nodes, relationships(p) as rels
        """

        all_nodes = {}
        all_edges = []

        with self.driver.session() as session:
            results = session.run(query, node_ids=node_ids)

            for record in results:
                for node in record["nodes"]:
                    uid = node.get("uid")

                    all_nodes[uid] = {
                        "type": list(node.labels)[0],
                        "id": uid,
                        "properties": dict(node)
                    }

                for rel in record["rels"]:
                    edge = {
                        "source": rel.start_node.get("uid"),
                        "target": rel.end_node.get("uid"),
                        "label": rel.type,
                        "properties": dict(rel)
                    }
                    all_edges.append(edge)

        return list(all_nodes.values()), all_edges

    # ====================================
    # Insert inferred edge
    # ====================================

    def insert_llm_edge(self, edge: Dict):
        query = """
        MATCH (a {uid: $source})
        MATCH (b {uid: $target})
        MERGE (a)-[r:LLM_RELATION {
            label: $label
        }]->(b)
        SET r += $properties
        """

        with self.driver.session() as session:
            session.run(
                query,
                source=edge["source"],
                target=edge["target"],
                label=edge["label"],
                properties=edge["properties"]
            )

class VectorSimilarityRetriever:

    def __init__(self):
        pass

    def find_similar_nodes(
        self,
        nodes: List[Dict],
        top_k: int = 20
    ) -> List[Dict]:
        """
        IMPLEMENT THIS YOURSELF.

        Expected return format:

        [
            {
                "type": "Bug",
                "id": "Bug:123",
                "properties": {
                    "title": "Authorization timeout"
                }
            }
        ]
        """

        return []
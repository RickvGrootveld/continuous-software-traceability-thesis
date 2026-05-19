from typing import List, Dict

from neo4j import GraphDatabase

# ============================================================
# CONFIGURATION
# ============================================================

# ------------------------
# Neo4j
# ------------------------

NEO4J_URI = "bolt://neo4j:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password"

# ------------------------
# Sliding Window
# ------------------------

WINDOW_SECONDS = 10

# ------------------------
# Retrieval
# ------------------------

K_HOPS = 2
MAX_VECTOR_RESULTS = 20
MAX_CONTEXT_NODES = 50


class Neo4jClient:

    def __init__(self):

        self.driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD)
        )

    def vector_index_creation(self):
        query = """
        CREATE VECTOR INDEX node_embeddings
        FOR (n)
        ON (n.embedding)
        OPTIONS {
            indexConfig: {
                `vector.dimensions`: 384,
                `vector.similarity_function`: 'cosine'
            }
        }
        """
        with self.driver.session() as session:
            session.run(query)

    # ========================================================
    # Get new/unprocessed nodes
    # ========================================================

    def get_recent_nodes(self, limit=100):

        query = """
        MATCH (n)
        WHERE
            n.last_llm_processed_at IS NULL
            OR n.last_llm_processed_at <
               datetime() - duration('PT1H')

        RETURN n
        ORDER BY n.created_at ASC
        LIMIT $limit
        """

        nodes = []

        with self.driver.session() as session:

            results = session.run(query, limit=limit)

            for record in results:

                node = record["n"]

                nodes.append({
                    "type": list(node.labels)[0],
                    "id": node["uid"],
                    "properties": dict(node)
                })

        return nodes

    # ========================================================
    # k-hop neighborhood retrieval
    # ========================================================

    def get_k_hop_neighbors(
        self,
        node_ids: List[str],
        k: int = 2
    ):
        """Retrieve k-hop neighborhood with 2 hops for a list of node IDs."""

        query = f"""
        MATCH (n)
        WHERE n.uid IN $node_ids

        MATCH p=(n)-[*1..{k}]-(m)

        RETURN DISTINCT
            nodes(p) as nodes,
            relationships(p) as rels
        """

        all_nodes = {}
        all_edges = []

        with self.driver.session() as session:

            results = session.run(
                query,
                node_ids=node_ids
            )

            for record in results:

                for node in record["nodes"]:

                    uid = node["uid"]

                    all_nodes[uid] = {
                        "type": list(node.labels)[0],
                        "id": uid,
                        "properties": dict(node)
                    }

                for rel in record["rels"]:

                    edge = {
                        "source": rel.start_node["uid"],
                        "target": rel.end_node["uid"],
                        "label": rel.type,
                        "properties": dict(rel)
                    }

                    all_edges.append(edge)

        return list(all_nodes.values()), all_edges

    # ========================================================
    # Insert inferred edge
    # ========================================================

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

    # ========================================================
    # Insert nodes
    # ========================================================

    def insert_nodes(self, nodes: list):
        """Insert nodes using UNWIND."""
        query = """
            UNWIND $nodes AS node
            CALL apoc.merge.node(
              [node.type],
              {id: node.id},
              node.properties,
              {}
            ) 
            YIELD node AS n
            RETURN count(n)
        """
        with self.driver.session() as session:
            session.run(query, nodes=nodes)

    # ========================================================
    # Insert edges
    # ========================================================

    def link_nodes(self, edges: list):
        """Insert edges using UNWIND."""
        query = """
            UNWIND $edges AS edge

            // 1. Extract Label and ID from strings like "Commit:82f5b6..."
            WITH edge, 
                 split(edge.source, ':') AS srcParts, 
                 split(edge.target, ':') AS tgtParts

            // 2. Use labels for speed. If labels are dynamic, use APOC to find nodes.
            CALL apoc.merge.node([srcParts[0]], {id: srcParts[1]}) YIELD node AS a
            CALL apoc.merge.node([tgtParts[0]], {id: tgtParts[1]}) YIELD node AS b

            // 3. Create the relationship with all 6 required arguments
            CALL apoc.merge.relationship(
              a,               // Start node
              edge.label,      // Rel type (e.g., 'CreatedBy')
              {},              // Ident properties (usually empty for rels)
              edge.properties, // Properties to set on Create
              b,               // End node
              {}               // Properties to set on Match (Required 6th arg)
            ) 
            YIELD rel
            RETURN count(rel)
        """
        with self.driver.session() as session:
            session.run(query, edges=edges)

    # ========================================================
    # Mark processed
    # ========================================================

    def mark_nodes_processed(self, node_ids: List[str]):

        query = """
        MATCH (n)
        WHERE n.uid IN $node_ids

        SET n.last_llm_processed_at = datetime()

        SET n.llm_processing_count =
            coalesce(n.llm_processing_count, 0) + 1
        """

        with self.driver.session() as session:

            session.run(
                query,
                node_ids=node_ids
            )
    
    def query_similar_nodes(
        self,
        embedding,
        top_k=50
    ):

        query = """
        CALL db.index.vector.queryNodes(
            'node_embeddings',
            $top_k,
            $embedding
        )

        YIELD node, score

        RETURN node, score
        """

        nodes = []

        with self.driver.session() as session:

            results = session.run(
                query,
                embedding=embedding,
                top_k=top_k
            )

            for record in results:

                node = record["node"]

                score = record["score"]

                nodes.append({
                    "type": list(node.labels)[0],
                    "id": node["uid"],
                    "score": score,
                    "properties": dict(node)
                })

        return nodes
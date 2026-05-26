from typing import List, Dict

from neo4j import GraphDatabase

NEO4J_URI = "bolt://neo4j:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password"

WINDOW_SECONDS = 10
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
        FOR (n:TraceabilityNode)
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

    def get_k_hop_neighbors(self, node_ids: List[str]):
        """
        Retrieve the neighborhood for a list of node IDs with edge-type-aware hop limits:
          - Edges with system='dataset' → 2 hops
          - Edges with system='LLM'     → 1 hop
        Both result sets are merged and deduplicated.
        """

        # 2-hop traversal restricted to dataset edges only
        dataset_query = """
        MATCH (n)
        WHERE n.uid IN $node_ids

        MATCH p=(n)-[r*1..2]-(m)
        WHERE ALL(rel IN relationships(p) WHERE rel.system = 'dataset')

        RETURN DISTINCT
            nodes(p)         AS nodes,
            relationships(p) AS rels
        """

        # 1-hop traversal restricted to LLM edges only
        llm_query = """
        MATCH (n)
        WHERE n.uid IN $node_ids

        MATCH p=(n)-[r*1..1]-(m)
        WHERE ALL(rel IN relationships(p) WHERE rel.system = 'LLM')

        RETURN DISTINCT
            nodes(p)         AS nodes,
            relationships(p) AS rels
        """

        all_nodes = {}
        all_edges = {}   # keyed by (source, target, label) to deduplicate

        def _collect(results):
            for record in results:
                for node in record["nodes"]:
                    uid = node["uid"]
                    if uid not in all_nodes:
                        all_nodes[uid] = {
                            "type":       list(node.labels)[0],
                            "id":         uid,
                            "properties": dict(node),
                        }

                for rel in record["rels"]:
                    src   = rel.start_node["uid"]
                    tgt   = rel.end_node["uid"]
                    label = rel.type
                    key   = (src, tgt, label)
                    if key not in all_edges:
                        all_edges[key] = {
                            "source":     src,
                            "target":     tgt,
                            "label":      label,
                            "properties": dict(rel),
                        }

        with self.driver.session() as session:
            _collect(session.run(dataset_query, node_ids=node_ids))
            _collect(session.run(llm_query,     node_ids=node_ids))

        return list(all_nodes.values()), list(all_edges.values())

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

    def insert_nodes(self, nodes: list):
        """Insert nodes using UNWIND."""
        query = """
        UNWIND $nodes AS node

        CALL apoc.merge.node(
          ["TraceabilityNode", node.type],
          {id: node.id},
          node.properties,
          node.properties
        )
        YIELD node AS n

        RETURN count(n)
        """
        with self.driver.session() as session:
            session.run(query, nodes=nodes)

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
    
    def query_similar_nodes(self, embedding, top_k=50):
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
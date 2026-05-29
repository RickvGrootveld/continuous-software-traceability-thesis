from typing import List, Dict

from neo4j import GraphDatabase

NEO4J_URI = "bolt://neo4j:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password"

WINDOW_SECONDS = 10
K_HOPS = 1
MAX_VECTOR_RESULTS = 20
MAX_CONTEXT_NODES = 50


class Neo4jClient:

    def __init__(self):

        self.driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASSWORD)
        )
        
        self.vector_index_creation()

    def vector_index_creation(self):
        query = """
        CREATE VECTOR INDEX node_embeddings IF NOT EXISTS
        FOR (n:TraceabilityNode)
        ON n.embedding
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
            datetime(n.timestamp) >= datetime({timezone: 'UTC'}) - duration('PT1S')
        RETURN n, 
               // Filter out TraceabilityNode, sort alphabetically, and join with colons
               reduce(s = "", l IN apoc.coll.sort([label IN labels(n) WHERE label <> 'TraceabilityNode']) | 
                   s + (CASE WHEN s = "" THEN "" ELSE ":" END) + l
               ) AS clean_type
        ORDER BY n.timestamp DESC
        LIMIT $limit
        """

        nodes = []

        with self.driver.session() as session:
            results = session.run(query, limit=limit)
            for record in results:
                node = record["n"]
                n = {
                    "type": record["clean_type"],  # Pulls the pre-formatted string directly
                    "id": node["uid"],
                    "properties": dict(node)
                }
                print(f"n.labels: {list(node.labels)}")
                print(f"n.type: {n.type}")
                nodes.append(n)

        return nodes

    def get_k_hop_neighbors(self, node_ids: List[str], k=1):
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

    #def insert_llm_edge(self, edge: Dict):
    #    query = """
    #    MATCH (a {uid: $source})
    #    MATCH (b {uid: $target})
#
    #    MERGE (a)-[r:LLM_RELATION {
    #        label: $label
    #    }]->(b)
#
    #    SET r += $properties
    #    """
#
    #    with self.driver.session() as session:
    #        session.run(
    #            query,
    #            source=edge["source"],
    #            target=edge["target"],
    #            label=edge["label"],
    #            properties=edge["properties"]
    #        )

    def insert_nodes(self, nodes: list):
        """Insert nodes using UNWIND."""
        query = """
        UNWIND $nodes AS node

        CALL apoc.merge.node(
          node.type,
          {id: node.id},
          node.properties,
          node.properties
        )
        YIELD node AS n

        RETURN count(n)
        """

        with self.driver.session() as session:
            session.run(query, nodes=nodes)

    def insert_edges(self, edges: list):
        """Insert edges safely using native label arrays."""
        query = """
        UNWIND $edges AS edge

        // 1. Look up or create the source node using 'source type' and 'source id'
        CALL apoc.merge.node(edge.`source type`, {id: edge.`source id`}) YIELD node AS a

        // 2. Look up or create the target node using 'target type' and 'target id'
        CALL apoc.merge.node(edge.`target type`, {id: edge.`target id`}) YIELD node AS b

        // 3. Construct the connecting relationship cleanly
        CALL apoc.merge.relationship(
          a, 
          edge.label, 
          {}, 
          edge.properties, 
          b, 
          {}
        ) 
        YIELD rel
        RETURN count(rel)
        """
        with self.driver.session() as session:
            session.run(query, edges=edges)
    
    def query_similar_nodes(self, embedding, top_k=50):
        query = """
        MATCH (node:TraceabilityNode)
        SEARCH node IN (
          VECTOR INDEX node_embeddings 
          FOR $embedding 
          LIMIT $top_k
        ) SCORE AS score
        WHERE score >= 0.75
        RETURN node, score
        ORDER BY score DESC;
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

                print(f"Retrieved similar node {node}")

                nodes.append({
                    "type": list(node.labels)[0],
                    "id": node["uid"],
                    "score": score,
                    "properties": dict(node)
                })

        return nodes
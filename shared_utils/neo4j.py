from typing import List, Dict

from neo4j import GraphDatabase

NEO4J_URI = "bolt://neo4j:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password"

WINDOW_SECONDS = 10
K_HOPS = 1
MAX_VECTOR_RESULTS = 20
MAX_CONTEXT_NODES = 200


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
        // 1. Fetch the recent source nodes
        MATCH (n:TraceabilityNode)
        WHERE datetime(n.timestamp) >= datetime({timezone: 'UTC'}) - duration('PT1S')
        WITH n
        ORDER BY n.timestamp DESC
        LIMIT $limit

        // 2. Collect the nodes so we can find relationships connecting ONLY this subset
        WITH collect(n) AS node_list
        UNWIND node_list AS n

        // 3. Find edges where both the start and end nodes are inside our collected list
        OPTIONAL MATCH (n)-[r]->(target)
        WHERE target IN node_list

        RETURN 
            n, 
            coll.sort([label IN labels(n) WHERE label <> 'TraceabilityNode']) AS filtered_labels,
            collect(DISTINCT {
                rel: r,
                target_id: target.id,
                target_labels: coll.sort([label IN labels(target) WHERE label <> 'TraceabilityNode'])
            }) AS connected_edges
        """

        nodes = []
        edges = []
        seen_edges = set()  # Prevent duplicate edge tracking in the undirected check

        with self.driver.session() as session:
            results = session.run(query, limit=limit)
            for record in results:
                node = record["n"]
                source_id = node["id"]
                # Formulate the source label array
                source_labels = ["TraceabilityNode"] + record["filtered_labels"]

                # Format and append the node block
                nodes.append({
                    "id": source_id,
                    "type": source_labels,
                    **dict(node)
                })

                # Format and append the accompanying edges
                for edge_entry in record["connected_edges"]:
                    rel = edge_entry["rel"]
                    if rel is None:
                        continue
                    
                    # Create a unique tracking key using the Neo4j element/relationship ID
                    rel_internal_id = rel.element_id if hasattr(rel, 'element_id') else rel.id
                    if rel_internal_id in seen_edges:
                        continue
                    seen_edges.add(rel_internal_id)

                    target_labels = ["TraceabilityNode"] + edge_entry["target_labels"]

                    edges.append({
                        "source id": source_id,
                        "target id": edge_entry["target_id"],
                        "source type": source_labels,
                        "target type": target_labels,
                        "label": rel.type,
                        "properties": dict(rel)
                    })

        return nodes, edges

    def get_k_hop_neighbors(self, node_ids: List[str], k=1):
        """
        Retrieve the neighborhood for a list of node IDs with edge-type-aware hop limits:
          - Edges with system='dataset' → 2 hops
          - Edges with system='LLM'     → 1 hop
        This function returns the nodes that have incoming and outgoing edges from the giving list of nodes, using -(m) instead of ->(m).
        Both result sets are merged and deduplicated.
        """

        # 2-hop traversal restricted to dataset edges only
        dataset_query = f"""
        MATCH (n)
        WHERE n.id IN $node_ids

        MATCH p=(n)-[r*1..{k}]-(m)
        WHERE ALL(rel IN relationships(p) WHERE rel.system = 'dataset')

        RETURN DISTINCT
            nodes(p)         AS nodes,
            relationships(p) AS rels
        """

        # 1-hop traversal restricted to LLM edges only
        llm_query = """
        MATCH (n)
        WHERE n.id IN $node_ids

        MATCH p=(n)-[r*1..1]-(m)
        WHERE ALL(rel IN relationships(p) WHERE rel.system = 'LLM')

        RETURN DISTINCT
            nodes(p)         AS nodes,
            relationships(p) AS rels
        """

        all_nodes = []
        all_edges = []   # keyed by (source, target, label) to deduplicate
        ids_seen = set()  # To track seen node IDs for deduplication

        def _collect(results):
            for record in results:
                for node in record["nodes"]:
                    id = node["id"]
                    # check if the id is already captured, if not, add it
                    if id not in ids_seen:
                        ids_seen.add(id)
                        all_nodes.append({
                            "id": id,
                            "type": ", ".join(node.labels),
                            **dict(node)
                        })
                        del all_nodes[-1]["embedding"]

                for rel in record["rels"]:
                    start_node, end_node = rel.nodes
                    src   = start_node["id"]
                    tgt   = end_node["id"]
                    label = rel.type
                    key   = (src, tgt, label)
                    if key not in ids_seen:
                        ids_seen.add(key)
                        all_edges.append({
                            "source":     src,
                            "target":     tgt,
                            "label":      label,
                            "properties": dict(rel),
                        })

        with self.driver.session() as session:
            _collect(session.run(dataset_query, node_ids=node_ids))
            _collect(session.run(llm_query,     node_ids=node_ids))

        return all_nodes, all_edges

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
        CALL apoc.merge.node(edge.`source type`, {id: edge.`source_id`}) YIELD node AS a

        // 2. Look up or create the target node using 'target type' and 'target id'
        CALL apoc.merge.node(edge.`target type`, {id: edge.`target_id`}) YIELD node AS b

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

    def insert_llm_edges(self, edges: list):
        """
        Insert edges safely using only source and target IDs. 
        This function doesn't make use of apoc, making sure no nodes were created by accident
        """
        query = """
        UNWIND $edges AS edge

        // 1. Strictly look up the existing source and target nodes by ID using the base label index
        MATCH (a:TraceabilityNode {id: edge.source_id})
        MATCH (b:TraceabilityNode {id: edge.target_id})

        // 2. Construct the connecting relationship cleanly
        CALL apoc.merge.relationship(
          a, 
          edge.label, 
          {}, 
          {
              system: edge.system,
              confidence: toFloat(edge.confidence),
              explanation: edge.explanation,
              timestamp: datetime({timezone: 'UTC'})
          }, 
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
        WHERE score >= 0.87
        RETURN node
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
                nodes.append({
                    "id": node["id"],
                    "type": ", ".join(node.labels),
                    **dict(node)
                })
                del nodes[-1]["embedding"]

        return nodes
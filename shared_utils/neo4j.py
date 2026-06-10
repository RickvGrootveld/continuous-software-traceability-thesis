from typing import List, Dict

from neo4j import GraphDatabase

NEO4J_URI = "bolt://neo4j:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "password"
K_HOPS = 1


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

    def measure_insertion_time(self, query, *args, **kwargs):
        with self.driver.session() as session:
            # 1. Execute the raw insertion query directly (no PROFILE wrapper)
            results = session.run(query, *args, **kwargs)

            # 2. Drain the streaming buffer into memory (important if your query ends with a RETURN clause)
            #records = list(results)

            # 3. Harvest server-side database consumption metadata
            summary = results.consume()
            db_insert_time_ms = summary.result_consumed_after

            # 4. Measure the updated Graph Pollution / Growth metrics *after* the insertion completes
            size_record = session.run(
                "MATCH (n) WITH count(n) as nodes MATCH ()-[r]->() RETURN nodes, count(r) as edges"
            ).single()

            graph_nodes = size_record["nodes"] if size_record else 0
            graph_edges = size_record["edges"] if size_record else 0

            metrics = {
                "graph_nodes": graph_nodes,
                "graph_edges": graph_edges,
                "db_insert_time_ms": db_insert_time_ms
            }

            #logger.info(f"[PROFILER - WRITE] Nodes: {graph_nodes} | Edges: {graph_edges} | Time: {db_insert_time_ms}ms")

            return metrics

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

        metrics = self.measure_insertion_time(query, nodes=nodes)
        return metrics

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

        metrics = self.measure_insertion_time(query, edges=edges)
        return metrics

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
        metrics = self.measure_insertion_time(query, edges=edges)
        return metrics
    
    def get_total_db_hits(self, profile_plan) -> int:
        """Recursively sums DbHits from all branches of the execution plan tree."""
        if not profile_plan:
            return 0
        total_hits = getattr(profile_plan, 'db_hits', 0)
        for child in getattr(profile_plan, 'children', []):
            total_hits += self.get_total_db_hits(child)
        return total_hits
    
    def get_neo4j_metrics(self, query: str, *args, **kwargs):
        """
        Executes a Neo4j query with profiling enabled and captures software engineering 
        research metrics (graph size/pollution, dbHits, and engine execution time).
    
        Supports dynamic query parameters natively.
        
        Args:
            driver: The Neo4j graph driver instance.
            query (str): The raw Cypher query string.
            *args: Positional arguments to pass to session.run().
            **kwargs: Keyword parameters for the query (e.g., limit, embedding, node_ids).
            
        Returns:
            Tuple[List[Record], Dict[str, Any]]: (materialized_records, metrics_dictionary)
        """
        # 1. Enforce PROFILE wrapper on the query to capture structural performance metrics
        query_stripped = query.strip()
        if not query_stripped.upper().startswith("PROFILE"):
            profiled_query = f"PROFILE {query}"
        else:
            profiled_query = query
    
        with self.driver.session() as metric_session:
            # 2. Record Graph Pollution / Growth metrics before modifying or deep-traversing
            size_record = metric_session.run(
                "MATCH (n) WITH count(n) as nodes MATCH ()-[r]->() RETURN nodes, count(r) as edges"
            ).single()
            
            graph_nodes = size_record["nodes"] if size_record else 0
            graph_edges = size_record["edges"] if size_record else 0
    
            # 3. Execute the target query, proxying all flexible parameter configurations
        with self.driver.session() as session:
            results = session.run(profiled_query, *args, **kwargs)
            
            # 4. Drain the streaming buffer into memory to complete execution
            records = list(results)
            
            # 5. Harvest performance metadata
            summary = results.consume()
            
            db_retrieval_time_ms = summary.result_consumed_after
            total_db_hits = self.get_total_db_hits(summary.profile)

        return records, graph_nodes, graph_edges, total_db_hits, db_retrieval_time_ms

    def get_recent_nodes(self, limit=100):
        query = """
        // 1. Fetch the recent source nodes
        MATCH (n:TraceabilityNode)
        WHERE datetime(n.timestamp) >= datetime({timezone: 'UTC'}) - duration('PT1S') AND n.embedding IS NOT NULL
        WITH n
        ORDER BY n.timestamp DESC
        LIMIT $limit

        // 2. Collect the nodes so we can find relationships connecting ONLY this subset
        WITH collect(n) AS node_list
        UNWIND node_list AS n

        // 3. Find edges where both the start and end nodes are inside our collected list neglect ghost nodes
        OPTIONAL MATCH (n)-[r]->(target)
        WHERE target IN node_list AND target.embedding IS NOT NULL

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

        results, total_nodes, total_edges, total_db_hits, db_retrieval_time_ms = self.get_neo4j_metrics(query, limit=limit)

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
                    "label": rel.type,
                    })
                
        return nodes, edges, total_nodes, total_edges, total_db_hits, db_retrieval_time_ms 

    def get_k_hop_neighbors(self, node_ids: List[str], k=1):
        """
        Retrieve the neighborhood for a list of node IDs with edge-type-aware hop limits:
          - Edges with system='dataset' → 2 hops
          - Edges with system='LLM'     → 1 hop
        This function returns the nodes that have incoming and outgoing edges from the giving list of nodes, using -(m) instead of ->(m).
        Both result sets are merged and deduplicated. This function filters out ghost nodes that do not have the properties such as embedding.
        It also excludes the code files from including as neighbours, since code files have many neighbours.
        """
        top_p = len(node_ids)
        # 2-hop traversal restricted to dataset edges only
        dataset_query = dataset_query = f"""
        MATCH (n)
        WHERE n.id IN $node_ids 
          AND n.embedding IS NOT NULL
          AND NOT 'Code' IN labels(n)

        // 1. Find all valid paths up to depth k
        MATCH p=(n)-[r*1..{k}]-(m)
        WHERE ALL(rel IN relationships(p) WHERE rel.system = 'dataset')
          AND ALL(node IN nodes(p) WHERE node.embedding IS NOT NULL)
          AND NONE(node IN tail(nodes(p)) WHERE 'Release' IN labels(node))

        // 2. Group by the starting node and slice the first 25 paths found
        WITH n, collect(p)[..$limit] AS truncated_paths

        // 3. Unwind the restricted path set and return
        UNWIND truncated_paths AS path
        RETURN 
            nodes(path)         AS nodes,
            relationships(path) AS rels
        """

        # 1-hop traversal restricted to LLM edges only
        llm_query = """
        MATCH (n)
        WHERE n.id IN $node_ids 
          AND n.embedding IS NOT NULL
          AND NOT 'Code' IN labels(n)

        // 1. Match the direct neighbors
        MATCH (n)-[r]-(m)
        WHERE r.system = 'LLM'
          AND m.embedding IS NOT NULL
          AND NOT 'Code' IN labels(m)
          AND NOT 'Release' IN labels(m)

        // 2. Sort neighbors if you want specific ones (e.g., newest first)
        WITH n, r, m
        ORDER BY m.timestamp DESC

        // 3. Group by 'n' and slice the top 25 connections
        WITH n, collect({rel: r, neighbor: m})[..$limit] AS truncated_neighborhood

        // 4. Unwind back to rows and format to match your expected 'nodes' and 'rels' output
        UNWIND truncated_neighborhood AS edge
        RETURN 
            [n, edge.neighbor] AS nodes,
            [edge.rel] AS rels
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
                        # Remove the embedding
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
                            "source id":     src,
                            "target id":     tgt,
                            "label":      label,
                        })

        results_dataset, total_nodes, total_edges, total_db_hits_dataset, db_retrieval_time_ms_dataset = self.get_neo4j_metrics(dataset_query, node_ids=node_ids, limit=30)
        results_llm, total_nodes, total_edges, total_db_hits_llm, db_retrieval_time_ms_llm = self.get_neo4j_metrics(llm_query, node_ids=node_ids, limit=20)
        _collect(results_dataset)
        _collect(results_llm)

        return all_nodes, all_edges, total_nodes, total_edges, total_db_hits_dataset + total_db_hits_llm, db_retrieval_time_ms_dataset + db_retrieval_time_ms_llm

    def query_similar_nodes(self, embedding, top_k=25):
        """
        returns the similar nodes in the graph of the passed node using vector
        indexing in Neo4j with cosine similarity. The returned list is in descending
        order
        """

        query = """
        MATCH (node:TraceabilityNode)
        SEARCH node IN (
          VECTOR INDEX node_embeddings 
          FOR $embedding 
          LIMIT $top_k
        ) SCORE AS score
        WHERE score >= 0.88
        RETURN node
        ORDER BY score DESC;
        """

        nodes = []

        results, total_nodes, total_edges, total_db_hits, db_retrieval_time_ms = self.get_neo4j_metrics(query, embedding=embedding, top_k=top_k)

        for record in results:
            node = record["node"]
            nodes.append({
                "id": node["id"],
                "type": ", ".join(node.labels),
                **dict(node)
            })
            del nodes[-1]["embedding"]

        return nodes, total_nodes, total_edges, total_db_hits, db_retrieval_time_ms
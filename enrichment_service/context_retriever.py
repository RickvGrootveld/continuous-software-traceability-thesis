from typing import List, Dict
import logging

K_HOPS = 1
MAX_CONTENT_NODES = 99999999#150
MAX_VECTOR_NODES = 99999999#30
MIN_VECTOR_NODES = 0#15


class ContextRetriever:

    def __init__(self, neo4j_client):
        self.neo4j = neo4j_client

    def deduplicate_graph_nodes(self, data: dict) -> dict:
        """
        Removes duplicate nodes across all sub-graphs, caps node counts per category,
        and removes edges referencing removed nodes.
        
        Priority:
        1. All sliding_window_events nodes (no cap)
        2. MIN_VECTOR_NODES vector nodes guaranteed
        3. Remaining budget filled with k_hop_neighbourhood nodes
        4. Up to MAX_VECTOR_NODES vector nodes if budget remains
        """
        seen_node_ids = set()
        # Deduplicate each category and remove embeddings
        deduplicated = {}  # category -> list of unique nodes
    
        for category, content in data.items():
            if "nodes" not in content:
                deduplicated[category] = []
                continue
            
            unique_nodes = []
            for node in content["nodes"]:
                # Remove embedding from sliding window nodes to save tokens
                if category == "sliding_window_events":
                    del node["embedding"] # embedding is always in node
    
                node_id = node["id"]
                if node_id not in seen_node_ids:
                    if "SOLR" in node_id or "LUCENE" in node_id:
                        summary = node.get("summary") or ""
                        if len(summary) > 500:
                            node.update({"summary": summary[:100]})

                    seen_node_ids.add(node_id)
                    unique_nodes.append(node)
    
            deduplicated[category] = unique_nodes
    
        # Apply budget                                                
        sliding_nodes  = deduplicated.get("sliding_window_events", [])
        khop_nodes     = deduplicated.get("k_hop_neighbourhood", [])
        vector_nodes   = deduplicated.get("vector_similarity_retrieval", [])
    
        # 1. Sliding window: always keep all
        kept_sliding = sliding_nodes
        budget_remaining = MAX_CONTENT_NODES - len(kept_sliding)
    
        # 2. Guarantee minimum vector nodes
        kept_vector_min  = vector_nodes[:MIN_VECTOR_NODES]
        budget_remaining -= len(kept_vector_min)
    
        # 3. Fill remainder with neighbourhood nodes
        kept_khop        = khop_nodes[:min(len(khop_nodes), max(0, budget_remaining))]
        budget_remaining -= len(kept_khop)
    
        # 4. Use leftover budget for extra vector nodes up to MAX_VECTOR_NODES
        extra_vector_budget = min(budget_remaining, MAX_VECTOR_NODES - MIN_VECTOR_NODES)
        kept_vector_extra   = vector_nodes[MIN_VECTOR_NODES:MIN_VECTOR_NODES + max(0, extra_vector_budget)]
        kept_vector         = kept_vector_min + kept_vector_extra
    
        # Build kept ID sets of all categories for edge filtering
        kept_ids = (
            {n["id"] for n in kept_sliding} |
            {n["id"] for n in kept_khop} |
            {n["id"] for n in kept_vector}
        )
    
        # Write back nodes and filter edges
        final_data = {}
        category_nodes = {
            "sliding_window_events":       kept_sliding,
            "vector_similarity_retrieval": kept_vector,
            "k_hop_neighbourhood":         kept_khop,
        }
    
        for category, content in data.items():
            kept_nodes = category_nodes.get(category, [])
            #valid_ids  = kept_ids.get(category, set())
    
            # Filter edges: both endpoints must be in kept IDs for this category
            filtered_edges = []
            for edge in content.get("edges", []):
                if edge["source id"] in kept_ids and edge["target id"] in kept_ids:
                    filtered_edges.append(edge)

            #if category == "k_hop_neighbourhood":
            #    filtered_edges = filtered_edges[:100]
            final_data[category] = {
                "nodes": kept_nodes,
                "edges": filtered_edges,
            }

        return final_data

    def retrieve_context(self, current_window: dict) -> dict:
        # Get the IDs from each node in the window
        seed_ids = [node["id"] for node in current_window["nodes"]]

        # k-hop retrieval
        neighbour_nodes, neighbour_edges, total_nodes_neighbour, total_edges_neighbour, total_db_hits_neighbour, db_retrieval_time_ms_neighbour = self.neo4j.get_k_hop_neighbors(
                seed_ids,
                k=K_HOPS
            )

        # Vector retrieval
        vector_nodes, graph_nodes_vector, graph_edges_vector, total_db_hits_vector, db_retrieval_time_ms_vector = self.find_similar_nodes(
            nodes=current_window["nodes"], # Only find the similar nodes of the nodes in the current window
            top_k=MAX_VECTOR_NODES
        )

        # Merge
        merged = {
            "sliding_window_events": {},
            "vector_similarity_retrieval": {},
            "k_hop_neighbourhood": {}
        }

        merged["sliding_window_events"] = {
            "nodes": current_window["nodes"],
            "edges": current_window["edges"]
        }
        merged["k_hop_neighbourhood"] = {
            "nodes": neighbour_nodes,
            "edges": neighbour_edges
        }
        merged["vector_similarity_retrieval"] = {
            "nodes": vector_nodes,
            "edges": []  # No edges in vector retrieval
        }

        # remove duplicates
        merged = self.deduplicate_graph_nodes(merged)

        logging.info(f"window nodes: {current_window["nodes"]}")
        logging.info(f"window edges: {current_window["edges"]}")
        logging.info(f"neighbourhood nodes: {neighbour_nodes}")
        logging.info(f"neighbourhood edges {neighbour_edges}")
        logging.info(f"vector nodes: {len(vector_nodes)}")

        metrics_data = {
            "total_nodes_neighbour": total_nodes_neighbour,
            "total_edges_neighbour": total_edges_neighbour,
            "total_db_hits_neighbour": total_db_hits_neighbour,
            "db_retrieval_time_ms_neighbour": db_retrieval_time_ms_neighbour,
            "graph_nodes_vector": graph_nodes_vector, 
            "graph_edges_vector": graph_edges_vector, 
            "total_db_hits_vector": total_db_hits_vector, 
            "db_retrieval_time_ms_vector": db_retrieval_time_ms_vector,
        }

        return merged, metrics_data
    
    def find_similar_nodes(self, nodes, top_k=50):
        similar_nodes = []
        seen = set()

        for node in nodes:
            retrieved, total_nodes, total_edges, total_db_hits, db_retrieval_time_ms = self.neo4j.query_similar_nodes(
                embedding=node["embedding"],
                top_k=top_k
            )

            # Check if the node has already been seen by another node in the list of nodes
            for retrieved_node in retrieved:
                node_id = retrieved_node["id"]
                if node_id == node["id"]:
                    continue

                if node_id in seen:
                    continue

                seen.add(node_id)
                similar_nodes.append(retrieved_node)

        return similar_nodes, total_nodes, total_edges, total_db_hits, db_retrieval_time_ms

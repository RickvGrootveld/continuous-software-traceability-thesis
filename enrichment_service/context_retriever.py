from typing import List, Dict

WINDOW_SECONDS = 10

K_HOPS = 1
MAX_VECTOR_RESULTS = 20
MAX_CONTEXT_NODES = 50


class ContextRetriever:

    def __init__(self, neo4j_client, vector_retriever):
        self.neo4j = neo4j_client
        self.vector = vector_retriever

    def deduplicate_graph_nodes(self, data: dict) -> dict:
        """Removes duplicate nodes across all sub-graphs based on their unique node IDs
        while preserving the original dictionary structure.
        """
        seen_node_ids = set()

        # Iterate through each sub-graph category (sliding_window_events, etc.)
        for category, content in data.items():
            if "nodes" not in content:
                continue
            unique_nodes = []

            for node_dict in content["nodes"]:
                # Extract the unique key/ID of the node (e.g., 'bug_302')
                node_id = next(iter(node_dict.keys()))

                # If we haven't seen this node ID yet, keep it and mark it as seen
                if node_id not in seen_node_ids:
                    seen_node_ids.add(node_id)
                    unique_nodes.append(node_dict)
            # Update the category with the deduplicated list of nodes

            data[category]["nodes"] = unique_nodes
            
        return data

    def retrieve_context(self, current_window: dict) -> dict:
        # Get the IDs from each node in the window
        seed_ids = [
            node["id"]
            for node in current_window["nodes"]
        ]

        # k-hop retrieval
        neighbour_nodes, neighbour_edges = \
            self.neo4j.get_k_hop_neighbors(
                seed_ids,
                k=K_HOPS
            )

        # Vector retrieval
        vector_nodes = self.vector.find_similar_nodes(
            nodes=current_window["nodes"], # Only find the similar nodes of the nodes in the current window
            top_k=MAX_VECTOR_RESULTS
        )
        
        # Merge
        merged = {}

        for node in (current_window["nodes"] + neighbour_nodes + vector_nodes):
            # Make sure there are no duplicates in the combined dict
            if node["id"] not in merged:
                merged[node["id"]] = node

            # Delete the embeddings to minimize the token usage
            del node["properties"]["embedding"]

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
        
        # Shorten the context to make it fit in the LLM's context window
        max_vector_nodes = max(0, MAX_CONTEXT_NODES - len(merged["k_hop_neighbourhood"]["nodes"]) + len(merged["vector_similarity_retrieval"]["nodes"]))
        merged["vector_similarity_retrieval"]["nodes"] = merged["vector_similarity_retrieval"]["nodes"][:max_vector_nodes]

        return merged 
    


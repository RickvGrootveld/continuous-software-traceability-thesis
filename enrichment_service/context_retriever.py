from typing import List, Dict

WINDOW_SECONDS = 10

K_HOPS = 2
MAX_VECTOR_RESULTS = 20
MAX_CONTEXT_NODES = 50


class ContextRetriever:

    def __init__(self, neo4j_client, vector_retriever):
        self.neo4j = neo4j_client
        self.vector = vector_retriever

    def retrieve_context(self, window_nodes: List[Dict], window_edges: List[Dict]):
        # Get the IDs from each node in the window
        seed_ids = [
            node["id"]
            for node in window_nodes
        ]

        # k-hop retrieval
        neighbour_nodes, neighbour_edges = \
            self.neo4j.get_k_hop_neighbors(
                seed_ids,
                k=K_HOPS
            )

        # Vector retrieval
        vector_nodes = self.vector.find_similar_nodes(
            nodes=window_nodes + neighbour_nodes,
            top_k=MAX_VECTOR_RESULTS
        )

        # Merge
        merged = {}

        for node in (window_nodes + neighbour_nodes + vector_nodes):
            # Make sure there are no duplicates in the combined dict
            if node["id"] not in merged:
                merged[node["id"]] = node

        # Convert to list to make it readable for LLMs
        merged_nodes = list(merged.values())

        # Shorten the context to make it fit in the LLM's context window
        merged_nodes = merged_nodes[:MAX_CONTEXT_NODES]

        edges = window_edges + neighbour_edges

        return merged_nodes, edges 
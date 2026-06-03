from sentence_transformers import SentenceTransformer

class EmbeddingService:

    def __init__(self):
        # Use MiniLM as lightweight semantic embedding model
        self.model = SentenceTransformer("all-MiniLM-L6-v2")

    def node_to_text(self, node):
        """
        Converts node JSON into semantic text.
    
        Example node input now:
        {
            "type": ["TraceabilityNode", "Issue", "Bug"],
            "id": "...",
            "properties": { ... }
        }
        """
        text_parts = []
    
        # 1. Handle the list of labels safely
        labels = node["type"]
        if isinstance(labels, list):
            # Filter out 'TraceabilityNode' to leave the specific types (e.g., ['Issue', 'Bug'])
            specific_labels = [l for l in labels if l != "TraceabilityNode"]
            # Ensure a consistent order (e.g., 'Issue:Bug')
            specific_labels.sort(reverse=True) 
            type_str = ":".join(specific_labels)
        else:
            # Fallback just in case a raw string slips through
            type_str = str(labels)
    
        # Append the clean string representation of the type
        text_parts.append(f"Type: {type_str}")
    
        # 2. Include properties
        for key, value in node["properties"].items():
            # Skip internal metrics/fields that don't add semantic value for text processing
            if value is None or key in ["id", "embedding"]:
                continue
            text_parts.append(f"{key}: {value}")
    
        return " ".join(text_parts)

    def generate_embeddings(self, nodes):
        # Convert nodes to text
        texts = [
            self.node_to_text(node)
            for node in nodes
        ]

        embeddings = self.model.encode(texts)

        # Attach embeddings to nodes
        for node, embedding in zip(nodes, embeddings):
            node["properties"]["embedding"] = embedding.tolist()

        return nodes
    

class VectorSimilarityRetriever:

    def __init__(self, neo4j_client):
        self.neo4j = neo4j_client

        # Same model as KG service
        self.model = SentenceTransformer(
            "all-MiniLM-L6-v2"
        )

    def find_similar_nodes(self, nodes, top_k=50):
        similar_nodes = []
        seen = set()

        for node in nodes:
            retrieved = self.neo4j.query_similar_nodes(
                embedding=node["properties"]["embedding"],
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

        return similar_nodes
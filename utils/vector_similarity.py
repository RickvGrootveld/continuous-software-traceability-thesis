from sentence_transformers import SentenceTransformer


class EmbeddingService:

    def __init__(self):
        # Use MiniLM as lightweight semantic embedding model
        self.model = SentenceTransformer("all-MiniLM-L6-v2")

    # =====================================================
    # Convert node into semantic text
    # =====================================================

    def node_to_text(self, node):
        """
        Converts node JSON into semantic text.

        Example node:
        {
            "type": "Commit",
            "id": "...",
            "properties": {
                "message": "...",
                "committed_date": "..."
            }
        }
        """
        text_parts = []

        # Include node type
        text_parts.append(node["type"])

        # Include properties
        for key, value in node["properties"].items():
            if value is None:
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
            node["embedding"] = embedding.tolist()

        return nodes
    

class VectorSimilarityRetriever:

    def __init__(self, neo4j_client):
        self.neo4j = neo4j_client

        # Same model as KG service
        self.model = SentenceTransformer(
            "all-MiniLM-L6-v2"
        )

    def node_to_text(self, node):
        text_parts = []
        text_parts.append(node["type"])

        for key, value in node["properties"].items():
            if value is None:
                continue

            # Skip embedding itself
            if key == "embedding":
                continue

            text_parts.append(f"{key}: {value}")

        return " ".join(text_parts)

    def generate_embedding(self, node):
        text = self.node_to_text(node)
        embedding = self.model.encode(text)
        return embedding.tolist()

    def find_similar_nodes(self, nodes, top_k=20):
        similar_nodes = []
        seen = set()

        for node in nodes:
            embedding = self.generate_embedding(node)
            retrieved = self.neo4j.query_similar_nodes(
                embedding=embedding,
                top_k=top_k
            )

            for retrieved_node in retrieved:
                node_id = retrieved_node["id"]
                if node_id == node["id"]:
                    continue

                if node_id in seen:
                    continue

                seen.add(node_id)
                similar_nodes.append(retrieved_node)

        return similar_nodes
import os
from neo4j import GraphDatabase

URI = "bolt://neo4j:7687"
AUTH = ("neo4j", "password") #tuple(os.getenv('NEO4J_AUTH').split('/'))


class KnowledgeGraph:
    def __init__(self):
        self.driver = GraphDatabase.driver(URI, auth=AUTH)

    def close(self):
        self.driver.close()

def insert_nodes(tx, nodes: list):
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
    tx.run(query, nodes=nodes)

def link_nodes_original(tx, edges: list):
    query = """
    UNWIND $edges AS edge
    MATCH (a {id: edge.source})
    MATCH (b {id: edge.target})

    CALL apoc.merge.relationship(
      a,
      edge.label,
      {},
      edge.properties,
      b
    ) 
    YIELD rel
    RETURN count(rel)
    """
    tx.run(query, edges=edges)

def link_nodes_hybrid(tx, edges: list):
    query = """
    UNWIND $edges AS edge
    WITH edge
    WHERE edge.source IS NOT NULL 
      AND edge.target IS NOT NULL 
      AND edge.label IS NOT NULL

    // Extract type + id
    WITH edge,
         split(edge.source, ':') AS sourceParts,
         split(edge.target, ':') AS targetParts

    MERGE (a {id: edge.source})
    ON CREATE SET a:Unknown

    MERGE (b {id: edge.target})
    ON CREATE SET b:Unknown

    CALL apoc.merge.relationship(
      a,
      edge.label,
      {},
      {},
      b
    ) YIELD rel

    SET rel += edge.properties

    RETURN count(rel)
    """
    tx.run(query, edges=edges)

def link_nodes(tx, edges: list):
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
    tx.run(query, edges=edges)
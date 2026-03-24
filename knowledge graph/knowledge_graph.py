import os
from neo4j import GraphDatabase

URI = "bolt://neo4j:7687"
AUTH = os.getenv('DB_AUTH')


class KnowledgeGraph:
    def __init__(self):
        self.driver = GraphDatabase.driver(URI, AUTH)

    def close(self):
        self.driver.close()


#def update_into_neo4j(tx, record):
#    label = record.get("event_type")
#    query = """
#    MERGE (n:{label} {id: $id})
#    SET n += $props
#    """
#    tx.run(query, id=record.get("id"), props=record)
#
#def delete_from_neo4j(tx, record_id):
#    label = record_id.get("event_type")
#    query = """
#    MATCH (n:{label} {id: $id})
#    DETACH DELETE n
#    """
#    tx.run(query, id=record_id)
#
#def insert_into_neo4j(tx, label, id_key, properties):
#    query = """
#    MERGE (n:{label} {{{id_key}: $props.{id_key}}})
#    SET n += $props
#    """
#    tx.run(query, props=properties)

# expects that there are no NULL types
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
    SET n += node.properties
    """
    tx.run(query, nodes=nodes)

def link_nodes(tx, edges: list):
    query = """
    UNWIND $edges AS edge
    MATCH (a {id: edge.source})
    MATCH (b {id: edge.target})

    CALL apoc.merge.relationship(
      a,
      edge.label,
      {},
      {},
      b
    ) 
    YIELD rel
    SET rel += edge.properties

    RETURN count(rel)
    """
    tx.run(query, edges=edges)
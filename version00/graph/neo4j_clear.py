"""
Clear Neo4j Database
Simple script to wipe all nodes and relationships
"""
from neo4j import GraphDatabase

# Connection
uri = "bolt://localhost:7687"
user = "neo4j"
password = "123456789"

driver = GraphDatabase.driver(uri, auth=(user, password))

with driver.session() as session:
    # Delete everything
    session.run("MATCH (n) DETACH DELETE n")
    print("✓ Database cleared")

driver.close()

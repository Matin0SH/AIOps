"""
Check Neo4j database contents
"""
from neo4j import GraphDatabase

uri = "bolt://localhost:7687"
user = "neo4j"
password = "123456789"

driver = GraphDatabase.driver(uri, auth=(user, password))

with driver.session() as session:
    # Count nodes
    result = session.run("MATCH (n) RETURN labels(n) as label, count(n) as count")
    print("=== NODES ===")
    for record in result:
        print(f"  {record['label'][0]}: {record['count']}")

    # Count relationships
    result = session.run("MATCH ()-[r]->() RETURN type(r) as type, count(r) as count")
    print("\n=== RELATIONSHIPS ===")
    for record in result:
        print(f"  {record['type']}: {record['count']}")

    # Show devices
    result = session.run("MATCH (d:Device) RETURN d.hostname, d.type, d.ip_address")
    print("\n=== DEVICES ===")
    for record in result:
        print(f"  {record['d.hostname']} ({record['d.type']}) - {record['d.ip_address']}")

print()  # Extra newline before close
driver.close()

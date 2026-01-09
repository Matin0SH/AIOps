"""
Clear all data from Neo4j graph database
"""
from pathlib import Path
import yaml
from neo4j import GraphDatabase


def load_yaml(file_path):
    with open(file_path, 'r') as f:
        return yaml.safe_load(f)


# Load Neo4j config
config_dir = Path(__file__).parent / 'config'
neo4j_cfg = load_yaml(config_dir / 'neo4j.yaml')['connection']

driver = GraphDatabase.driver(
    neo4j_cfg['uri'],
    auth=(neo4j_cfg['user'], neo4j_cfg['password'])
)

print("="*70)
print("CLEARING NEO4J DATABASE")
print("="*70)

with driver.session() as session:
    # Delete all nodes and relationships
    print("\n[1] Deleting all nodes and relationships...")
    result = session.run("MATCH (n) DETACH DELETE n")
    print("[OK] Database cleared")

    # Verify
    print("\n[2] Verifying...")
    result = session.run("MATCH (n) RETURN count(n) as count")
    count = result.single()['count']
    print(f"[OK] Remaining nodes: {count}")

driver.close()

print("\n" + "="*70)
print("DATABASE CLEARED SUCCESSFULLY")
print("="*70)

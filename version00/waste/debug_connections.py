"""
Debug script to understand CDP connection patterns in Neo4j
"""
from pathlib import Path
import yaml
from neo4j import GraphDatabase


def load_yaml(file_path):
    with open(file_path, 'r') as f:
        return yaml.safe_load(f)


# Load Neo4j config
config_dir = Path(__file__).parent / 'graph' / 'config'
neo4j_cfg = load_yaml(config_dir / 'neo4j.yaml')['connection']

driver = GraphDatabase.driver(
    neo4j_cfg['uri'],
    auth=(neo4j_cfg['user'], neo4j_cfg['password'])
)

print("="*70)
print("DEBUGGING CDP CONNECTIONS")
print("="*70)

with driver.session() as session:
    # 1. Check all relationship types
    print("\n[1] ALL RELATIONSHIP TYPES:")
    result = session.run("CALL db.relationshipTypes()")
    for record in result:
        print(f"  - {record[0]}")

    # 2. Count CONNECTED_TO relationships
    print("\n[2] COUNT OF CONNECTED_TO RELATIONSHIPS:")
    result = session.run("MATCH ()-[r:CONNECTED_TO]->() RETURN count(r) as count")
    count = result.single()['count']
    print(f"  Total: {count}")

    # 3. Sample CONNECTED_TO relationships
    print("\n[3] SAMPLE CONNECTED_TO RELATIONSHIPS (first 5):")
    result = session.run("""
        MATCH (i1:Interface)-[r:CONNECTED_TO]->(i2:Interface)
        RETURN i1.id, i1.name, r.protocol, i2.id, i2.name
        LIMIT 5
    """)
    for record in result:
        print(f"  {record['i1.id']} ({record['i1.name']}) --[{record['r.protocol']}]--> {record['i2.id']} ({record['i2.name']})")

    # 4. Check CORE-SW1 interfaces
    print("\n[4] CORE-SW1 INTERFACES:")
    result = session.run("""
        MATCH (d:Device {hostname: 'CORE-SW1'})-[:HAS_INTERFACE]->(i:Interface)
        RETURN i.id, i.name, i.status
        LIMIT 10
    """)
    for record in result:
        print(f"  - {record['i.id']} | {record['i.name']} | {record['i.status']}")

    # 5. Check if CORE-SW1 interfaces have CONNECTED_TO relationships
    print("\n[5] CORE-SW1 INTERFACES WITH CONNECTIONS:")
    result = session.run("""
        MATCH (d:Device {hostname: 'CORE-SW1'})-[:HAS_INTERFACE]->(i:Interface)
        OPTIONAL MATCH (i)-[r:CONNECTED_TO]->(i2:Interface)
        RETURN i.id, i.name, r.protocol, i2.id, i2.name
        LIMIT 10
    """)
    for record in result:
        if record['r.protocol']:
            print(f"  ✓ {record['i.id']} --[{record['r.protocol']}]--> {record['i2.id']}")
        else:
            print(f"  ✗ {record['i.id']} (no connection)")

    # 6. Check bidirectional - incoming connections to CORE-SW1
    print("\n[6] INCOMING CONNECTIONS TO CORE-SW1:")
    result = session.run("""
        MATCH (d:Device {hostname: 'CORE-SW1'})-[:HAS_INTERFACE]->(i:Interface)
        MATCH (i2:Interface)-[r:CONNECTED_TO]->(i)
        RETURN i2.id, i2.name, r.protocol, i.id, i.name
        LIMIT 10
    """)
    count = 0
    for record in result:
        print(f"  {record['i2.id']} --[{record['r.protocol']}]--> {record['i.id']}")
        count += 1
    if count == 0:
        print("  (none)")

    # 7. Check all connections involving CORE-SW1 (either direction)
    print("\n[7] ALL CONNECTIONS INVOLVING CORE-SW1 (BIDIRECTIONAL):")
    result = session.run("""
        MATCH (d:Device {hostname: 'CORE-SW1'})-[:HAS_INTERFACE]->(i:Interface)
        MATCH (i)-[r:CONNECTED_TO]-(i2:Interface)
        RETURN i.id, i.name, r.protocol, i2.id, i2.name
        LIMIT 10
    """)
    count = 0
    for record in result:
        print(f"  {record['i.id']} <--[{record['r.protocol']}]--> {record['i2.id']}")
        count += 1
    if count == 0:
        print("  (none)")

driver.close()

print("\n" + "="*70)
print("DEBUG COMPLETE")
print("="*70)

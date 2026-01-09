"""
Create Simple Graph in Neo4j
Just creates EDGE-R1 router node with basic properties
"""
from neo4j import GraphDatabase

# Connection
uri = "bolt://localhost:7687"
user = "neo4j"
password = "123456789"

driver = GraphDatabase.driver(uri, auth=(user, password))

with driver.session() as session:
    # Create EDGE-R1 router
    session.run("""
        CREATE (r:Device {
            hostname: 'EDGE-R1',
            type: 'router',
            ip: '10.10.10.1',
            ospf_rid: '1.1.1.1'
        })
    """)
    print("✓ Created EDGE-R1 router")

    # Create some interfaces
    session.run("""
        MATCH (r:Device {hostname: 'EDGE-R1'})
        CREATE (i1:Interface {
            id: 'EDGE-R1:GigabitEthernet0/0',
            name: 'GigabitEthernet0/0',
            ip: 'unassigned',
            status: 'up',
            protocol: 'up'
        })
        CREATE (i2:Interface {
            id: 'EDGE-R1:GigabitEthernet0/0.10',
            name: 'GigabitEthernet0/0.10',
            ip: '10.10.10.1',
            status: 'up',
            protocol: 'up'
        })
        CREATE (i3:Interface {
            id: 'EDGE-R1:Loopback0',
            name: 'Loopback0',
            ip: '1.1.1.1',
            status: 'up',
            protocol: 'up'
        })
        CREATE (r)-[:HAS_INTERFACE]->(i1)
        CREATE (r)-[:HAS_INTERFACE]->(i2)
        CREATE (r)-[:HAS_INTERFACE]->(i3)
    """)
    print("✓ Created 3 interfaces")

    # Count nodes
    result = session.run("MATCH (n) RETURN count(n) as count")
    count = result.single()['count']
    print(f"✓ Total nodes: {count}")

driver.close()
print("\nDone! Open Neo4j Browser and run: MATCH (n) RETURN n")

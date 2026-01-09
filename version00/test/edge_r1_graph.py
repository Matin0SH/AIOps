"""
EDGE-R1 Graph Builder
Fetches live data from EDGE-R1 router and populates Neo4j
"""
from neo4j import GraphDatabase
from collectors.router_collector import RouterCollector
import time

# Neo4j connection
uri = "bolt://localhost:7687"
user = "neo4j"
password = "123456789"

# Device credentials
creds = {"username": "", "password": "", "enable_secret": "cisco"}

print("=" * 60)
print("EDGE-R1 GRAPH BUILDER")
print("=" * 60)

# Connect to Neo4j
print("\n[1] Connecting to Neo4j...")
driver = GraphDatabase.driver(uri, auth=(user, password))
print("[OK] Neo4j connected")

# Connect to EDGE-R1
print("\n[2] Connecting to EDGE-R1...")
edge = RouterCollector("EDGE-R1", "192.168.56.101", 5008, creds)
edge.connect()
print("[OK] Connected to EDGE-R1")

# Fetch data
print("\n[3] Fetching interface data...")
time.sleep(2)
interfaces = edge.get_interface_brief()
print(f"[OK] Got {len(interfaces)} interfaces")
print("INTERFACES DATA:")
for iface in interfaces:
    print(f"  {iface}")

print("\n[4] Fetching CDP neighbors...")
time.sleep(2)
cdp = edge.get_cdp_neighbors()
print(f"[OK] Got {len(cdp)} CDP neighbors")
print("CDP DATA:")
for neighbor in cdp:
    print(f"  {neighbor}")

print("\n[5] Fetching OSPF neighbors...")
time.sleep(2)
ospf = edge.get_ospf_neighbors()
print(f"[OK] Got {len(ospf)} OSPF neighbors")
print("OSPF DATA:")
for neighbor in ospf:
    print(f"  {neighbor}")

# Create nodes in Neo4j
print("\n[6] Creating EDGE-R1 device node...")
with driver.session() as session:
    # Create Device node
    session.run("""
        MERGE (d:Device {hostname: $hostname})
        SET d.type = $type,
            d.ip_address = $ip_address,
            d.model = $model,
            d.os_version = $os_version
    """, {
        'hostname': 'EDGE-R1',
        'type': 'router',
        'ip_address': '10.10.10.1',
        'model': 'IOSv',
        'os_version': '15.6'
    })
    print("[OK] Device node created")

    # Create Interface nodes
    print(f"\n[7] Creating {len(interfaces)} interface nodes...")
    for iface in interfaces:
        iface_id = f"EDGE-R1:{iface['interface']}"
        session.run("""
            MATCH (d:Device {hostname: $hostname})
            MERGE (i:Interface {id: $iface_id})
            SET i.name = $name,
                i.ip_address = $ip_address,
                i.status = $status,
                i.protocol = $protocol,
                i.description = $description
            MERGE (d)-[:HAS_INTERFACE]->(i)
        """, {
            'hostname': 'EDGE-R1',
            'iface_id': iface_id,
            'name': iface['interface'],
            'ip_address': iface.get('ip_address', 'unassigned'),
            'status': iface.get('status', 'unknown'),
            'protocol': iface.get('protocol', 'unknown'),
            'description': iface.get('description', '')
        })
    print(f"[OK] Created {len(interfaces)} interface nodes")

    # Create CDP relationships
    print(f"\n[8] Creating {len(cdp)} CDP relationships...")
    for neighbor in cdp:
        if 'local_interface' in neighbor and 'neighbor_interface' in neighbor and 'neighbor_device' in neighbor:
            local_iface_id = f"EDGE-R1:{neighbor['local_interface']}"
            remote_host = neighbor['neighbor_device'].split('.')[0]
            remote_iface_id = f"{remote_host}:{neighbor['neighbor_interface']}"

            session.run("""
                MATCH (local:Interface {id: $local_iface_id})
                MERGE (remote:Interface {id: $remote_iface_id})
                MERGE (local)-[r:CONNECTED_TO]->(remote)
                SET r.protocol = 'CDP'
            """, {
                'local_iface_id': local_iface_id,
                'remote_iface_id': remote_iface_id
            })
    print(f"[OK] Created {len(cdp)} CDP relationships")

    # Create OSPF relationships
    print(f"\n[9] Creating {len(ospf)} OSPF relationships...")
    # Map OSPF Router IDs (loopback IPs) to hostnames
    ospf_id_to_hostname = {
        '1.1.1.1': 'EDGE-R1',
        '2.2.2.2': 'CORE-SW1',
        '3.3.3.3': 'CORE-SW2'
    }

    for neighbor in ospf:
        neighbor_id = neighbor.get('neighbor_id', 'unknown')
        neighbor_hostname = ospf_id_to_hostname.get(neighbor_id, neighbor_id)

        session.run("""
            MATCH (d:Device {hostname: $hostname})
            MERGE (n:Device {hostname: $neighbor_hostname})
            MERGE (d)-[r:OSPF_NEIGHBOR]->(n)
            SET r.state = $state,
                r.priority = $priority,
                r.dr_ip = $dr_ip,
                r.bdr_ip = $bdr_ip,
                r.neighbor_id = $neighbor_id
        """, {
            'hostname': 'EDGE-R1',
            'neighbor_hostname': neighbor_hostname,
            'neighbor_id': neighbor_id,
            'state': neighbor.get('state', 'unknown'),
            'priority': neighbor.get('priority', 0),
            'dr_ip': neighbor.get('dr_ip', '0.0.0.0'),
            'bdr_ip': neighbor.get('bdr_ip', '0.0.0.0')
        })
    print(f"[OK] Created {len(ospf)} OSPF relationships")

# Check database stats
print("\n[10] Checking database stats...")
with driver.session() as session:
    result = session.run("""
        MATCH (n)
        RETURN count(n) as nodes
    """)
    node_count = result.single()['nodes']

    result = session.run("""
        MATCH ()-[r]->()
        RETURN count(r) as relationships
    """)
    rel_count = result.single()['relationships']

    print(f"[OK] Total nodes: {node_count}")
    print(f"[OK] Total relationships: {rel_count}")

# Cleanup
edge.disconnect()
print("\n" + "=" * 60)
print("EDGE-R1 GRAPH BUILD COMPLETE")
print("=" * 60)

driver.close()


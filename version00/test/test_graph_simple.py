"""
Simple test to debug graph building issues
Tests each step individually with detailed error output
"""
from graph.neo4j_connector import Neo4jConnector
from collectors.switch_collector import SwitchCollector
from collectors.router_collector import RouterCollector
import traceback

print("=" * 80)
print("GRAPH BUILDER DEBUG TEST")
print("=" * 80)

# Connect to Neo4j
print("\n[1] Connecting to Neo4j...")
try:
    db = Neo4jConnector(
        uri="bolt://localhost:7687",
        user="neo4j",
        password="123456789"
    )
    print("✓ Neo4j connected")
    db.clear_database()
    print("✓ Database cleared")
except Exception as e:
    print(f"✗ Neo4j connection failed: {e}")
    exit(1)

# Test device connection
print("\n[2] Testing device connection...")
creds = {"username": "", "password": "", "enable_secret": "cisco"}

try:
    device = SwitchCollector("CORE-SW1", "192.168.56.101", 5012, creds)
    device.connect()
    print("✓ Connected to CORE-SW1")
except Exception as e:
    print(f"✗ Device connection failed: {e}")
    traceback.print_exc()
    exit(1)

# Test get_interface_brief
print("\n[3] Testing get_interface_brief()...")
try:
    interfaces = device.get_interface_brief()
    print(f"✓ Got {len(interfaces)} interfaces")
    print(f"  Sample: {interfaces[0]}")
except Exception as e:
    print(f"✗ get_interface_brief failed: {e}")
    traceback.print_exc()

# Test get_cdp_neighbors
print("\n[4] Testing get_cdp_neighbors()...")
try:
    cdp = device.get_cdp_neighbors()
    print(f"✓ Got {len(cdp)} CDP neighbors")
    if cdp:
        print(f"  Sample: {cdp[0]}")
except Exception as e:
    print(f"✗ get_cdp_neighbors failed: {e}")
    traceback.print_exc()

# Test get_ospf_neighbors
print("\n[5] Testing get_ospf_neighbors()...")
try:
    ospf = device.get_ospf_neighbors()
    print(f"✓ Got {len(ospf)} OSPF neighbors")
    if ospf:
        print(f"  Sample: {ospf[0]}")
except Exception as e:
    print(f"✗ get_ospf_neighbors failed: {e}")
    traceback.print_exc()

# Test get_vlan_brief
print("\n[6] Testing get_vlan_brief()...")
try:
    vlans = device.get_vlan_brief()
    print(f"✓ Got {len(vlans)} VLANs")
    if vlans:
        print(f"  Sample: {vlans[0]}")
except Exception as e:
    print(f"✗ get_vlan_brief failed: {e}")
    traceback.print_exc()

# Test get_trunk_interfaces
print("\n[7] Testing get_trunk_interfaces()...")
try:
    trunks = device.get_trunk_interfaces()
    print(f"✓ Got {len(trunks)} trunk interfaces")
    if trunks:
        print(f"  Sample: {trunks[0]}")
except Exception as e:
    print(f"✗ get_trunk_interfaces failed: {e}")
    traceback.print_exc()

# Test get_mac_address_table
print("\n[8] Testing get_mac_address_table()...")
try:
    macs = device.get_mac_address_table()
    print(f"✓ Got {len(macs)} MAC addresses")
    if macs:
        print(f"  Sample: {macs[0]}")
except Exception as e:
    print(f"✗ get_mac_address_table failed: {e}")
    traceback.print_exc()

# Test get_spanning_tree_summary
print("\n[9] Testing get_spanning_tree_summary()...")
try:
    stp = device.get_spanning_tree_summary()
    print(f"✓ Got STP summary")
    print(f"  Config keys: {list(stp['config'].keys())}")
    print(f"  VLAN stats: {len(stp['vlan_stats'])} VLANs")
except Exception as e:
    print(f"✗ get_spanning_tree_summary failed: {e}")
    traceback.print_exc()

# Now test creating nodes in Neo4j
print("\n[10] Testing Neo4j node creation...")
try:
    query = """
    MERGE (d:Device {hostname: $hostname})
    SET d.ip_address = $ip_address
    """
    db.execute_write(query, {
        'hostname': 'CORE-SW1',
        'ip_address': '10.10.10.2'
    })
    print("✓ Created Device node")
except Exception as e:
    print(f"✗ Node creation failed: {e}")
    traceback.print_exc()

# Test creating interface nodes
print("\n[11] Testing Interface node creation...")
try:
    for iface in interfaces[:2]:  # Just test first 2
        iface_id = f"CORE-SW1:{iface['interface']}"
        query = """
        MATCH (d:Device {hostname: $hostname})
        MERGE (i:Interface {id: $iface_id})
        SET i.name = $name,
            i.ip_address = $ip_address,
            i.status = $status
        MERGE (d)-[:HAS_INTERFACE]->(i)
        """
        db.execute_write(query, {
            'hostname': 'CORE-SW1',
            'iface_id': iface_id,
            'name': iface['interface'],
            'ip_address': iface['ip_address'],
            'status': iface['status']
        })
    print(f"✓ Created Interface nodes and relationships")
except Exception as e:
    print(f"✗ Interface creation failed: {e}")
    traceback.print_exc()

# Check what's in the database
print("\n[12] Checking database contents...")
try:
    stats = db.get_stats()
    print(f"✓ Database stats:")
    print(f"  Total nodes: {stats['nodes']}")
    print(f"  Total relationships: {stats['relationships']}")
    print(f"  Node types: {stats['node_labels']}")
    print(f"  Relationship types: {stats['relationship_types']}")
except Exception as e:
    print(f"✗ Stats retrieval failed: {e}")
    traceback.print_exc()

# Cleanup
device.disconnect()
db.close()

print("\n" + "=" * 80)
print("DEBUG TEST COMPLETE")
print("=" * 80)

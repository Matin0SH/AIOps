"""
ACC-SW1 Graph Builder
Fetches live data from ACC-SW1 switch and populates Neo4j
"""
from neo4j import GraphDatabase
from collectors.switch_collector import SwitchCollector
import time

# Neo4j connection
uri = "bolt://localhost:7687"
user = "neo4j"
password = "123456789"

# Device credentials
creds = {"username": "", "password": "", "enable_secret": "cisco"}

print("=" * 60)
print("ACC-SW1 GRAPH BUILDER")
print("=" * 60)

# Connect to Neo4j
print("\n[1] Connecting to Neo4j...")
driver = GraphDatabase.driver(uri, auth=(user, password))
print("[OK] Neo4j connected")

# Connect to ACC-SW1
print("\n[2] Connecting to ACC-SW1...")
device = SwitchCollector("ACC-SW1", "192.168.56.101", 5016, creds)
device.connect()
print("[OK] Connected to ACC-SW1")

# Fetch data
print("\n[3] Fetching interface data...")
time.sleep(2)
interfaces = device.get_interface_brief()
print(f"[OK] Got {len(interfaces)} interfaces")
print("INTERFACES DATA:")
for iface in interfaces:
    print(f"  {iface}")

print("\n[4] Fetching CDP neighbors...")
time.sleep(2)
cdp = device.get_cdp_neighbors()
print(f"[OK] Got {len(cdp)} CDP neighbors")
print("CDP DATA:")
for neighbor in cdp:
    print(f"  {neighbor}")

print("\n[5] Fetching VLAN data...")
time.sleep(2)
vlans = device.get_vlan_brief()
print(f"[OK] Got {len(vlans)} VLANs")
print("VLAN DATA:")
for vlan in vlans:
    print(f"  {vlan}")

print("\n[6] Fetching trunk interfaces...")
time.sleep(2)
trunks = device.get_trunk_interfaces()
print(f"[OK] Got {len(trunks)} trunk interfaces")
print("TRUNK DATA:")
for trunk in trunks:
    print(f"  {trunk}")

print("\n[7] Fetching MAC address table...")
time.sleep(2)
macs = device.get_mac_address_table()
print(f"[OK] Got {len(macs)} MAC addresses")
print("MAC DATA (first 5):")
for mac in macs[:5]:
    print(f"  {mac}")

print("\n[8] Fetching spanning tree data...")
time.sleep(2)
stp = device.get_spanning_tree_summary()
print(f"[OK] Got STP data for {len(stp['vlan_stats'])} VLANs")
print("STP DATA:")
print(f"  Config: {stp['config']}")
print(f"  VLAN Stats (first 3): {stp['vlan_stats'][:3]}")

# Create nodes in Neo4j
print("\n[9] Creating ACC-SW1 device node...")
with driver.session() as session:
    # Create Device node
    session.run("""
        MERGE (d:Device {hostname: $hostname})
        SET d.type = $type,
            d.ip_address = $ip_address,
            d.model = $model,
            d.os_version = $os_version
    """, {
        'hostname': 'ACC-SW1',
        'type': 'switch',
        'ip_address': '10.10.20.2',
        'model': 'IOSv',
        'os_version': '15.2'
    })
    print("[OK] Device node created")

    # Create Interface nodes
    print(f"\n[10] Creating {len(interfaces)} interface nodes...")
    for iface in interfaces:
        iface_id = f"ACC-SW1:{iface['interface']}"
        session.run("""
            MATCH (d:Device {hostname: $hostname})
            MERGE (i:Interface {id: $iface_id})
            SET i.name = $name,
                i.ip_address = $ip_address,
                i.status = $status,
                i.protocol = $protocol,
                i.vlan = $vlan,
                i.duplex = $duplex,
                i.speed = $speed,
                i.type = $type
            MERGE (d)-[:HAS_INTERFACE]->(i)
        """, {
            'hostname': 'ACC-SW1',
            'iface_id': iface_id,
            'name': iface['interface'],
            'ip_address': iface.get('ip_address', 'unassigned'),
            'status': iface.get('status', 'unknown'),
            'protocol': iface.get('protocol', 'unknown'),
            'vlan': iface.get('vlan', 'none'),
            'duplex': iface.get('duplex', 'auto'),
            'speed': iface.get('speed', 'auto'),
            'type': iface.get('type', 'unknown')
        })
    print(f"[OK] Created {len(interfaces)} interface nodes")

    # Create VLAN nodes
    print(f"\n[11] Creating {len(vlans)} VLAN nodes...")
    for vlan in vlans:
        session.run("""
            MERGE (v:VLAN {id: $vlan_id})
            SET v.name = $name,
                v.status = $status
        """, {
            'vlan_id': vlan['vlan_id'],
            'name': vlan.get('name', 'unknown'),
            'status': vlan.get('status', 'active')
        })
    print(f"[OK] Created {len(vlans)} VLAN nodes")

    # Create trunk relationships
    print(f"\n[12] Creating trunk VLAN relationships...")
    trunk_count = 0
    for trunk in trunks:
        if "port" not in trunk:
            continue
        iface_id = f"ACC-SW1:{trunk['port']}"
        session.run("""
            MATCH (i:Interface {id: $iface_id})
            SET i.mode = $mode,
                i.encapsulation = $encapsulation,
                i.trunk_status = $status,
                i.native_vlan = $native_vlan,
                i.vlans_allowed = $vlans_allowed,
                i.vlans_active = $vlans_active,
                i.vlans_forwarding = $vlans_forwarding
        """, {
            'iface_id': iface_id,
            'mode': trunk.get('mode', ''),
            'encapsulation': trunk.get('encapsulation', ''),
            'status': trunk.get('status', ''),
            'native_vlan': trunk.get('native_vlan', ''),
            'vlans_allowed': trunk.get('vlans_allowed', ''),
            'vlans_active': trunk.get('vlans_active', ''),
            'vlans_forwarding': trunk.get('vlans_forwarding', '')
        })
        allowed_vlans = trunk.get("vlans_allowed", "")
        for vlan_id in allowed_vlans.split(","):
            vlan_id = vlan_id.strip()
            if not vlan_id:
                continue
            session.run("""
                MATCH (i:Interface {id: $iface_id})
                MATCH (v:VLAN {id: $vlan_id})
                MERGE (i)-[r:TRUNKS_VLAN]->(v)
            """, {
                'iface_id': iface_id,
                'vlan_id': str(vlan_id)
            })
            trunk_count += 1
    print(f"[OK] Created {trunk_count} trunk relationships")

    # Create MAC address nodes
    print(f"\n[13] Creating {len(macs)} MAC address nodes...")
    for mac in macs:
        session.run("""
            MERGE (m:MACAddress {address: $mac_address})
            SET m.type = $type
        """, {
            'mac_address': mac['mac_address'],
            'type': mac.get('type', 'dynamic')
        })

        # Link MAC to interface
        port = mac.get("port")
        if not port:
            continue
        iface_id = f"ACC-SW1:{port}"
        session.run("""
            MATCH (m:MACAddress {address: $mac_address})
            MATCH (i:Interface {id: $iface_id})
            MERGE (m)-[r:LEARNED_ON]->(i)
            SET r.vlan = $vlan
        """, {
            'mac_address': mac['mac_address'],
            'iface_id': iface_id,
            'vlan': mac.get('vlan', 'unknown')
        })
    print(f"[OK] Created {len(macs)} MAC address nodes and relationships")

    # Create CDP relationships
    print(f"\n[14] Creating {len(cdp)} CDP relationships...")
    for neighbor in cdp:
        if 'local_interface' in neighbor and 'neighbor_interface' in neighbor and 'neighbor_device' in neighbor:
            local_iface_id = f"ACC-SW1:{neighbor['local_interface']}"
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

# Check database stats
print("\n[15] Checking database stats...")
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
device.disconnect()
print("\n" + "=" * 60)
print("ACC-SW1 GRAPH BUILD COMPLETE")
print("=" * 60)

driver.close()


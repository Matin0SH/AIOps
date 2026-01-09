"""
Feed Existing JSON Snapshot to Neo4j
Usage: python feed_snapshot.py <path_to_json_file>
"""
import json
import sys
from pathlib import Path

try:
    from .base import GraphClient
except ImportError:
    from base import GraphClient


def load_snapshot(json_file):
    """Load JSON snapshot file"""
    with open(json_file, 'r') as f:
        return json.load(f)


def feed_to_neo4j(network_data):
    """Feed network snapshot to Neo4j - Two-Phase Approach."""
    snapshot_id = network_data['snapshot_id']

    with GraphClient() as client:
        with client.session() as session:
            # ==================== PHASE 0: CREATE SNAPSHOT NODE ====================
            session.run("""
                CREATE (s:Snapshot {
                    id: $snapshot_id,
                    timestamp: datetime($snapshot_id),
                    device_count: $device_count
                })
            """, {
                'snapshot_id': snapshot_id,
                'device_count': len(network_data['devices'])
            })

            # ==================== PHASE 1: CREATE NODES ====================
            # Create all interfaces with properties
            interfaces_payload = []
            for device_data in network_data['devices']:
                hostname = device_data['hostname']
                for iface in device_data['interfaces']:
                    interfaces_payload.append({
                        'hostname': hostname,
                        'iface_id': f"{hostname}:{iface['interface']}",
                        'name': iface['interface'],
                        'ip_address': iface.get('ip_address', ''),
                        'ok': iface.get('ok', ''),
                        'method': iface.get('method', ''),
                        'status': iface.get('status', ''),
                        'protocol': iface.get('protocol', ''),
                        'snapshot_id': snapshot_id
                    })

            session.run("""
                UNWIND $interfaces AS iface
                MATCH (d:Device {hostname: iface.hostname})
                MERGE (i:Interface {id: iface.iface_id})
                SET i.name = iface.name,
                    i.ip_address = iface.ip_address,
                    i.ok = iface.ok,
                    i.method = iface.method,
                    i.status = iface.status,
                    i.protocol = iface.protocol,
                    i.snapshot_id = iface.snapshot_id
                MERGE (d)-[:HAS_INTERFACE]->(i)
            """, {"interfaces": interfaces_payload})

            # Store extra data as device properties (VLANs, MACs, STP, Trunks)
            switch_payload = []
            for device_data in network_data['devices']:
                if device_data['type'] == 'switch':
                    hostname = device_data['hostname']

                    switch_payload.append({
                        'hostname': hostname,
                        'vlans': json.dumps(device_data.get('vlans', [])),
                        'macs': json.dumps(device_data.get('mac_addresses', [])),
                        'stp': json.dumps(device_data.get('spanning_tree', {})),
                        'trunks': json.dumps(device_data.get('trunks', [])),
                        'snapshot_id': snapshot_id
                    })

            session.run("""
                UNWIND $switches AS sw
                MATCH (d:Device {hostname: sw.hostname})
                SET d.vlans = sw.vlans,
                    d.mac_addresses = sw.macs,
                    d.spanning_tree = sw.stp,
                    d.trunks = sw.trunks,
                    d.snapshot_id = sw.snapshot_id
            """, {"switches": switch_payload})

            # ==================== PHASE 2: CREATE RELATIONSHIPS ====================
            # Build interface lookup: (hostname, interface_name) -> interface_data
            iface_by_name = {}
            for device_data in network_data['devices']:
                hostname = device_data['hostname']
                for iface in device_data['interfaces']:
                    iface_by_name[(hostname, iface['interface'])] = iface

            # Build IP-to-Device lookup for OSPF
            device_by_ip = {}
            for device_data in network_data['devices']:
                ip = device_data.get('ip_address')
                if ip:
                    device_by_ip[ip] = device_data['hostname']

            # Create CDP physical connections
            cdp_links = []
            for device_data in network_data['devices']:
                hostname = device_data['hostname']
                for cdp in device_data['cdp_neighbors']:
                    local_name = cdp.get('local_interface', '')
                    neighbor_device = cdp.get('neighbor_device', '').split('.')[0]
                    neighbor_name = cdp.get('neighbor_interface', '')

                    if not local_name or not neighbor_device or not neighbor_name:
                        continue

                    # Lookup both interfaces
                    local_iface = iface_by_name.get((hostname, local_name), {})
                    remote_iface = iface_by_name.get((neighbor_device, neighbor_name), {})

                    # Only create connection if BOTH interfaces exist
                    if local_iface and remote_iface:
                        local_id = f"{hostname}:{local_name}"
                        remote_id = f"{neighbor_device}:{neighbor_name}"
                        cdp_links.append({
                            'local_id': local_id,
                            'remote_id': remote_id,
                            'neighbor_ip': cdp.get('neighbor_ip', ''),
                            'local_status': local_iface.get('status', ''),
                            'local_protocol': local_iface.get('protocol', ''),
                            'remote_status': remote_iface.get('status', ''),
                            'remote_protocol': remote_iface.get('protocol', ''),
                            'snapshot_id': snapshot_id
                        })

            session.run("""
                UNWIND $links AS link
                MATCH (local:Interface {id: link.local_id})
                MATCH (remote:Interface {id: link.remote_id})
                MERGE (local)-[r:CONNECTED_TO]->(remote)
                SET r.protocol = 'CDP',
                    r.neighbor_ip = link.neighbor_ip,
                    r.local_status = link.local_status,
                    r.local_protocol = link.local_protocol,
                    r.remote_status = link.remote_status,
                    r.remote_protocol = link.remote_protocol,
                    r.snapshot_id = link.snapshot_id
            """, {"links": cdp_links})

            # Create OSPF logical connections
            ospf_links = []
            for device_data in network_data['devices']:
                hostname = device_data['hostname']
                for ospf in device_data.get('ospf_neighbors', []):
                    neighbor_address = ospf.get('address', '')
                    neighbor_hostname = device_by_ip.get(neighbor_address)

                    # Only create relationship if we can map IP to Device
                    if neighbor_hostname:
                        ospf_links.append({
                            'local_hostname': hostname,
                            'remote_hostname': neighbor_hostname,
                            'neighbor_id': ospf.get('neighbor_id', ''),
                            'state': ospf.get('state', ''),
                            'priority': ospf.get('priority', ''),
                            'dead_time': ospf.get('dead_time', ''),
                            'local_interface': ospf.get('interface', ''),
                            'neighbor_address': neighbor_address,
                            'snapshot_id': snapshot_id
                        })

            session.run("""
                UNWIND $links AS link
                MATCH (local:Device {hostname: link.local_hostname})
                MATCH (remote:Device {hostname: link.remote_hostname})
                MERGE (local)-[r:OSPF_NEIGHBOR]->(remote)
                SET r.neighbor_id = link.neighbor_id,
                    r.state = link.state,
                    r.priority = link.priority,
                    r.dead_time = link.dead_time,
                    r.local_interface = link.local_interface,
                    r.neighbor_address = link.neighbor_address,
                    r.snapshot_id = link.snapshot_id
            """, {"links": ospf_links})

    return {
        "snapshot_id": snapshot_id,
        "devices": len(network_data['devices']),
        "interfaces": len(interfaces_payload),
        "cdp_connections": len(cdp_links),
        "ospf_connections": len(ospf_links),
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python feed_snapshot.py <path_to_json_snapshot>")
        sys.exit(1)

    json_file = Path(sys.argv[1])

    if not json_file.exists():
        print(f"[ERROR] File not found: {json_file}")
        sys.exit(1)

    # Load and feed snapshot
    network_data = load_snapshot(json_file)
    summary = feed_to_neo4j(network_data)
    print(
        "Snapshot loaded: "
        f"{summary['devices']} devices, "
        f"{summary['interfaces']} interfaces, "
        f"{summary['cdp_connections']} CDP, "
        f"{summary['ospf_connections']} OSPF."
    )

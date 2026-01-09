"""
Network-Wide Data Fetcher - Clean Two-Phase Approach
Phase 1: Fetch all devices and create nodes with properties
Phase 2: Create relationships (CDP physical + OSPF logical)
"""
import sys
from pathlib import Path
from datetime import datetime
import json

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from collectors.router_collector import RouterCollector
from collectors.switch_collector import SwitchCollector
from neo4j import GraphDatabase
import yaml


def load_yaml(file_path):
    """Load YAML configuration"""
    with open(file_path, 'r') as f:
        return yaml.safe_load(f)


class NetworkFetcher:
    """Fetches data from ALL devices in a single snapshot"""

    def __init__(self):
        config_dir = Path(__file__).parent / 'config'

        # Load configs
        self.devices = load_yaml(config_dir / 'devices.yaml')['devices']
        neo4j_cfg = load_yaml(config_dir / 'neo4j.yaml')['connection']

        # Neo4j driver
        self.driver = GraphDatabase.driver(
            neo4j_cfg['uri'],
            auth=(neo4j_cfg['user'], neo4j_cfg['password'])
        )

    def fetch_device(self, hostname, device_config):
        """Fetch data from a single device"""
        print(f"\n{'='*70}")
        print(f"FETCHING: {hostname} ({device_config['type']})")
        print('='*70)

        # Choose collector based on device type
        if device_config['type'] == 'router':
            collector = RouterCollector(
                hostname,
                device_config['mgmt_ip'],
                device_config['mgmt_port'],
                device_config['credentials']
            )
        else:
            collector = SwitchCollector(
                hostname,
                device_config['mgmt_ip'],
                device_config['mgmt_port'],
                device_config['credentials']
            )

        try:
            print(f"[1] Connecting to {hostname}...")
            collector.connect()
            print("[OK] Connected")

            print("\n[2] Fetching interfaces...")
            interfaces = collector.get_interface_brief()
            print(f"[OK] Found {len(interfaces)} interfaces")

            print("\n[3] Fetching CDP neighbors...")
            cdp_neighbors = collector.get_cdp_neighbors()
            print(f"[OK] Found {len(cdp_neighbors)} CDP neighbors")

            data = {
                "hostname": hostname,
                "type": device_config['type'],
                "ip_address": device_config.get('ip_address', ''),
                "interfaces": interfaces,
                "cdp_neighbors": cdp_neighbors
            }

            # Router-specific or switch-specific data
            if device_config['type'] == 'router':
                print("\n[4] Fetching OSPF neighbors...")
                ospf_neighbors = collector.get_ospf_neighbors()
                print(f"[OK] Found {len(ospf_neighbors)} OSPF neighbors")
                data['ospf_neighbors'] = ospf_neighbors
            else:
                print("\n[4] Fetching VLANs...")
                vlans = collector.get_vlan_brief()
                print(f"[OK] Found {len(vlans)} VLANs")

                print("\n[5] Fetching trunk interfaces...")
                trunks = collector.get_trunk_interfaces()
                print(f"[OK] Found {len(trunks)} trunk interfaces")

                print("\n[6] Fetching MAC address table...")
                macs = collector.get_mac_address_table()
                print(f"[OK] Found {len(macs)} MAC addresses")

                print("\n[7] Fetching spanning tree...")
                stp = collector.get_spanning_tree_summary()
                print(f"[OK] Got STP data for {len(stp.get('vlan_stats', []))} VLANs")

                # Check for OSPF on L3 switches
                try:
                    print("\n[8] Fetching OSPF neighbors (if L3 switch)...")
                    ospf_neighbors = collector.get_ospf_neighbors()
                    print(f"[OK] Found {len(ospf_neighbors)} OSPF neighbors")
                except:
                    ospf_neighbors = []
                    print("[OK] No OSPF (L2 switch)")

                data['vlans'] = vlans
                data['trunks'] = trunks
                data['mac_addresses'] = macs
                data['spanning_tree'] = stp
                data['ospf_neighbors'] = ospf_neighbors

            collector.disconnect()
            print(f"[OK] {hostname} fetch complete\n")

            return data

        except Exception as e:
            print(f"[ERROR] Failed to fetch {hostname}: {e}")
            collector.disconnect()
            return None

    def fetch_all(self):
        """Fetch data from all enabled devices"""
        print("="*70)
        print("NETWORK-WIDE DATA FETCHER")
        print("="*70)

        # Generate SINGLE snapshot ID for entire network
        snapshot_id = datetime.now().isoformat()
        snapshot_id_clean = snapshot_id.replace(':', '-')

        all_data = {
            "snapshot_id": snapshot_id,
            "devices": []
        }

        # Fetch from all enabled devices
        for hostname, config in self.devices.items():
            if config.get('enabled', True):
                device_data = self.fetch_device(hostname, config)
                if device_data:
                    all_data['devices'].append(device_data)

        # Save complete network snapshot to JSON
        output_dir = Path(__file__).parent / 'snapshots'
        output_dir.mkdir(exist_ok=True)
        json_file = output_dir / f"network_{snapshot_id_clean}.json"

        with open(json_file, 'w') as f:
            json.dump(all_data, f, indent=2)

        print("\n" + "="*70)
        print("NETWORK SNAPSHOT COMPLETE")
        print("="*70)
        print(f"Snapshot ID: {snapshot_id}")
        print(f"Devices collected: {len(all_data['devices'])}")
        print(f"JSON saved to: {json_file}")
        print("="*70)

        return all_data

    def feed_to_neo4j(self, network_data):
        """Feed network snapshot to Neo4j - Two-Phase Approach"""
        snapshot_id = network_data['snapshot_id']

        print("\n" + "="*70)
        print("FEEDING NETWORK TO NEO4J - TWO-PHASE APPROACH")
        print("="*70)

        with self.driver.session() as session:
            # ==================== PHASE 0: CREATE SNAPSHOT NODE ====================
            print("\n[PHASE 0] CREATING SNAPSHOT NODE")
            print("-" * 70)
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
            print(f"[OK] Snapshot node created: {snapshot_id}")

            # ==================== PHASE 1: CREATE NODES ====================
            print("\n[PHASE 1] CREATING NODES WITH PROPERTIES")
            print("-" * 70)

            # Create all interfaces with properties
            print(f"\n[1.1] Creating interfaces...")
            interface_count = 0
            for device_data in network_data['devices']:
                hostname = device_data['hostname']
                for iface in device_data['interfaces']:
                    iface_id = f"{hostname}:{iface['interface']}"
                    session.run("""
                        MATCH (d:Device {hostname: $hostname})
                        MERGE (i:Interface {id: $iface_id})
                        SET i.name = $name,
                            i.ip_address = $ip_address,
                            i.ok = $ok,
                            i.method = $method,
                            i.status = $status,
                            i.protocol = $protocol,
                            i.snapshot_id = $snapshot_id
                        MERGE (d)-[:HAS_INTERFACE]->(i)
                    """, {
                        'hostname': hostname,
                        'iface_id': iface_id,
                        'name': iface['interface'],
                        'ip_address': iface.get('ip_address', ''),
                        'ok': iface.get('ok', ''),
                        'method': iface.get('method', ''),
                        'status': iface.get('status', ''),
                        'protocol': iface.get('protocol', ''),
                        'snapshot_id': snapshot_id
                    })
                    interface_count += 1
            print(f"[OK] Created {interface_count} interfaces")

            # Store extra data as device properties (VLANs, MACs, STP, Trunks)
            print(f"\n[1.2] Storing switch extra data (VLANs, MACs, STP, Trunks)...")
            for device_data in network_data['devices']:
                if device_data['type'] == 'switch':
                    hostname = device_data['hostname']

                    # Store as JSON properties
                    vlans_json = json.dumps(device_data.get('vlans', []))
                    macs_json = json.dumps(device_data.get('mac_addresses', []))
                    stp_json = json.dumps(device_data.get('spanning_tree', {}))
                    trunks_json = json.dumps(device_data.get('trunks', []))

                    session.run("""
                        MATCH (d:Device {hostname: $hostname})
                        SET d.vlans = $vlans,
                            d.mac_addresses = $macs,
                            d.spanning_tree = $stp,
                            d.trunks = $trunks,
                            d.snapshot_id = $snapshot_id
                    """, {
                        'hostname': hostname,
                        'vlans': vlans_json,
                        'macs': macs_json,
                        'stp': stp_json,
                        'trunks': trunks_json,
                        'snapshot_id': snapshot_id
                    })
            print(f"[OK] Extra data stored as properties")

            # ==================== PHASE 2: CREATE RELATIONSHIPS ====================
            print("\n[PHASE 2] CREATING RELATIONSHIPS")
            print("-" * 70)

            # Build interface lookup: (hostname, interface_name) -> interface_data
            print(f"\n[2.1] Building interface lookup...")
            iface_by_name = {}
            for device_data in network_data['devices']:
                hostname = device_data['hostname']
                for iface in device_data['interfaces']:
                    iface_by_name[(hostname, iface['interface'])] = iface
            print(f"[OK] Indexed {len(iface_by_name)} interfaces")

            # Build IP-to-Device lookup for OSPF
            print(f"\n[2.2] Building IP-to-Device lookup from JSON data...")
            device_by_ip = {}

            # First, map from ip_address field in JSON
            for device_data in network_data['devices']:
                ip = device_data.get('ip_address')
                if ip:
                    device_by_ip[ip] = device_data['hostname']

            for ip, hostname in device_by_ip.items():
                print(f"  [DEBUG] {ip} -> {hostname}")
            print(f"[OK] Indexed {len(device_by_ip)} devices by IP")

            # Create CDP physical connections
            print(f"\n[2.3] Creating CDP physical connections...")
            cdp_count = 0
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

                        session.run("""
                            MATCH (local:Interface {id: $local_id})
                            MATCH (remote:Interface {id: $remote_id})
                            MERGE (local)-[r:CONNECTED_TO]->(remote)
                            SET r.protocol = 'CDP',
                                r.neighbor_ip = $neighbor_ip,
                                r.local_status = $local_status,
                                r.local_protocol = $local_protocol,
                                r.remote_status = $remote_status,
                                r.remote_protocol = $remote_protocol,
                                r.snapshot_id = $snapshot_id
                        """, {
                            'local_id': local_id,
                            'remote_id': remote_id,
                            'neighbor_ip': cdp.get('neighbor_ip', ''),
                            'local_status': local_iface.get('status', ''),
                            'local_protocol': local_iface.get('protocol', ''),
                            'remote_status': remote_iface.get('status', ''),
                            'remote_protocol': remote_iface.get('protocol', ''),
                            'snapshot_id': snapshot_id
                        })
                        cdp_count += 1
            print(f"[OK] Created {cdp_count} CDP connections")

            # Create OSPF logical connections
            print(f"\n[2.4] Creating OSPF logical connections...")
            ospf_count = 0
            for device_data in network_data['devices']:
                hostname = device_data['hostname']
                for ospf in device_data.get('ospf_neighbors', []):
                    neighbor_address = ospf.get('address', '')
                    neighbor_hostname = device_by_ip.get(neighbor_address)
                    print(f"  [DEBUG] {hostname} -> OSPF neighbor {neighbor_address} maps to {neighbor_hostname}")

                    # Only create relationship if we can map IP to Device
                    if neighbor_hostname:
                        session.run("""
                            MATCH (local:Device {hostname: $local_hostname})
                            MATCH (remote:Device {hostname: $remote_hostname})
                            MERGE (local)-[r:OSPF_NEIGHBOR]->(remote)
                            SET r.neighbor_id = $neighbor_id,
                                r.state = $state,
                                r.priority = $priority,
                                r.dead_time = $dead_time,
                                r.local_interface = $local_interface,
                                r.neighbor_address = $neighbor_address,
                                r.snapshot_id = $snapshot_id
                        """, {
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
                        ospf_count += 1
            print(f"[OK] Created {ospf_count} OSPF connections")

        print("\n" + "="*70)
        print("[OK] NETWORK DATA FED TO NEO4J")
        print(f"  - Interfaces: {interface_count}")
        print(f"  - CDP connections: {cdp_count}")
        print(f"  - OSPF connections: {ospf_count}")
        print("="*70)

    def run(self):
        """Main workflow: fetch all devices + feed to Neo4j"""
        try:
            # Fetch data from all devices
            network_data = self.fetch_all()

            # Feed to Neo4j with two-phase approach
            self.feed_to_neo4j(network_data)

            print("\n" + "="*70)
            print("[SUCCESS] NETWORK SNAPSHOT COMPLETE")
            print("="*70)

        finally:
            self.driver.close()


if __name__ == "__main__":
    fetcher = NetworkFetcher()
    fetcher.run()

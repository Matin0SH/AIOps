"""
Switch Data Fetcher
Fetches live data from switch, saves JSON, and feeds to Neo4j
"""
import sys
from pathlib import Path
from datetime import datetime
import json

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from collectors.switch_collector import SwitchCollector
from neo4j import GraphDatabase
import yaml


def load_yaml(file_path):
    """Load YAML configuration"""
    with open(file_path, 'r') as f:
        return yaml.safe_load(f)


class SwitchFetcher:
    """Fetches switch data, saves JSON, and feeds to Neo4j"""

    def __init__(self, hostname):
        self.hostname = hostname
        config_dir = Path(__file__).parent / 'config'

        # Load configs
        devices = load_yaml(config_dir / 'devices.yaml')['devices']
        self.device_config = devices[hostname]

        neo4j_cfg = load_yaml(config_dir / 'neo4j.yaml')['connection']

        # SwitchCollector
        self.collector = SwitchCollector(
            hostname,
            self.device_config['mgmt_ip'],
            self.device_config['mgmt_port'],
            self.device_config['credentials']
        )

        # Neo4j driver
        self.driver = GraphDatabase.driver(
            neo4j_cfg['uri'],
            auth=(neo4j_cfg['user'], neo4j_cfg['password'])
        )

    def fetch(self):
        """Connect to switch and fetch all data"""
        print("=" * 70)
        print(f"SWITCH DATA FETCHER: {self.hostname}")
        print("=" * 70)

        print(f"\n[1] Connecting to {self.hostname}...")
        self.collector.connect()
        print("[OK] Connected")

        print("\n[2] Fetching interfaces...")
        interfaces = self.collector.get_interface_brief()
        print(f"[OK] Found {len(interfaces)} interfaces")

        print("\n[3] Fetching CDP neighbors...")
        cdp_neighbors = self.collector.get_cdp_neighbors()
        print(f"[OK] Found {len(cdp_neighbors)} CDP neighbors")

        print("\n[4] Fetching VLANs...")
        vlans = self.collector.get_vlan_brief()
        print(f"[OK] Found {len(vlans)} VLANs")

        print("\n[5] Fetching trunk interfaces...")
        trunks = self.collector.get_trunk_interfaces()
        print(f"[OK] Found {len(trunks)} trunk interfaces")

        print("\n[6] Fetching MAC address table...")
        macs = self.collector.get_mac_address_table()
        print(f"[OK] Found {len(macs)} MAC addresses")

        print("\n[7] Fetching spanning tree...")
        stp = self.collector.get_spanning_tree_summary()
        print(f"[OK] Got STP data for {len(stp.get('vlan_stats', []))} VLANs")

        # Check for OSPF (only L3 switches)
        try:
            print("\n[8] Fetching OSPF neighbors (if L3 switch)...")
            ospf_neighbors = self.collector.get_ospf_neighbors()
            print(f"[OK] Found {len(ospf_neighbors)} OSPF neighbors")
        except:
            ospf_neighbors = []
            print("[OK] No OSPF (L2 switch)")

        self.collector.disconnect()

        # Build schema
        snapshot_id = datetime.now().isoformat()
        snapshot_id_clean = snapshot_id.replace(':', '-')

        data = {
            "device": {
                "hostname": self.hostname,
                "type": self.device_config['type'],
                "snapshot_id": snapshot_id
            },
            "interfaces": interfaces,
            "cdp_neighbors": cdp_neighbors,
            "vlans": vlans,
            "trunks": trunks,
            "mac_addresses": macs,
            "spanning_tree": stp,
            "ospf_neighbors": ospf_neighbors
        }

        # Save to JSON
        output_dir = Path(__file__).parent / 'snapshots'
        output_dir.mkdir(exist_ok=True)
        json_file = output_dir / f"{self.hostname}_{snapshot_id_clean}.json"

        with open(json_file, 'w') as f:
            json.dump(data, f, indent=2)

        print(f"\n[9] JSON saved to: {json_file}")

        # Print summary
        print("\n" + "=" * 70)
        print("DATA SUMMARY:")
        print("=" * 70)
        print(f"Device: {self.hostname} ({self.device_config['type']})")
        print(f"Snapshot ID: {snapshot_id}")
        print(f"Interfaces: {len(interfaces)}")
        print(f"CDP Neighbors: {len(cdp_neighbors)}")
        print(f"VLANs: {len(vlans)}")
        print(f"Trunks: {len(trunks)}")
        print(f"MAC Addresses: {len(macs)}")
        print(f"STP VLANs: {len(stp.get('vlan_stats', []))}")
        print(f"OSPF Neighbors: {len(ospf_neighbors)}")

        # Print preview (first few items only due to size)
        print("\n" + "=" * 70)
        print("DATA PREVIEW (Limited):")
        print("=" * 70)

        preview = {
            "device": data["device"],
            "interfaces": data["interfaces"][:3] if len(data["interfaces"]) > 3 else data["interfaces"],
            "cdp_neighbors": data["cdp_neighbors"],
            "vlans": data["vlans"],
            "trunks": data["trunks"][:2] if len(data["trunks"]) > 2 else data["trunks"],
            "mac_addresses": data["mac_addresses"][:5] if len(data["mac_addresses"]) > 5 else data["mac_addresses"],
            "spanning_tree": {
                "config": data["spanning_tree"].get("config", {}),
                "vlan_stats": data["spanning_tree"].get("vlan_stats", [])[:2]
            },
            "ospf_neighbors": data["ospf_neighbors"]
        }

        print(json.dumps(preview, indent=2))
        print("\n[NOTE] Full data saved to JSON file")

        print("\n" + "=" * 70)
        print("[OK] FETCH COMPLETE")
        print("=" * 70)

        return data

    def feed_to_neo4j(self, data, snapshot_id):
        """Feed switch data to Neo4j"""
        print("\n" + "=" * 70)
        print("FEEDING TO NEO4J")
        print("=" * 70)

        with self.driver.session() as session:
            # Create snapshot
            print("\n[1] Creating snapshot...")
            session.run("""
                CREATE (s:Snapshot {
                    id: $snapshot_id,
                    timestamp: datetime($snapshot_id),
                    device: $hostname,
                    type: 'switch'
                })
            """, {
                'snapshot_id': snapshot_id,
                'hostname': self.hostname
            })

            # Link device to snapshot
            session.run("""
                MATCH (d:Device {hostname: $hostname})
                MATCH (s:Snapshot {id: $snapshot_id})
                MERGE (d)-[:SNAPSHOT_AT]->(s)
            """, {
                'hostname': self.hostname,
                'snapshot_id': snapshot_id
            })
            print("[OK] Snapshot created")

            # Create interfaces
            print(f"\n[2] Creating {len(data['interfaces'])} interfaces...")
            for iface in data['interfaces']:
                iface_id = f"{self.hostname}:{iface['interface']}"
                session.run("""
                    MATCH (d:Device {hostname: $hostname})
                    MATCH (s:Snapshot {id: $snapshot_id})
                    MERGE (i:Interface {id: $iface_id})
                    SET i.name = $name,
                        i.ip_address = $ip_address,
                        i.status = $status,
                        i.protocol = $protocol
                    MERGE (d)-[:HAS_INTERFACE]->(i)
                    MERGE (i)-[:STATE_IN]->(s)
                """, {
                    'hostname': self.hostname,
                    'snapshot_id': snapshot_id,
                    'iface_id': iface_id,
                    'name': iface['interface'],
                    'ip_address': iface['ip_address'],
                    'status': iface['status'],
                    'protocol': iface['protocol']
                })
            print(f"[OK] {len(data['interfaces'])} interfaces created")

            # Create VLANs
            print(f"\n[3] Creating {len(data['vlans'])} VLANs...")
            for vlan in data['vlans']:
                session.run("""
                    MATCH (s:Snapshot {id: $snapshot_id})
                    MERGE (v:VLAN {id: $vlan_id})
                    SET v.name = $name,
                        v.status = $status
                    MERGE (v)-[:STATE_IN]->(s)
                """, {
                    'snapshot_id': snapshot_id,
                    'vlan_id': vlan['vlan_id'],
                    'name': vlan['name'],
                    'status': vlan['status']
                })
            print(f"[OK] {len(data['vlans'])} VLANs created")

            # Create trunk relationships
            print(f"\n[4] Creating trunk relationships...")
            trunk_count = 0
            for trunk in data['trunks']:
                iface_id = f"{self.hostname}:{trunk['port']}"
                for vlan_id in trunk.get('vlans_allowed', '').split(','):
                    vlan_id = vlan_id.strip()
                    if vlan_id:
                        session.run("""
                            MATCH (i:Interface {id: $iface_id})
                            MATCH (v:VLAN {id: $vlan_id})
                            MERGE (i)-[r:TRUNKS_VLAN]->(v)
                            SET r.snapshot_id = $snapshot_id
                        """, {
                            'iface_id': iface_id,
                            'vlan_id': vlan_id,
                            'snapshot_id': snapshot_id
                        })
                        trunk_count += 1
            print(f"[OK] {trunk_count} trunk relationships created")

            # Create MAC addresses
            print(f"\n[5] Creating {len(data['mac_addresses'])} MAC addresses...")
            for mac in data['mac_addresses']:
                iface_id = f"{self.hostname}:{mac.get('port', '')}"
                session.run("""
                    MERGE (m:MACAddress {address: $mac_address})
                    MERGE (i:Interface {id: $iface_id})
                    MERGE (m)-[r:LEARNED_ON]->(i)
                    SET r.vlan = $vlan,
                        r.snapshot_id = $snapshot_id
                """, {
                    'mac_address': mac['mac_address'],
                    'iface_id': iface_id,
                    'vlan': mac.get('vlan', ''),
                    'snapshot_id': snapshot_id
                })
            print(f"[OK] {len(data['mac_addresses'])} MAC addresses created")

            # Create CDP relationships
            print(f"\n[6] Creating {len(data['cdp_neighbors'])} CDP connections...")
            for cdp in data['cdp_neighbors']:
                local_iface = f"{self.hostname}:{cdp['local_interface']}"
                remote_device = cdp['neighbor_device'].split('.')[0]
                remote_iface = f"{remote_device}:{cdp['neighbor_interface']}"

                session.run("""
                    MATCH (local:Interface {id: $local_iface})
                    MERGE (remote:Interface {id: $remote_iface})
                    MERGE (local)-[r:CONNECTED_TO]->(remote)
                    SET r.protocol = 'CDP',
                        r.neighbor_ip = $neighbor_ip,
                        r.snapshot_id = $snapshot_id
                """, {
                    'snapshot_id': snapshot_id,
                    'local_iface': local_iface,
                    'remote_iface': remote_iface,
                    'neighbor_ip': cdp.get('neighbor_ip', '')
                })
            print(f"[OK] {len(data['cdp_neighbors'])} CDP connections created")

            # Store OSPF neighbor info on device (no node creation)
            if data['ospf_neighbors']:
                print(f"\n[7] Storing {len(data['ospf_neighbors'])} OSPF neighbors...")
                ospf_data = []
                for ospf in data['ospf_neighbors']:
                    ospf_data.append({
                        'router_id': ospf['neighbor_id'],
                        'state': ospf['state'],
                        'address': ospf['address']
                    })

                # Convert to JSON string for Neo4j storage
                ospf_json = json.dumps(ospf_data)

                session.run("""
                    MATCH (d:Device {hostname: $hostname})
                    SET d.ospf_neighbors = $ospf_json,
                        d.ospf_snapshot_id = $snapshot_id
                """, {
                    'hostname': self.hostname,
                    'ospf_json': ospf_json,
                    'snapshot_id': snapshot_id
                })
                print(f"[OK] {len(data['ospf_neighbors'])} OSPF neighbors stored")

        print("\n" + "=" * 70)
        print("[OK] DATA FED TO NEO4J")
        print("=" * 70)

    def run(self):
        """Main workflow: fetch + feed"""
        try:
            # Fetch data
            data = self.fetch()

            # Feed to Neo4j
            self.feed_to_neo4j(data, data['device']['snapshot_id'])

            print("\n" + "=" * 70)
            print(f"[SUCCESS] {self.hostname} COMPLETE")
            print("=" * 70)

        finally:
            self.driver.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Fetch switch data and output JSON')
    parser.add_argument('hostname', help='Switch hostname (e.g., CORE-SW1, MANAGEMENT)')

    args = parser.parse_args()

    fetcher = SwitchFetcher(args.hostname)
    fetcher.run()

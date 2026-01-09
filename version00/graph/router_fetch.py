"""
Router Data Fetcher
Fetches live data from router, saves JSON, and feeds to Neo4j
"""
import sys
from pathlib import Path
from datetime import datetime
import json

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from collectors.router_collector import RouterCollector
from neo4j import GraphDatabase
import yaml


def load_yaml(file_path):
    """Load YAML configuration"""
    with open(file_path, 'r') as f:
        return yaml.safe_load(f)


class RouterFetcher:
    """Fetches router data, saves JSON, and feeds to Neo4j"""

    def __init__(self, hostname):
        self.hostname = hostname
        config_dir = Path(__file__).parent / 'config'

        # Load configs
        devices = load_yaml(config_dir / 'devices.yaml')['devices']
        self.device_config = devices[hostname]

        neo4j_cfg = load_yaml(config_dir / 'neo4j.yaml')['connection']

        # RouterCollector
        self.collector = RouterCollector(
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
        """Connect to router and fetch all data"""
        print("=" * 70)
        print(f"ROUTER DATA FETCHER: {self.hostname}")
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

        print("\n[4] Fetching OSPF neighbors...")
        ospf_neighbors = self.collector.get_ospf_neighbors()
        print(f"[OK] Found {len(ospf_neighbors)} OSPF neighbors")

        self.collector.disconnect()

        # Build schema
        snapshot_id = datetime.now().isoformat()
        # Clean snapshot_id for filename (remove colons for Windows)
        snapshot_id_clean = snapshot_id.replace(':', '-')

        data = {
            "device": {
                "hostname": self.hostname,
                "type": self.device_config['type'],
                "snapshot_id": snapshot_id
            },
            "interfaces": interfaces,
            "cdp_neighbors": cdp_neighbors,
            "ospf_neighbors": ospf_neighbors
        }

        # Save to JSON
        output_dir = Path(__file__).parent / 'snapshots'
        output_dir.mkdir(exist_ok=True)
        json_file = output_dir / f"{self.hostname}_{snapshot_id_clean}.json"

        with open(json_file, 'w') as f:
            json.dump(data, f, indent=2)

        print(f"\n[5] JSON saved to: {json_file}")

        # Print summary
        print("\n" + "=" * 70)
        print("DATA SUMMARY:")
        print("=" * 70)
        print(f"Device: {self.hostname} ({self.device_config['type']})")
        print(f"Snapshot ID: {snapshot_id}")
        print(f"Interfaces: {len(interfaces)}")
        print(f"CDP Neighbors: {len(cdp_neighbors)}")
        print(f"OSPF Neighbors: {len(ospf_neighbors)}")

        # Print preview
        print("\n" + "=" * 70)
        print("DATA PREVIEW:")
        print("=" * 70)
        print(json.dumps(data, indent=2))

        print("\n" + "=" * 70)
        print("[OK] FETCH COMPLETE")
        print("=" * 70)

        return data

    def feed_to_neo4j(self, data, snapshot_id):
        """Feed router data to Neo4j"""
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
                    type: 'router'
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

            # Create CDP relationships
            print(f"\n[3] Creating {len(data['cdp_neighbors'])} CDP connections...")
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
                print(f"\n[4] Storing {len(data['ospf_neighbors'])} OSPF neighbors...")
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
            else:
                print("\n[4] No OSPF neighbors to store")

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

    parser = argparse.ArgumentParser(description='Fetch router data and output JSON')
    parser.add_argument('hostname', help='Router hostname (e.g., EDGE-R1)')

    args = parser.parse_args()

    fetcher = RouterFetcher(args.hostname)
    fetcher.run()

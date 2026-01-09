"""
Router Node Collector
Collects live data from router and creates Neo4j snapshot
"""
import sys
from pathlib import Path
from datetime import datetime
import json

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from collectors.router_collector import RouterCollector
from neo4j import GraphDatabase
import yaml


def load_yaml(file_path):
    """Load YAML configuration"""
    with open(file_path, 'r') as f:
        return yaml.safe_load(f)


class RouterNodeCollector:
    """Collects router data and stores in Neo4j with snapshot"""

    def __init__(self, hostname):
        self.hostname = hostname
        config_dir = Path(__file__).parent.parent / 'config'

        # Load configs
        devices = load_yaml(config_dir / 'devices.yaml')['devices']
        neo4j_cfg = load_yaml(config_dir / 'neo4j.yaml')['connection']

        # Device config
        self.device_config = devices[hostname]

        # Neo4j connection
        self.driver = GraphDatabase.driver(
            neo4j_cfg['uri'],
            auth=(neo4j_cfg['user'], neo4j_cfg['password'])
        )

        # RouterCollector
        self.collector = RouterCollector(
            hostname,
            self.device_config['mgmt_ip'],
            self.device_config['mgmt_port'],
            self.device_config['credentials']
        )

    def fetch_data(self):
        """Connect to router and fetch all data"""
        print(f"\n[1] Connecting to {self.hostname}...")
        self.collector.connect()
        print("[OK] Connected")

        print("\n[2] Fetching router data...")
        data = {
            "device": {
                "hostname": self.hostname,
                "type": self.device_config['type']
            },
            "interfaces": self.collector.get_interface_brief(),
            "cdp_neighbors": self.collector.get_cdp_neighbors(),
            "ospf_neighbors": self.collector.get_ospf_neighbors()
        }

        print(f"[OK] Collected: {len(data['interfaces'])} interfaces, "
              f"{len(data['cdp_neighbors'])} CDP neighbors, "
              f"{len(data['ospf_neighbors'])} OSPF neighbors")

        self.collector.disconnect()
        return data

    def save_snapshot(self, data, snapshot_id):
        """Save data to Neo4j as snapshot"""
        print(f"\n[3] Creating snapshot {snapshot_id}...")

        with self.driver.session() as session:
            # Create snapshot node
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

            # Create interfaces
            for iface in data['interfaces']:
                iface_id = f"{self.hostname}:{iface['interface']}"
                session.run("""
                    MATCH (d:Device {hostname: $hostname})
                    MATCH (s:Snapshot {id: $snapshot_id})
                    MERGE (i:Interface {id: $iface_id})
                    SET i.name = $name,
                        i.ip_address = $ip_address,
                        i.status = $status,
                        i.protocol = $protocol,
                        i.ok = $ok,
                        i.method = $method
                    MERGE (d)-[:HAS_INTERFACE]->(i)
                    MERGE (i)-[:STATE_IN]->(s)
                """, {
                    'hostname': self.hostname,
                    'snapshot_id': snapshot_id,
                    'iface_id': iface_id,
                    'name': iface['interface'],
                    'ip_address': iface['ip_address'],
                    'status': iface['status'],
                    'protocol': iface['protocol'],
                    'ok': iface['ok'],
                    'method': iface['method']
                })

            # Create CDP relationships
            for cdp in data['cdp_neighbors']:
                local_iface = f"{self.hostname}:{cdp['local_interface']}"
                remote_iface = f"{cdp['neighbor_device']}:{cdp['neighbor_interface']}"

                session.run("""
                    MATCH (s:Snapshot {id: $snapshot_id})
                    MATCH (local:Interface {id: $local_iface})
                    MERGE (remote:Interface {id: $remote_iface})
                    MERGE (local)-[r:CONNECTED_TO]->(remote)
                    SET r.protocol = 'CDP',
                        r.neighbor_ip = $neighbor_ip,
                        r.platform = $platform,
                        r.capabilities = $capabilities
                    MERGE (r)-[:DISCOVERED_IN]->(s)
                """, {
                    'snapshot_id': snapshot_id,
                    'local_iface': local_iface,
                    'remote_iface': remote_iface,
                    'neighbor_ip': cdp.get('neighbor_ip', ''),
                    'platform': cdp.get('platform', ''),
                    'capabilities': cdp.get('capabilities', '')
                })

            # Create OSPF relationships
            for ospf in data['ospf_neighbors']:
                session.run("""
                    MATCH (d:Device {hostname: $hostname})
                    MATCH (s:Snapshot {id: $snapshot_id})
                    MERGE (n:Device {hostname: $neighbor_hostname})
                    MERGE (d)-[r:OSPF_NEIGHBOR]->(n)
                    SET r.neighbor_id = $neighbor_id,
                        r.priority = $priority,
                        r.state = $state,
                        r.address = $address,
                        r.interface = $interface
                    MERGE (r)-[:DISCOVERED_IN]->(s)
                """, {
                    'hostname': self.hostname,
                    'snapshot_id': snapshot_id,
                    'neighbor_hostname': f"UNKNOWN-{ospf['neighbor_id']}",  # Will be resolved by mapping
                    'neighbor_id': ospf['neighbor_id'],
                    'priority': ospf['priority'],
                    'state': ospf['state'],
                    'address': ospf['address'],
                    'interface': ospf['interface']
                })

        print(f"[OK] Snapshot created with {len(data['interfaces'])} interfaces")

    def collect(self, save_json=True):
        """Main collection workflow"""
        print("=" * 70)
        print(f"ROUTER NODE COLLECTOR: {self.hostname}")
        print("=" * 70)

        try:
            # Generate snapshot ID
            snapshot_id = datetime.now().isoformat()

            # Fetch live data
            data = self.fetch_data()
            data['device']['snapshot_id'] = snapshot_id

            # Save JSON if requested
            if save_json:
                output_dir = Path(__file__).parent.parent / 'snapshots'
                output_dir.mkdir(exist_ok=True)
                json_file = output_dir / f"{self.hostname}_{snapshot_id}.json"

                with open(json_file, 'w') as f:
                    json.dump(data, f, indent=2)
                print(f"\n[JSON] Saved to {json_file}")

            # Save to Neo4j
            self.save_snapshot(data, snapshot_id)

            print("\n" + "=" * 70)
            print(f"[OK] COLLECTION COMPLETE: {self.hostname}")
            print("=" * 70)

            return snapshot_id

        except Exception as e:
            print(f"\n[ERROR] Collection failed: {e}")
            raise

        finally:
            self.driver.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Collect router data and create Neo4j snapshot')
    parser.add_argument('hostname', help='Router hostname (e.g., EDGE-R1)')
    parser.add_argument('--no-json', action='store_true', help='Skip JSON file creation')

    args = parser.parse_args()

    collector = RouterNodeCollector(args.hostname)
    collector.collect(save_json=not args.no_json)

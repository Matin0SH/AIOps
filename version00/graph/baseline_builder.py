"""
Baseline Graph Builder
Creates minimal device skeleton from devices.yaml
Just Device nodes - collectors will add everything else live
"""
import yaml
from pathlib import Path
from neo4j import GraphDatabase


def load_yaml(file_path):
    """Load YAML configuration file"""
    with open(file_path, 'r') as f:
        return yaml.safe_load(f)


class BaselineBuilder:
    def __init__(self):
        config_dir = Path(__file__).parent / 'config'

        # Load configurations
        self.devices_config = load_yaml(config_dir / 'devices.yaml')
        self.neo4j_config = load_yaml(config_dir / 'neo4j.yaml')

        # Connect to Neo4j
        conn = self.neo4j_config['connection']
        self.driver = GraphDatabase.driver(
            conn['uri'],
            auth=(conn['user'], conn['password'])
        )

    def create_indexes(self):
        """Create Neo4j indexes for performance"""
        print("\n[1] Creating indexes...")
        with self.driver.session() as session:
            indexes = [
                "CREATE INDEX device_hostname IF NOT EXISTS FOR (d:Device) ON (d.hostname)",
                "CREATE INDEX interface_id IF NOT EXISTS FOR (i:Interface) ON (i.id)",
                "CREATE INDEX vlan_id IF NOT EXISTS FOR (v:VLAN) ON (v.id)",
                "CREATE INDEX snapshot_id IF NOT EXISTS FOR (s:Snapshot) ON (s.id)",
                "CREATE INDEX mac_address IF NOT EXISTS FOR (m:MACAddress) ON (m.address)"
            ]

            for index_query in indexes:
                session.run(index_query)

        print("[OK] Indexes created")

    def create_devices(self):
        """Create Device nodes from YAML - minimal skeleton only"""
        print("\n[2] Creating Device nodes...")
        devices = self.devices_config['devices']

        with self.driver.session() as session:
            for hostname, config in devices.items():
                if not config.get('enabled', True):
                    print(f"[SKIP] {hostname} (disabled)")
                    continue

                session.run("""
                    MERGE (d:Device {hostname: $hostname})
                    SET d.type = $type,
                        d.ip_address = $ip_address,
                        d.mgmt_ip = $mgmt_ip,
                        d.mgmt_port = $mgmt_port,
                        d.created_at = datetime()
                """, {
                    'hostname': hostname,
                    'type': config['type'],
                    'ip_address': config.get('ip_address', ''),
                    'mgmt_ip': config['mgmt_ip'],
                    'mgmt_port': config['mgmt_port']
                })

                print(f"[OK] {hostname} ({config['type']})")

        print(f"[OK] Created {len([d for d in devices.values() if d.get('enabled', True)])} devices")

    def get_stats(self):
        """Get graph statistics"""
        print("\n[3] Graph statistics...")
        with self.driver.session() as session:
            result = session.run("MATCH (d:Device) RETURN count(d) as total")
            total = result.single()['total']

            print(f"\n  Device nodes: {total}")
            print(f"  Relationships: 0 (skeleton only)")

    def build(self):
        """Build baseline skeleton"""
        print("=" * 70)
        print("BASELINE GRAPH BUILDER - SKELETON ONLY")
        print("=" * 70)

        try:
            self.create_indexes()
            self.create_devices()
            self.get_stats()

            print("\n" + "=" * 70)
            print("[OK] SKELETON CREATED - Ready for collectors")
            print("=" * 70)

        except Exception as e:
            print(f"\n[ERROR] Failed to build skeleton: {e}")
            raise

        finally:
            self.driver.close()


if __name__ == "__main__":
    builder = BaselineBuilder()
    builder.build()

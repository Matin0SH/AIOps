"""
Test YAML Configuration
Verifies devices.yaml and neo4j.yaml are valid and displays the structure
"""
import yaml
from pathlib import Path

def load_yaml(file_path):
    """Load and parse YAML file"""
    with open(file_path, 'r') as f:
        return yaml.safe_load(f)

def main():
    config_dir = Path(__file__).parent / 'config'

    print("=" * 70)
    print("TESTING YAML CONFIGURATION FILES")
    print("=" * 70)

    # Test devices.yaml
    print("\n[1] Loading devices.yaml...")
    try:
        devices_config = load_yaml(config_dir / 'devices.yaml')
        print("[OK] devices.yaml loaded successfully")

        print("\n[2] Devices found:")
        for hostname, config in devices_config['devices'].items():
            status = "[ENABLED]" if config.get('enabled', True) else "[DISABLED]"
            print(f"  {hostname:15} | {config['type']:8} | {config['mgmt_ip']}:{config['mgmt_port']} | {status}")

        print(f"\n[3] Network settings:")
        network = devices_config.get('network', {})
        print(f"  Name: {network.get('name', 'N/A')}")
        print(f"  Domain: {network.get('domain', 'N/A')}")

        print(f"\n[4] VLANs configured:")
        for vlan in devices_config.get('network', {}).get('vlans', []):
            print(f"  VLAN {vlan['id']:3} | {vlan['name']:12} | {vlan['subnet']:16} | GW: {vlan['gateway']}")

        print(f"\n[5] OSPF Router ID Mapping:")
        ospf_mapping = devices_config.get('ospf', {}).get('router_id_mapping', {})
        for router_id, hostname in ospf_mapping.items():
            print(f"  {router_id:15} -> {hostname}")

    except Exception as e:
        print(f"[ERROR] Error loading devices.yaml: {e}")
        return False

    # Test neo4j.yaml
    print("\n" + "=" * 70)
    print("\n[6] Loading neo4j.yaml...")
    try:
        neo4j_config = load_yaml(config_dir / 'neo4j.yaml')
        print("[OK] neo4j.yaml loaded successfully")

        conn = neo4j_config.get('connection', {})
        print(f"\n[7] Neo4j connection:")
        print(f"  URI: {conn.get('uri', 'N/A')}")
        print(f"  User: {conn.get('user', 'N/A')}")
        print(f"  Password: {'*' * len(conn.get('password', ''))}")

        timeouts = neo4j_config.get('timeouts', {})
        print(f"\n[8] Timeouts:")
        print(f"  Read: {timeouts.get('read', 'N/A')}s")
        print(f"  Write: {timeouts.get('write', 'N/A')}s")
        print(f"  Transaction: {timeouts.get('transaction', 'N/A')}s")

    except Exception as e:
        print(f"[ERROR] Error loading neo4j.yaml: {e}")
        return False

    print("\n" + "=" * 70)
    print("[OK] ALL YAML CONFIGURATION FILES ARE VALID")
    print("=" * 70)

    return True

if __name__ == "__main__":
    main()

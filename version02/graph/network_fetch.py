"""
Network-Wide Data Fetcher
Fetch device data and write a JSON snapshot only.
"""
from datetime import datetime
import json
from pathlib import Path
import sys

STRUCTURED_ROOT = Path(__file__).resolve().parents[1]
if str(STRUCTURED_ROOT) not in sys.path:
    sys.path.append(str(STRUCTURED_ROOT))

from graph.base import load_devices
from tools.collector import Collector


class NetworkFetcher:
    """Fetches data from ALL devices in a single snapshot"""

    def __init__(self):
        self.devices = load_devices()

    def fetch_device(self, hostname, device_config):
        """Fetch data from a single device"""
        print(f"\n{'='*70}")
        print(f"FETCHING: {hostname} ({device_config['type']})")
        print('='*70)

        try:
            print(f"[1] Connecting to {hostname}...")
            collector = Collector(
                hostname,
                device_config['mgmt_ip'],
                device_config['mgmt_port'],
                device_config['credentials']
            )

            with collector as connected:
                print("[OK] Connected")

                print("\n[2] Fetching interfaces...")
                interfaces = connected.get_interface_brief()
                print(f"[OK] Found {len(interfaces)} interfaces")

                print("\n[3] Fetching CDP neighbors...")
                cdp_neighbors = connected.get_cdp_neighbors()
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
                    ospf_neighbors = connected.get_ospf_neighbors()
                    print(f"[OK] Found {len(ospf_neighbors)} OSPF neighbors")
                    data['ospf_neighbors'] = ospf_neighbors
                else:
                    print("\n[4] Fetching VLANs...")
                    vlans = connected.get_vlan_brief()
                    print(f"[OK] Found {len(vlans)} VLANs")

                    print("\n[5] Fetching trunk interfaces...")
                    trunks = connected.get_trunk_interfaces()
                    print(f"[OK] Found {len(trunks)} trunk interfaces")

                    print("\n[6] Fetching MAC address table...")
                    macs = connected.get_mac_address_table()
                    print(f"[OK] Found {len(macs)} MAC addresses")

                    print("\n[7] Fetching spanning tree...")
                    stp = connected.get_spanning_tree_summary()
                    print(f"[OK] Got STP data for {len(stp.get('vlan_stats', []))} VLANs")

                    # Check for OSPF on L3 switches
                    try:
                        print("\n[8] Fetching OSPF neighbors (if L3 switch)...")
                        ospf_neighbors = connected.get_ospf_neighbors()
                        print(f"[OK] Found {len(ospf_neighbors)} OSPF neighbors")
                    except Exception:
                        ospf_neighbors = []
                        print("[OK] No OSPF (L2 switch)")

                    data['vlans'] = vlans
                    data['trunks'] = trunks
                    data['mac_addresses'] = macs
                    data['spanning_tree'] = stp
                    data['ospf_neighbors'] = ospf_neighbors

            print(f"[OK] {hostname} fetch complete\n")
            return data

        except Exception as e:
            print(f"[ERROR] Failed to fetch {hostname}: {e}")
            return None

    def fetch_all(self):
        """Fetch data from all enabled devices"""
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

        return all_data

    def run(self):
        """Main workflow: fetch all devices + write snapshot"""
        self.fetch_all()


if __name__ == "__main__":
    fetcher = NetworkFetcher()
    fetcher.run()

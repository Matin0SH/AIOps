"""
Live Network Graph Builder - SIMPLE VERSION
Connects to devices, collects data, builds graph
"""
from graph.neo4j_connector import Neo4jConnector
from collectors.router_collector import RouterCollector
from collectors.switch_collector import SwitchCollector
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LiveGraphBuilder:
    """Build network graph from live device data"""

    def __init__(self, neo4j_uri, neo4j_user, neo4j_password, device_delay=3):
        self.db = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)
        self.devices = []
        self.device_delay = device_delay

    def _pause(self):
        """Give devices time to respond between calls."""
        if self.device_delay:
            time.sleep(self.device_delay)

    def add_device(self, hostname, device_type, host, port, creds):
        """Add device to list"""
        self.devices.append({
            'hostname': hostname,
            'type': device_type,
            'host': host,
            'port': port,
            'creds': creds
        })

    def collect_data(self):
        """Collect data from all devices"""
        logger.info("=" * 80)
        logger.info("COLLECTING DATA")
        logger.info("=" * 80)

        all_data = {}

        for device_info in self.devices:
            hostname = device_info['hostname']
            logger.info(f"\n[{hostname}]")

            # Create collector
            if device_info['type'] == 'router':
                collector = RouterCollector(hostname, device_info['host'], device_info['port'], device_info['creds'])
            else:
                collector = SwitchCollector(hostname, device_info['host'], device_info['port'], device_info['creds'])

            data = {
                'hostname': hostname,
                'type': device_info['type'],
                'interfaces': [],
                'cdp': [],
                'ospf': [],
                'vlans': [],
                'trunks': [],
                'macs': [],
                'stp': None
            }

            try:
                # Connect
                collector.connect()
                logger.info("  Connected")
                self._pause()

                # Get interfaces
                try:
                    logger.info("  Fetching interfaces...")
                    data['interfaces'] = collector.get_interface_brief()
                    logger.info(f"  Interfaces: {len(data['interfaces'])}")
                except Exception as e:
                    logger.error(f"  Interfaces failed: {e}")
                self._pause()

                # Get CDP
                try:
                    logger.info("  Fetching CDP neighbors...")
                    data['cdp'] = collector.get_cdp_neighbors()
                    logger.info(f"  CDP: {len(data['cdp'])}")
                except Exception as e:
                    logger.error(f"  CDP failed: {e}")
                self._pause()

                # Get OSPF
                try:
                    logger.info("  Fetching OSPF neighbors...")
                    data['ospf'] = collector.get_ospf_neighbors()
                    logger.info(f"  OSPF: {len(data['ospf'])}")
                except Exception as e:
                    logger.error(f"  OSPF failed: {e}")
                self._pause()

                # Switch-specific
                if device_info['type'] == 'switch':
                    try:
                        logger.info("  Fetching VLANs...")
                        data['vlans'] = collector.get_vlan_brief()
                        logger.info(f"  VLANs: {len(data['vlans'])}")
                    except Exception as e:
                        logger.error(f"  VLANs failed: {e}")
                    self._pause()

                    try:
                        logger.info("  Fetching trunk interfaces...")
                        data['trunks'] = collector.get_trunk_interfaces()
                        logger.info(f"  Trunks: {len(data['trunks'])}")
                    except Exception as e:
                        logger.error(f"  Trunks failed: {e}")
                    self._pause()

                    try:
                        logger.info("  Fetching MAC address table...")
                        data['macs'] = collector.get_mac_address_table()
                        logger.info(f"  MACs: {len(data['macs'])}")
                    except Exception as e:
                        logger.error(f"  MACs failed: {e}")
                    self._pause()

                    try:
                        logger.info("  Fetching STP summary...")
                        data['stp'] = collector.get_spanning_tree_summary()
                        logger.info("  STP: OK")
                    except Exception as e:
                        logger.error(f"  STP failed: {e}")
                    self._pause()

                collector.disconnect()
                logger.info("  Disconnected")

            except Exception as e:
                logger.error(f"  ERROR: {e}")

            all_data[hostname] = data

        logger.info("\n" + "=" * 80)
        logger.info(f"COLLECTED DATA FROM {len(all_data)} DEVICES")
        logger.info("=" * 80)

        return all_data

    def build_graph(self, data, debug=False):
        """Build graph from collected data"""
        logger.info("\n" + "=" * 80)
        logger.info("BUILDING GRAPH")
        logger.info("=" * 80)

        # Optional debug output
        if debug:
            logger.info("\n=== DEBUG: COLLECTED DATA ===")
            for hostname, d in data.items():
                logger.info(f"\n[{hostname}]")
                logger.info(f"  Type: {d['type']}")
                logger.info(f"  Interfaces: {len(d['interfaces'])}")
                logger.info(f"  CDP: {len(d['cdp'])}")
                logger.info(f"  OSPF: {len(d['ospf'])}")
                logger.info(f"  VLANs: {len(d['vlans'])}")
                logger.info(f"  Trunks: {len(d['trunks'])}")
                logger.info(f"  MACs: {len(d['macs'])}")
                logger.info(f"  STP: {'Yes' if d['stp'] else 'No'}")
            logger.info("\n=== END DEBUG ===\n")

        # Clear database
        self.db.clear_database()
        self.db.create_constraints()

        # OSPF mapping
        ospf_map = {'EDGE-R1': '1.1.1.1', 'CORE-SW1': '2.2.2.2', 'CORE-SW2': '3.3.3.3'}
        rid_to_host = {v: k for k, v in ospf_map.items()}

        # Step 1: Devices
        logger.info("\n[1] Devices...")
        for hostname, d in data.items():
            ip = next((i['ip_address'] for i in d['interfaces'] if i['ip_address'] != 'unassigned'), None)
            self.db.execute_write("""
                MERGE (d:Device {hostname: $h})
                SET d.type = $t, d.ip = $ip, d.ospf_rid = $rid
            """, {'h': hostname, 't': d['type'], 'ip': ip, 'rid': ospf_map.get(hostname)})
        logger.info(f"  Created {len(data)} devices")

        # Step 2: Interfaces
        logger.info("\n[2] Interfaces...")
        count = 0
        for hostname, d in data.items():
            for iface in d['interfaces']:
                iface_id = f"{hostname}:{iface['interface']}"
                self.db.execute_write("""
                    MATCH (d:Device {hostname: $h})
                    MERGE (i:Interface {id: $id})
                    SET i.name = $name, i.ip = $ip, i.status = $status, i.protocol = $protocol
                    MERGE (d)-[:HAS_INTERFACE]->(i)
                """, {'h': hostname, 'id': iface_id, 'name': iface['interface'],
                      'ip': iface['ip_address'], 'status': iface['status'], 'protocol': iface['protocol']})
                count += 1
        logger.info(f"  Created {count} interfaces")

        # Step 3: CDP
        logger.info("\n[3] CDP links...")
        count = 0
        skipped = 0
        for hostname, d in data.items():
            for cdp in d['cdp']:
                # Skip if missing required fields
                if 'local_interface' not in cdp or 'neighbor_interface' not in cdp or 'neighbor_device' not in cdp:
                    logger.warning(f"  SKIPPED incomplete CDP from {hostname}")
                    skipped += 1
                    continue

                local = f"{hostname}:{cdp['local_interface']}"
                remote_host = cdp['neighbor_device'].split('.')[0]
                remote = f"{remote_host}:{cdp['neighbor_interface']}"

                self.db.execute_write("""
                    MATCH (l:Interface {id: $local})
                    MATCH (r:Interface {id: $remote})
                    MERGE (l)-[rel:CONNECTED_TO]->(r)
                    SET rel.via = 'CDP',
                        rel.platform = $platform,
                        rel.capabilities = $capabilities,
                        rel.neighbor_ip = $neighbor_ip
                """, {
                    'local': local,
                    'remote': remote,
                    'platform': cdp.get('platform', ''),
                    'capabilities': cdp.get('capabilities', ''),
                    'neighbor_ip': cdp.get('neighbor_ip', '')
                })
                count += 1
        logger.info(f"  Created {count} links (skipped {skipped})")

        # Step 4: OSPF
        logger.info("\n[4] OSPF neighbors...")
        count = 0
        for hostname, d in data.items():
            for ospf in d['ospf']:
                remote = rid_to_host.get(ospf['neighbor_id'])
                if remote:
                    self.db.execute_write("""
                        MATCH (l:Device {hostname: $local})
                        MATCH (r:Device {hostname: $remote})
                        MERGE (l)-[rel:OSPF_NEIGHBOR]->(r)
                        SET rel.neighbor_id = $neighbor_id,
                            rel.state = $state,
                            rel.priority = $priority,
                            rel.dead_time = $dead_time,
                            rel.address = $address,
                            rel.interface = $interface
                    """, {
                        'local': hostname,
                        'remote': remote,
                        'neighbor_id': ospf['neighbor_id'],
                        'state': ospf['state'],
                        'priority': ospf['priority'],
                        'dead_time': ospf['dead_time'],
                        'address': ospf['address'],
                        'interface': ospf['interface']
                    })
                    count += 1
        logger.info(f"  Created {count} relationships")

        # Step 5: VLANs
        logger.info("\n[5] VLANs...")
        vlan_set = set()
        for hostname, d in data.items():
            for vlan in d['vlans']:
                if vlan['vlan_id'] not in vlan_set:
                    self.db.execute_write("""
                        MERGE (v:VLAN {vlan_id: $id})
                        SET v.name = $name, v.status = $status
                    """, {'id': vlan['vlan_id'], 'name': vlan['name'], 'status': vlan['status']})
                    vlan_set.add(vlan['vlan_id'])
        logger.info(f"  Created {len(vlan_set)} VLANs")

        # Step 6: Trunks
        logger.info("\n[6] Trunks...")
        count = 0
        for hostname, d in data.items():
            for trunk in d['trunks']:
                iface_id = f"{hostname}:{trunk['port']}"
                self.db.execute_write("""
                    MATCH (i:Interface {id: $id})
                    SET i.mode = $mode,
                        i.encapsulation = $encap,
                        i.trunk_status = $status,
                        i.native_vlan = $native,
                        i.vlans_allowed = $allowed,
                        i.vlans_active = $active,
                        i.vlans_forwarding = $forwarding
                """, {
                    'id': iface_id,
                    'mode': trunk['mode'],
                    'encap': trunk['encapsulation'],
                    'status': trunk['status'],
                    'native': trunk['native_vlan'],
                    'allowed': trunk['vlans_allowed'],
                    'active': trunk['vlans_active'],
                    'forwarding': trunk.get('vlans_forwarding', '')
                })

                for vid in trunk['vlans_allowed'].split(','):
                    vid = vid.strip()
                    if vid:
                        self.db.execute_write("""
                            MATCH (i:Interface {id: $iface})
                            MATCH (v:VLAN {vlan_id: $vlan})
                            MERGE (i)-[:TRUNKS_VLAN]->(v)
                        """, {'iface': iface_id, 'vlan': vid})
                        count += 1
        logger.info(f"  Created {count} trunk-VLAN links")

        # Step 7: MACs
        logger.info("\n[7] MAC addresses...")
        count = 0
        for hostname, d in data.items():
            for mac in d['macs']:
                iface_id = f"{hostname}:{mac['port']}"
                self.db.execute_write("""
                    MERGE (m:MACAddress {mac: $mac})
                    SET m.vlan = $vlan, m.type = $type
                    WITH m
                    MATCH (i:Interface {id: $iface})
                    MERGE (m)-[:LEARNED_ON]->(i)
                """, {'mac': mac['mac_address'], 'vlan': mac['vlan'], 'type': mac['type'], 'iface': iface_id})
                count += 1
        logger.info(f"  Created {count} MACs")

        # Step 8: STP
        logger.info("\n[8] STP info...")
        count = 0
        for hostname, d in data.items():
            if d['stp'] and 'config' in d['stp']:
                config = d['stp']['config']
                self.db.execute_write("""
                    MATCH (dev:Device {hostname: $h})
                    SET dev.stp_mode = $mode,
                        dev.stp_root_bridge_for = $root,
                        dev.stp_portfast_default = $portfast,
                        dev.stp_loopguard = $loopguard,
                        dev.stp_bpduguard = $bpduguard,
                        dev.stp_bpdufilter = $bpdufilter
                """, {
                    'h': hostname,
                    'mode': config.get('mode', ''),
                    'root': config.get('root_bridge_for', ''),
                    'portfast': config.get('portfast_default', ''),
                    'loopguard': config.get('loopguard', ''),
                    'bpduguard': config.get('bpduguard', ''),
                    'bpdufilter': config.get('bpdufilter', '')
                })
                count += 1
        logger.info(f"  Updated {count} devices")

        stats = self.db.get_stats()
        logger.info("\n" + "=" * 80)
        logger.info("DONE!")
        logger.info(f"Nodes: {stats['nodes']} | Relationships: {stats['relationships']}")
        logger.info("=" * 80)

    def run(self):
        """Main entry: collect data then build graph"""
        data = self.collect_data()
        self.build_graph(data)

    def close(self):
        """Cleanup"""
        self.db.close()

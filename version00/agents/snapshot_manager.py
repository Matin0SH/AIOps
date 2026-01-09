"""
Snapshot Manager - Select and load network snapshots into Neo4j
"""
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from neo4j import GraphDatabase
import yaml


class SnapshotManager:
    """Manage network snapshots - list, select, and load into Neo4j

    Supports multiple snapshots loaded simultaneously, isolated by snapshot_id.
    Each snapshot is completely separate and can be queried independently.
    """

    def __init__(self, snapshots_dir: str = None, config_dir: str = None):
        """Initialize snapshot manager

        Args:
            snapshots_dir: Path to snapshots directory (default: graph/snapshots)
            config_dir: Path to config directory (default: graph/config)
        """
        if snapshots_dir is None:
            self.snapshots_dir = Path(__file__).parent.parent / 'graph' / 'snapshots'
        else:
            self.snapshots_dir = Path(snapshots_dir)

        if config_dir is None:
            self.config_dir = Path(__file__).parent.parent / 'graph' / 'config'
        else:
            self.config_dir = Path(config_dir)

        # Load Neo4j config
        neo4j_cfg = self._load_yaml(self.config_dir / 'neo4j.yaml')['connection']
        self.driver = GraphDatabase.driver(
            neo4j_cfg['uri'],
            auth=(neo4j_cfg['user'], neo4j_cfg['password'])
        )

        # Track active snapshot for queries (default: latest)
        self.active_snapshot_id = None

    def _load_yaml(self, file_path: Path) -> dict:
        """Load YAML configuration"""
        with open(file_path, 'r') as f:
            return yaml.safe_load(f)

    def list_snapshots(self) -> List[Dict]:
        """List all available snapshots with metadata

        Returns:
            List of dicts with snapshot info: {index, filename, timestamp, devices, size}
        """
        snapshots = []
        json_files = sorted(self.snapshots_dir.glob('*.json'), reverse=True)

        for idx, json_file in enumerate(json_files, 1):
            # Load snapshot to get metadata
            with open(json_file, 'r') as f:
                data = json.load(f)

            snapshot_info = {
                'index': idx,
                'filename': json_file.name,
                'path': str(json_file),
                'snapshot_id': data.get('snapshot_id', 'unknown'),
                'devices': len(data.get('devices', [])),
                'size_kb': json_file.stat().st_size / 1024
            }

            # Parse timestamp from snapshot_id
            try:
                timestamp = datetime.fromisoformat(data['snapshot_id'])
                snapshot_info['timestamp'] = timestamp.strftime('%Y-%m-%d %H:%M:%S')
            except:
                snapshot_info['timestamp'] = 'unknown'

            snapshots.append(snapshot_info)

        return snapshots

    def display_snapshots(self) -> List[Dict]:
        """Display all snapshots in a readable format

        Returns:
            List of snapshot info dicts
        """
        snapshots = self.list_snapshots()

        if not snapshots:
            print("No snapshots found in:", self.snapshots_dir)
            return []

        print("\n" + "="*80)
        print("AVAILABLE NETWORK SNAPSHOTS")
        print("="*80)
        print(f"{'#':<4} {'Timestamp':<20} {'Devices':<10} {'Size':<10} {'Filename':<30}")
        print("-"*80)

        for snap in snapshots:
            print(f"{snap['index']:<4} {snap['timestamp']:<20} {snap['devices']:<10} "
                  f"{snap['size_kb']:.1f} KB    {snap['filename']:<30}")

        print("="*80)
        return snapshots

    def clear_neo4j(self):
        """Clear all data from Neo4j database"""
        print("\n[WARNING] Clearing all data from Neo4j...")

        with self.driver.session() as session:
            # Delete all relationships
            session.run("MATCH ()-[r]->() DELETE r")

            # Delete all nodes
            session.run("MATCH (n) DELETE n")

        print("[OK] Neo4j database cleared")

    def load_snapshot(self, snapshot_index: int = None, snapshot_path: str = None, set_active: bool = True):
        """Load a snapshot into Neo4j (keeps existing snapshots intact)

        Args:
            snapshot_index: Index from list_snapshots() (1-based)
            snapshot_path: Direct path to snapshot file
            set_active: Set this snapshot as active for queries (default: True)

        Either snapshot_index OR snapshot_path must be provided.
        Multiple snapshots can be loaded simultaneously - they are isolated by snapshot_id.
        """
        # Determine which snapshot to load
        if snapshot_index is not None:
            snapshots = self.list_snapshots()
            if snapshot_index < 1 or snapshot_index > len(snapshots):
                raise ValueError(f"Invalid snapshot index: {snapshot_index}. Must be 1-{len(snapshots)}")

            snapshot_file = Path(snapshots[snapshot_index - 1]['path'])
        elif snapshot_path is not None:
            snapshot_file = Path(snapshot_path)
            if not snapshot_file.exists():
                raise FileNotFoundError(f"Snapshot file not found: {snapshot_path}")
        else:
            raise ValueError("Must provide either snapshot_index or snapshot_path")

        # Load snapshot data
        print(f"\n[LOADING] {snapshot_file.name}")
        with open(snapshot_file, 'r') as f:
            network_data = json.load(f)

        snapshot_id = network_data['snapshot_id']

        # Check if this snapshot is already loaded
        if self.is_snapshot_loaded(snapshot_id):
            print(f"[INFO] Snapshot {snapshot_id} is already loaded in Neo4j")
            if set_active:
                self.active_snapshot_id = snapshot_id
                print(f"[OK] Set active snapshot to: {snapshot_id}")
            return {
                'snapshot_id': snapshot_id,
                'already_loaded': True
            }

        print("\n" + "="*70)
        print("FEEDING SNAPSHOT TO NEO4J")
        print("="*70)
        print(f"Snapshot ID: {snapshot_id}")
        print(f"Devices: {len(network_data['devices'])}")

        with self.driver.session() as session:
            # ==================== PHASE 0: CREATE SNAPSHOT NODE ====================
            print("\n[PHASE 0] Creating Snapshot Node")
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
            print(f"[OK] Snapshot node created")

            # ==================== PHASE 1: CREATE DEVICE NODES ====================
            print("\n[PHASE 1] Creating Device Nodes")
            for device_data in network_data['devices']:
                session.run("""
                    MERGE (d:Device {hostname: $hostname})
                    SET d.type = $type,
                        d.ip_address = $ip_address,
                        d.snapshot_id = $snapshot_id
                """, {
                    'hostname': device_data['hostname'],
                    'type': device_data['type'],
                    'ip_address': device_data.get('ip_address', ''),
                    'snapshot_id': snapshot_id
                })
            print(f"[OK] Created {len(network_data['devices'])} devices")

            # ==================== PHASE 2: CREATE INTERFACES ====================
            print("\n[PHASE 2] Creating Interfaces")
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

            # ==================== PHASE 3: STORE EXTRA DATA ====================
            print("\n[PHASE 3] Storing Switch Extra Data")
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
                            d.trunks = $trunks
                    """, {
                        'hostname': hostname,
                        'vlans': vlans_json,
                        'macs': macs_json,
                        'stp': stp_json,
                        'trunks': trunks_json
                    })
            print(f"[OK] Extra data stored")

            # ==================== PHASE 4: BUILD LOOKUPS ====================
            print("\n[PHASE 4] Building Lookups")

            # Interface lookup
            iface_by_name = {}
            for device_data in network_data['devices']:
                hostname = device_data['hostname']
                for iface in device_data['interfaces']:
                    iface_by_name[(hostname, iface['interface'])] = iface

            # IP-to-Device lookup
            device_by_ip = {}
            for device_data in network_data['devices']:
                ip = device_data.get('ip_address')
                if ip:
                    device_by_ip[ip] = device_data['hostname']

            print(f"[OK] Indexed {len(iface_by_name)} interfaces, {len(device_by_ip)} devices")

            # ==================== PHASE 5: CREATE CDP CONNECTIONS ====================
            print("\n[PHASE 5] Creating CDP Connections")
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
                                r.snapshot_id = $snapshot_id
                        """, {
                            'local_id': local_id,
                            'remote_id': remote_id,
                            'neighbor_ip': cdp.get('neighbor_ip', ''),
                            'snapshot_id': snapshot_id
                        })
                        cdp_count += 1
            print(f"[OK] Created {cdp_count} CDP connections")

            # ==================== PHASE 6: CREATE OSPF CONNECTIONS ====================
            print("\n[PHASE 6] Creating OSPF Connections")
            ospf_count = 0
            for device_data in network_data['devices']:
                hostname = device_data['hostname']
                for ospf in device_data.get('ospf_neighbors', []):
                    neighbor_address = ospf.get('address', '')
                    neighbor_hostname = device_by_ip.get(neighbor_address)

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
        print("[SUCCESS] SNAPSHOT LOADED INTO NEO4J")
        print(f"  - Devices: {len(network_data['devices'])}")
        print(f"  - Interfaces: {interface_count}")
        print(f"  - CDP connections: {cdp_count}")
        print(f"  - OSPF connections: {ospf_count}")
        print("="*70)

        # Set as active snapshot if requested
        if set_active:
            self.active_snapshot_id = snapshot_id
            print(f"\n[OK] Active snapshot set to: {snapshot_id}")

        return {
            'snapshot_id': snapshot_id,
            'devices': len(network_data['devices']),
            'interfaces': interface_count,
            'cdp_connections': cdp_count,
            'ospf_connections': ospf_count,
            'already_loaded': False
        }

    def is_snapshot_loaded(self, snapshot_id: str) -> bool:
        """Check if a snapshot is already loaded in Neo4j

        Args:
            snapshot_id: The snapshot ID to check

        Returns:
            True if snapshot exists in Neo4j, False otherwise
        """
        with self.driver.session() as session:
            result = session.run(
                "MATCH (s:Snapshot {id: $snapshot_id}) RETURN count(s) AS count",
                {'snapshot_id': snapshot_id}
            )
            record = result.single()
            return record['count'] > 0 if record else False

    def get_loaded_snapshots(self) -> List[Dict]:
        """Get all snapshots currently loaded in Neo4j

        Returns:
            List of dicts with snapshot info: {snapshot_id, timestamp, device_count, is_active}
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (s:Snapshot)
                RETURN s.id AS snapshot_id,
                       s.timestamp AS timestamp,
                       s.device_count AS device_count
                ORDER BY s.timestamp DESC
            """)

            snapshots = []
            for record in result:
                snapshot_info = {
                    'snapshot_id': record['snapshot_id'],
                    'timestamp': record['timestamp'],
                    'device_count': record['device_count'],
                    'is_active': record['snapshot_id'] == self.active_snapshot_id
                }
                snapshots.append(snapshot_info)

            return snapshots

    def display_loaded_snapshots(self):
        """Display all snapshots currently loaded in Neo4j"""
        loaded = self.get_loaded_snapshots()

        if not loaded:
            print("No snapshots loaded in Neo4j")
            return []

        print("\n" + "="*80)
        print("SNAPSHOTS LOADED IN NEO4J")
        print("="*80)
        print(f"{'Snapshot ID':<40} {'Devices':<10} {'Active':<10}")
        print("-"*80)

        for snap in loaded:
            active_marker = "  *** " if snap['is_active'] else ""
            print(f"{snap['snapshot_id']:<40} {snap['device_count']:<10} {active_marker}")

        print("="*80)
        if self.active_snapshot_id:
            print(f"Active snapshot: {self.active_snapshot_id}")
        else:
            print("No active snapshot set")
        print("="*80)

        return loaded

    def set_active_snapshot(self, snapshot_id: str):
        """Set the active snapshot for queries

        Args:
            snapshot_id: The snapshot ID to set as active

        Raises:
            ValueError: If snapshot is not loaded in Neo4j
        """
        if not self.is_snapshot_loaded(snapshot_id):
            raise ValueError(f"Snapshot {snapshot_id} is not loaded in Neo4j. Load it first.")

        self.active_snapshot_id = snapshot_id
        print(f"[OK] Active snapshot set to: {snapshot_id}")

    def get_active_snapshot(self) -> Optional[str]:
        """Get the currently active snapshot ID

        Returns:
            Active snapshot ID or None if not set
        """
        return self.active_snapshot_id

    def delete_snapshot(self, snapshot_id: str):
        """Delete a specific snapshot from Neo4j

        Args:
            snapshot_id: The snapshot ID to delete

        This removes all nodes and relationships for this snapshot only.
        """
        if not self.is_snapshot_loaded(snapshot_id):
            print(f"[INFO] Snapshot {snapshot_id} is not loaded")
            return

        print(f"\n[WARNING] Deleting snapshot: {snapshot_id}")

        with self.driver.session() as session:
            # Delete relationships
            session.run("""
                MATCH ()-[r {snapshot_id: $snapshot_id}]->()
                DELETE r
            """, {'snapshot_id': snapshot_id})

            # Delete nodes (Interfaces and Devices)
            session.run("""
                MATCH (n {snapshot_id: $snapshot_id})
                DELETE n
            """, {'snapshot_id': snapshot_id})

            # Delete snapshot node
            session.run("""
                MATCH (s:Snapshot {id: $snapshot_id})
                DELETE s
            """, {'snapshot_id': snapshot_id})

        print(f"[OK] Snapshot {snapshot_id} deleted from Neo4j")

        # Clear active if this was the active snapshot
        if self.active_snapshot_id == snapshot_id:
            self.active_snapshot_id = None
            print("[INFO] Active snapshot cleared")

    def get_current_snapshot(self) -> Optional[str]:
        """Get the snapshot_id of currently loaded data in Neo4j
        DEPRECATED: Use get_loaded_snapshots() instead for multi-snapshot support

        Returns:
            Snapshot ID string or None if no data loaded
        """
        with self.driver.session() as session:
            result = session.run("MATCH (s:Snapshot) RETURN s.id AS snapshot_id LIMIT 1")
            record = result.single()
            return record['snapshot_id'] if record else None

    def close(self):
        """Close Neo4j connection"""
        self.driver.close()

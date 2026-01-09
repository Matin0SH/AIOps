"""
Graph utilities for Neo4j scripts.
Shared helpers for config loading and driver lifecycle.
"""
from pathlib import Path
import yaml
from neo4j import GraphDatabase


def _load_yaml(file_path):
    with open(file_path, "r") as handle:
        return yaml.safe_load(handle)


def _config_dir():
    return Path(__file__).parent / "config"


def load_devices(config_dir=None):
    config_dir = config_dir or _config_dir()
    return _load_yaml(config_dir / "devices.yaml")["devices"]


def load_neo4j_connection(config_dir=None):
    config_dir = config_dir or _config_dir()
    return _load_yaml(config_dir / "neo4j.yaml")["connection"]


def create_driver(connection):
    return GraphDatabase.driver(
        connection["uri"],
        auth=(connection["user"], connection["password"]),
    )


class GraphClient:
    """Small wrapper for Neo4j driver lifecycle."""

    def __init__(self, connection=None, config_dir=None):
        conn = connection or load_neo4j_connection(config_dir)
        self._driver = create_driver(conn)

    def session(self):
        return self._driver.session()

    def close(self):
        self._driver.close()

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc_val, _exc_tb):
        self.close()
        return False


INDEX_QUERIES = [
    "CREATE INDEX device_hostname IF NOT EXISTS FOR (d:Device) ON (d.hostname)",
    "CREATE INDEX interface_id IF NOT EXISTS FOR (i:Interface) ON (i.id)",
    "CREATE INDEX vlan_id IF NOT EXISTS FOR (v:VLAN) ON (v.id)",
    "CREATE INDEX snapshot_id IF NOT EXISTS FOR (s:Snapshot) ON (s.id)",
    "CREATE INDEX mac_address IF NOT EXISTS FOR (m:MACAddress) ON (m.address)",
]


def clear_db(connection=None, config_dir=None):
    """Delete all nodes and relationships."""
    with GraphClient(connection=connection, config_dir=config_dir) as client:
        with client.session() as session:
            session.run("MATCH (n) DETACH DELETE n")


def create_indexes(session):
    """Create Neo4j indexes for performance."""
    for index_query in INDEX_QUERIES:
        session.run(index_query)


def create_devices(session, devices):
    """Create Device nodes from YAML - minimal skeleton only."""
    payload = []
    for hostname, config in devices.items():
        if not config.get("enabled", True):
            continue
        payload.append({
            "hostname": hostname,
            "type": config["type"],
            "ip_address": config.get("ip_address", ""),
            "mgmt_ip": config["mgmt_ip"],
            "mgmt_port": config["mgmt_port"],
        })

    session.run("""
        UNWIND $devices AS d
        MERGE (n:Device {hostname: d.hostname})
        SET n.type = d.type,
            n.ip_address = d.ip_address,
            n.mgmt_ip = d.mgmt_ip,
            n.mgmt_port = d.mgmt_port,
            n.created_at = datetime()
    """, {"devices": payload})

    return len(payload)


def get_device_count(session):
    """Return current Device node count."""
    result = session.run("MATCH (d:Device) RETURN count(d) AS total")
    return result.single()["total"]


def build_baseline(connection=None, config_dir=None):
    """Build baseline skeleton and return counts."""
    devices = load_devices(config_dir)
    with GraphClient(connection=connection, config_dir=config_dir) as client:
        with client.session() as session:
            create_indexes(session)
            created = create_devices(session, devices)
            total = get_device_count(session)
            return {"created": created, "total": total}


def run_baseline_build():
    """Command entrypoint for building baseline skeleton."""
    counts = build_baseline()
    print(f"Baseline created: {counts['created']} devices ({counts['total']} total).")


def run_clear_db():
    """Command entrypoint for clearing the database."""
    clear_db()
    print("Database cleared.")


def list_snapshots(snapshot_dir=None):
    """Return snapshot files in structured/graph/snapshots as JSON-friendly data."""
    base_dir = Path(snapshot_dir) if snapshot_dir else Path(__file__).parent / "snapshots"
    if not base_dir.exists():
        return {"snapshots": []}

    snapshots = []
    for path in base_dir.iterdir():
        if path.is_file() and path.suffix.lower() == ".json":
            snapshots.append(path.name)

    snapshots.sort()
    return {"snapshots": snapshots}

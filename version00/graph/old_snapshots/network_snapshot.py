"""
Network Snapshot
Creates the JSON snapshot, then writes physical interface links to Neo4j.
"""
from itertools import combinations

from network_fetch import NetworkFetcher


def is_physical_interface(name):
    return name.startswith("GigabitEthernet") and "." not in name


def normalize_ip(ip_address):
    if not ip_address or ip_address.lower() == "unassigned":
        return ""
    return ip_address


def build_physical_cdp_links(network_data):
    """
    Build physical link records from CDP, enriched with interface metadata.
    Returns a list of dicts ready to be written to Neo4j.
    """
    devices_by_name = {}
    iface_by_name = {}

    for device in network_data.get("devices", []):
        hostname = device.get("hostname", "")
        devices_by_name[hostname] = device
        for iface in device.get("interfaces", []):
            iface_name = iface.get("interface", "")
            iface_by_name[(hostname, iface_name)] = iface

    links = []
    snapshot_id = network_data.get("snapshot_id", "")

    for hostname, device in devices_by_name.items():
        for cdp in device.get("cdp_neighbors", []):
            local_iface_name = cdp.get("local_interface", "")
            neighbor_device = cdp.get("neighbor_device", "").split(".")[0]
            neighbor_iface_name = cdp.get("neighbor_interface", "")

            if not local_iface_name or not neighbor_device or not neighbor_iface_name:
                continue

            local_iface = iface_by_name.get((hostname, local_iface_name), {})
            remote_iface = iface_by_name.get((neighbor_device, neighbor_iface_name), {})

            links.append(
                {
                    "snapshot_id": snapshot_id,
                    "local_device": hostname,
                    "local_interface": local_iface_name,
                    "remote_device": neighbor_device,
                    "remote_interface": neighbor_iface_name,
                    "neighbor_ip": cdp.get("neighbor_ip", ""),
                    "local_ok": local_iface.get("ok", ""),
                    "local_method": local_iface.get("method", ""),
                    "local_status": local_iface.get("status", ""),
                    "local_protocol": local_iface.get("protocol", ""),
                    "remote_ok": remote_iface.get("ok", ""),
                    "remote_method": remote_iface.get("method", ""),
                    "remote_status": remote_iface.get("status", ""),
                    "remote_protocol": remote_iface.get("protocol", ""),
                }
            )

    return links


def write_physical_links(fetcher, network_data):
    snapshot_id = network_data["snapshot_id"]

    ip_to_interfaces = {}

    with fetcher.driver.session() as session:
        session.run(
            """
            MERGE (s:Snapshot {id: $snapshot_id})
            SET s.timestamp = datetime($snapshot_id),
                s.type = 'network'
            """,
            {"snapshot_id": snapshot_id},
        )

        for device_data in network_data.get("devices", []):
            hostname = device_data["hostname"]
            device_type = device_data.get("type", "")

            session.run(
                """
                MERGE (d:Device {hostname: $hostname})
                SET d.type = $type
                WITH d
                MATCH (s:Snapshot {id: $snapshot_id})
                MERGE (d)-[:SNAPSHOT_AT]->(s)
                """,
                {
                    "hostname": hostname,
                    "type": device_type,
                    "snapshot_id": snapshot_id,
                },
            )

            for iface in device_data.get("interfaces", []):
                name = iface.get("interface", "")
                if not is_physical_interface(name):
                    continue

                ip_address = normalize_ip(iface.get("ip_address", ""))
                iface_id = f"{hostname}:{name}"

                session.run(
                    """
                    MATCH (d:Device {hostname: $hostname})
                    MATCH (s:Snapshot {id: $snapshot_id})
                    MERGE (i:Interface {id: $iface_id})
                    SET i.name = $name,
                        i.ip_address = $ip_address,
                        i.status = $status,
                        i.protocol = $protocol
                    MERGE (d)-[:HAS_INTERFACE]->(i)
                    MERGE (i)-[:STATE_IN]->(s)
                    """,
                    {
                        "hostname": hostname,
                        "snapshot_id": snapshot_id,
                        "iface_id": iface_id,
                        "name": name,
                        "ip_address": ip_address,
                        "status": iface.get("status", ""),
                        "protocol": iface.get("protocol", ""),
                    },
                )

                if ip_address:
                    ip_to_interfaces.setdefault(ip_address, []).append(iface_id)

        for ip_address, iface_ids in ip_to_interfaces.items():
            if len(iface_ids) < 2:
                continue

            for a_id, b_id in combinations(sorted(set(iface_ids)), 2):
                session.run(
                    """
                    MATCH (a:Interface {id: $a_id})
                    MATCH (b:Interface {id: $b_id})
                    MERGE (a)-[r:PHYSICAL_LINK]->(b)
                    SET r.snapshot_id = $snapshot_id,
                        r.ip_address = $ip_address
                    """,
                    {
                        "a_id": a_id,
                        "b_id": b_id,
                        "snapshot_id": snapshot_id,
                        "ip_address": ip_address,
                    },
                )


def main():
    fetcher = NetworkFetcher()
    try:
        network_data = fetcher.fetch_all()
        write_physical_links(fetcher, network_data)
    finally:
        fetcher.driver.close()


if __name__ == "__main__":
    main()

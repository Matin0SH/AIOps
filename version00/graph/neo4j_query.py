"""
Neo4j Query Helper
Run common queries to explore the graph
"""
from neo4j import GraphDatabase
import json

uri = "bolt://localhost:7687"
user = "neo4j"
password = "123456789"

driver = GraphDatabase.driver(uri, auth=(user, password))

def show_device_details(hostname):
    """Show all details of a device"""
    with driver.session() as session:
        result = session.run("""
            MATCH (d:Device {hostname: $hostname})
            RETURN d
        """, {'hostname': hostname})

        record = result.single()
        if record:
            device = dict(record['d'])
            print(f"\n=== DEVICE: {hostname} ===")
            for key, value in device.items():
                print(f"  {key}: {value}")
        else:
            print(f"Device {hostname} not found")

def show_device_interfaces(hostname):
    """Show all interfaces of a device"""
    with driver.session() as session:
        result = session.run("""
            MATCH (d:Device {hostname: $hostname})-[:HAS_INTERFACE]->(i:Interface)
            RETURN i
            ORDER BY i.name
        """, {'hostname': hostname})

        print(f"\n=== INTERFACES FOR {hostname} ===")
        for record in result:
            iface = dict(record['i'])
            print(f"\n  {iface.get('name', 'unknown')}:")
            for key, value in iface.items():
                if key != 'name':
                    print(f"    {key}: {value}")

def show_connections(hostname):
    """Show all physical connections from a device"""
    with driver.session() as session:
        result = session.run("""
            MATCH (d:Device {hostname: $hostname})-[:HAS_INTERFACE]->(local:Interface)
            -[r:CONNECTED_TO]->(remote:Interface)<-[:HAS_INTERFACE]-(remote_device:Device)
            RETURN local.name as local_port,
                   remote_device.hostname as remote_device,
                   remote.name as remote_port,
                   r.protocol as protocol
        """, {'hostname': hostname})

        print(f"\n=== CONNECTIONS FROM {hostname} ===")
        for record in result:
            print(f"  {record['local_port']} -> {record['remote_device']}:{record['remote_port']} ({record['protocol']})")

def show_ospf_neighbors(hostname):
    """Show OSPF neighbors of a device"""
    with driver.session() as session:
        result = session.run("""
            MATCH (d:Device {hostname: $hostname})-[r:OSPF_NEIGHBOR]->(n:Device)
            RETURN n.hostname as neighbor, r.state as state, r.priority as priority
        """, {'hostname': hostname})

        print(f"\n=== OSPF NEIGHBORS FOR {hostname} ===")
        for record in result:
            print(f"  {record['neighbor']} - State: {record['state']}, Priority: {record['priority']}")

def show_all_devices():
    """Show all devices in the graph"""
    with driver.session() as session:
        result = session.run("""
            MATCH (d:Device)
            RETURN d.hostname as hostname, d.type as type, d.ip_address as ip
            ORDER BY d.hostname
        """)

        print("\n=== ALL DEVICES ===")
        for record in result:
            print(f"  {record['hostname']} ({record['type']}) - {record['ip']}")

# Example usage
if __name__ == "__main__":
    print("=" * 60)
    print("NEO4J GRAPH QUERY TOOL")
    print("=" * 60)

    # Show all devices
    show_all_devices()

    # Show EDGE-R1 details
    show_device_details('EDGE-R1')

    # Show EDGE-R1 interfaces
    show_device_interfaces('EDGE-R1')

    # Show connections
    show_connections('EDGE-R1')

    # Show OSPF neighbors
    show_ospf_neighbors('EDGE-R1')

    print("\n" + "=" * 60)

driver.close()

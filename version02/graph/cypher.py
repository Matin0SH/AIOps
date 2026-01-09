"""
Cypher helpers + LangChain tools for graph queries.

Design goals:
- Clean, predictable query helpers
- Consistent logging
- Tool wrappers for agent usage
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool

try:
    from .base import GraphClient
except ImportError:
    from base import GraphClient


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


# ============================================================================
# INTERNAL HELPERS
# ============================================================================

def _deduplicate_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    unique = []
    for record in records:
        record_hash = json.dumps(record, sort_keys=True)
        if record_hash in seen:
            continue
        seen.add(record_hash)
        unique.append(record)
    return unique


def _run_query(
    cypher: str,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = 30,
    deduplicate: bool = True,
) -> List[Dict[str, Any]]:
    with GraphClient() as client:
        with client.session() as session:
            result = session.run(cypher, params or {}, timeout=timeout)
            records = result.data()
            if deduplicate:
                return _deduplicate_records(records)
            return records


# ============================================================================
# QUERY HELPERS (PURE FUNCTIONS)
# ============================================================================

def list_devices() -> List[Dict[str, Any]]:
    """List all devices (hostname, type, IP)."""
    return _run_query("""
        MATCH (d:Device)
        RETURN d.hostname AS host, d.type AS type, d.ip_address AS ip
        ORDER BY host
    """)


def count_interfaces() -> List[Dict[str, Any]]:
    """Count interfaces per device."""
    return _run_query("""
        MATCH (d:Device)-[:HAS_INTERFACE]->(i:Interface)
        RETURN d.hostname AS host, count(i) AS interface_count
        ORDER BY interface_count DESC
    """)


def show_topology() -> List[Dict[str, Any]]:
    """Show full CDP physical topology."""
    return _run_query("""
        MATCH (d1:Device)-[:HAS_INTERFACE]->(i1:Interface)-[r:CONNECTED_TO]->(i2:Interface)<-[:HAS_INTERFACE]-(d2:Device)
        RETURN d1.hostname AS from, i1.name AS from_if, d2.hostname AS to, i2.name AS to_if, r.protocol AS protocol
        ORDER BY from, to
    """)


def find_down_interfaces() -> List[Dict[str, Any]]:
    """List interfaces that are down or not operational."""
    return _run_query("""
        MATCH (d:Device)-[:HAS_INTERFACE]->(i:Interface)
        WHERE i.status <> 'up' OR i.protocol <> 'up'
        RETURN d.hostname AS host, i.name AS iface, i.status AS status, i.protocol AS protocol
        ORDER BY host, iface
    """)


def show_ospf_neighbors() -> List[Dict[str, Any]]:
    """Show all OSPF neighbors (global)."""
    return _run_query("""
        MATCH (d:Device)-[r:OSPF_NEIGHBOR]->(n:Device)
        RETURN d.hostname AS local, n.hostname AS neighbor, r.neighbor_id AS neighbor_id, r.state AS state, r.neighbor_address AS neighbor_ip, r.local_interface AS local_if
        ORDER BY local, neighbor
    """)


def show_up_interfaces() -> List[Dict[str, Any]]:
    """Show all interfaces that are up/up (global)."""
    return _run_query("""
        MATCH (d:Device)-[:HAS_INTERFACE]->(i:Interface)
        WHERE i.status = 'up' AND i.protocol = 'up'
        RETURN d.hostname AS host, i.name AS iface, i.ip_address AS ip
        ORDER BY host, iface
    """)


def show_up_interfaces_device(device: str) -> List[Dict[str, Any]]:
    """Show up/up interfaces on a specific device."""
    return _run_query("""
        MATCH (d:Device {hostname: $device})-[:HAS_INTERFACE]->(i:Interface)
        WHERE i.status = 'up' AND i.protocol = 'up'
        RETURN i.name AS iface, i.ip_address AS ip
        ORDER BY iface
    """, {"device": device})


def show_interfaces_connected_device(device: str) -> List[Dict[str, Any]]:
    """Show interfaces connected to a specific device."""
    return _run_query("""
        MATCH (d:Device {hostname: $device})-[:HAS_INTERFACE]->(i:Interface)
        MATCH (i)-[r:CONNECTED_TO]->(ri:Interface)<-[:HAS_INTERFACE]-(rd:Device)
        RETURN i.name AS local_iface, rd.hostname AS remote_device, ri.name AS remote_iface, r.protocol AS protocol
        ORDER BY remote_device, remote_iface
    """, {"device": device})


def show_cdp_neighbors_device(device: str) -> List[Dict[str, Any]]:
    """Show CDP neighbors for a specific device."""
    return _run_query("""
        MATCH (d:Device {hostname: $device})-[:HAS_INTERFACE]->(i:Interface)
        MATCH (i)-[r:CONNECTED_TO]->(ri:Interface)<-[:HAS_INTERFACE]-(rd:Device)
        WHERE r.protocol = 'CDP'
        RETURN i.name AS local_iface, rd.hostname AS neighbor_device, ri.name AS neighbor_iface, r.neighbor_ip AS neighbor_ip
        ORDER BY neighbor_device, neighbor_iface
    """, {"device": device})


def show_ospf_neighbors_device(device: str) -> List[Dict[str, Any]]:
    """Show OSPF neighbors for a specific device."""
    return _run_query("""
        MATCH (d:Device {hostname: $device})-[r:OSPF_NEIGHBOR]->(n:Device)
        RETURN n.hostname AS neighbor, r.neighbor_id AS neighbor_id, r.state AS state, r.neighbor_address AS neighbor_ip, r.local_interface AS local_iface
        ORDER BY neighbor
    """, {"device": device})


def show_shortest_path(device1: str, device2: str) -> List[Dict[str, Any]]:
    """Show one shortest path between two devices."""
    return _run_query("""
        MATCH p = shortestPath((a:Device {hostname: $device1})-[:HAS_INTERFACE|CONNECTED_TO*]-(b:Device {hostname: $device2}))
        RETURN [n IN nodes(p) |
          CASE
            WHEN "Device" IN labels(n) THEN n.hostname + " (" + coalesce(n.ip_address,"") + ")"
            WHEN "Interface" IN labels(n) THEN "IF:" + coalesce(n.name, n.id, "unknown")
            ELSE "unknown"
          END
        ] AS path_nodes
    """, {"device1": device1, "device2": device2})


def show_all_paths(device1: str, device2: str) -> List[Dict[str, Any]]:
    """Show all shortest paths between two devices."""
    return _run_query("""
        MATCH p = allShortestPaths((a:Device {hostname: $device1})-[:HAS_INTERFACE|CONNECTED_TO*]-(b:Device {hostname: $device2}))
        RETURN [n IN nodes(p) |
          CASE
            WHEN "Device" IN labels(n) THEN n.hostname + " (" + coalesce(n.ip_address,"") + ")"
            WHEN "Interface" IN labels(n) THEN "IF:" + coalesce(n.name, n.id, "unknown")
            ELSE "unknown"
          END
        ] AS path_nodes
    """, {"device1": device1, "device2": device2})


# ============================================================================
# TOOL WRAPPERS (AGENT-FRIENDLY)
# ============================================================================

@tool("cypher.list_devices")
def list_devices_tool():
    """Show all devices with hostname, type, and IP for availability checks."""
    return list_devices()


# @tool("cypher.count_interfaces")
# def count_interfaces_tool():
#     return count_interfaces()


# @tool("cypher.show_topology")
# def show_topology_tool():
#     return show_topology()


# @tool("cypher.find_down_interfaces")
# def find_down_interfaces_tool():
#     return find_down_interfaces()


@tool("cypher.show_ospf_neighbors")
def show_ospf_neighbors_tool():
    """Show all OSPF neighbors across devices to see OSPF adjacencies."""
    return show_ospf_neighbors()


# @tool("cypher.show_up_interfaces")
# def show_up_interfaces_tool():
#     return show_up_interfaces()


# @tool("cypher.show_up_interfaces_device")
# def show_up_interfaces_device_tool(device: str):
#     return show_up_interfaces_device(device)


@tool("cypher.show_interfaces_connected_device")
def show_interfaces_connected_device_tool(device: str):
    """Show interfaces connected to a specific device (up links and peers)."""
    return show_interfaces_connected_device(device)


@tool("cypher.show_cdp_neighbors_device")
def show_cdp_neighbors_device_tool(device: str):
    """Show CDP neighbors for a specific device."""
    return show_cdp_neighbors_device(device)


@tool("cypher.show_ospf_neighbors_device")
def show_ospf_neighbors_device_tool(device: str):
    """Show OSPF neighbors for a specific device."""
    return show_ospf_neighbors_device(device)


@tool("cypher.show_shortest_path")
def show_shortest_path_tool(device1: str, device2: str):
    """Show one shortest path between two devices."""
    return show_shortest_path(device1, device2)


@tool("cypher.show_all_paths")
def show_all_paths_tool(device1: str, device2: str):
    """Show all shortest paths between two devices."""
    return show_all_paths(device1, device2)


__all__ = [
    "list_devices",
    # "count_interfaces",
    # "show_topology",
    # "find_down_interfaces",
    "show_ospf_neighbors",
    # "show_up_interfaces",
    # "show_up_interfaces_device",
    "show_interfaces_connected_device",
    "show_cdp_neighbors_device",
    "show_ospf_neighbors_device",
    "show_shortest_path",
    "show_all_paths",
    "list_devices_tool",
    # "count_interfaces_tool",
    # "show_topology_tool",
    # "find_down_interfaces_tool",
    "show_ospf_neighbors_tool",
    # "show_up_interfaces_tool",
    # "show_up_interfaces_device_tool",
    "show_interfaces_connected_device_tool",
    "show_cdp_neighbors_device_tool",
    "show_ospf_neighbors_device_tool",
    "show_shortest_path_tool",
    "show_all_paths_tool",
]

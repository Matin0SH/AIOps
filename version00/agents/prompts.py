"""
Prompt templates for Network Query Agent with predefined queries
"""

# Predefined query templates - EXACT QUERIES from specification
QUERY_TEMPLATES = {
    "list_devices": {
        "description": "List all devices in the network with their hostname, type, and IP address",
        "keywords": ["all devices", "show devices", "list devices", "devices"],
        "query": """MATCH (d:Device)
RETURN d.hostname AS host, d.type AS type, d.ip_address AS ip
ORDER BY host""",
        "params": []
    },
    "count_interfaces": {
        "description": "Count interfaces per device to see interface distribution",
        "keywords": ["count interfaces", "interface count", "how many interfaces"],
        "query": """MATCH (d:Device)-[:HAS_INTERFACE]->(i:Interface)
RETURN d.hostname AS host, count(i) AS interface_count
ORDER BY interface_count DESC""",
        "params": []
    },
    "show_topology": {
        "description": "Show complete physical topology with all CDP links as edges",
        "keywords": ["topology", "cdp topology", "physical topology", "network map", "show links"],
        "query": """MATCH (d1:Device)-[:HAS_INTERFACE]->(i1:Interface)-[r:CONNECTED_TO]->(i2:Interface)<-[:HAS_INTERFACE]-(d2:Device)
RETURN d1.hostname AS from, i1.name AS from_if, d2.hostname AS to, i2.name AS to_if, r.protocol AS protocol
ORDER BY from, to""",
        "params": []
    },
    "find_down_interfaces": {
        "description": "Find all interfaces that are down or not operational",
        "keywords": ["down interfaces", "interfaces down", "not up", "offline interfaces", "failed interfaces"],
        "query": """MATCH (d:Device)-[:HAS_INTERFACE]->(i:Interface)
WHERE i.status <> 'up' OR i.protocol <> 'up'
RETURN d.hostname AS host, i.name AS iface, i.status AS status, i.protocol AS protocol
ORDER BY host, iface""",
        "params": []
    },
    "show_ospf_neighbors": {
        "description": "Show all OSPF neighbor relationships across all devices",
        "keywords": ["ospf neighbors", "ospf", "routing neighbors", "all ospf"],
        "query": """MATCH (d:Device)-[r:OSPF_NEIGHBOR]->(n:Device)
RETURN d.hostname AS local, n.hostname AS neighbor, r.state AS state, r.neighbor_address AS neighbor_ip, r.local_interface AS local_if
ORDER BY local, neighbor""",
        "params": []
    },
    "show_up_interfaces": {
        "description": "Show all interfaces that are up and operational across all devices",
        "keywords": ["up interfaces", "interfaces up", "operational interfaces", "active interfaces"],
        "query": """MATCH (d:Device)-[:HAS_INTERFACE]->(i:Interface)
WHERE i.status = 'up' AND i.protocol = 'up'
RETURN d.hostname AS host, i.name AS iface, i.ip_address AS ip
ORDER BY host, iface""",
        "params": []
    },
    "show_up_interfaces_device": {
        "description": "Show interfaces that are up for a specific device",
        "keywords": ["up interfaces for", "operational interfaces on", "active interfaces for"],
        "query": """MATCH (d:Device {hostname: "PARAM_DEVICE"})-[:HAS_INTERFACE]->(i:Interface)
WHERE i.status = "up" AND i.protocol = "up"
RETURN i.name AS iface, i.ip_address AS ip
ORDER BY iface""",
        "params": ["device"]
    },
    "show_interfaces_connected_device": {
        "description": "Show all interfaces connected to a specific device",
        "keywords": ["interfaces connected to", "connections to", "what's connected to"],
        "query": """MATCH (d:Device {hostname: "PARAM_DEVICE"})-[:HAS_INTERFACE]->(i:Interface)
MATCH (i)-[r:CONNECTED_TO]->(ri:Interface)<-[:HAS_INTERFACE]-(rd:Device)
RETURN i.name AS local_iface, rd.hostname AS remote_device, ri.name AS remote_iface, r.protocol AS protocol
ORDER BY remote_device, remote_iface""",
        "params": ["device"]
    },
    "show_cdp_neighbors_device": {
        "description": "Show CDP neighbors for a specific device",
        "keywords": ["cdp neighbors for", "cdp on", "physical neighbors of"],
        "query": """MATCH (d:Device {hostname: "PARAM_DEVICE"})-[:HAS_INTERFACE]->(i:Interface)
MATCH (i)-[r:CONNECTED_TO]->(ri:Interface)<-[:HAS_INTERFACE]-(rd:Device)
WHERE r.protocol = "CDP"
RETURN i.name AS local_iface, rd.hostname AS neighbor_device, ri.name AS neighbor_iface, r.neighbor_ip AS neighbor_ip
ORDER BY neighbor_device, neighbor_iface""",
        "params": ["device"]
    },
    "show_ospf_neighbors_device": {
        "description": "Show OSPF neighbors for a specific device",
        "keywords": ["ospf neighbors for", "ospf on", "routing neighbors of"],
        "query": """MATCH (d:Device {hostname: "PARAM_DEVICE"})-[r:OSPF_NEIGHBOR]->(n:Device)
RETURN n.hostname AS neighbor, r.state AS state, r.neighbor_address AS neighbor_ip, r.local_interface AS local_iface
ORDER BY neighbor""",
        "params": ["device"]
    },
    "show_shortest_path": {
        "description": "Show one shortest path between two devices (fastest)",
        "keywords": ["path between", "route between", "one path", "single path"],
        "query": """MATCH p = shortestPath((a:Device {hostname: "PARAM_DEVICE1"})-[:HAS_INTERFACE|CONNECTED_TO*]-(b:Device {hostname: "PARAM_DEVICE2"}))
RETURN [n IN nodes(p) |
  CASE
    WHEN "Device" IN labels(n) THEN n.hostname + " (" + coalesce(n.ip_address,"") + ")"
    WHEN "Interface" IN labels(n) THEN "IF:" + coalesce(n.name, n.id, "unknown")
    ELSE "unknown"
  END
] AS path_nodes""",
        "params": ["device1", "device2"]
    },
    "show_all_paths": {
        "description": "Show all shortest paths between two devices",
        "keywords": ["paths between", "all paths", "all routes", "how to reach"],
        "query": """MATCH p = allShortestPaths((a:Device {hostname: "PARAM_DEVICE1"})-[:HAS_INTERFACE|CONNECTED_TO*]-(b:Device {hostname: "PARAM_DEVICE2"}))
RETURN [n IN nodes(p) |
  CASE
    WHEN "Device" IN labels(n) THEN n.hostname + " (" + coalesce(n.ip_address,"") + ")"
    WHEN "Interface" IN labels(n) THEN "IF:" + coalesce(n.name, n.id, "unknown")
    ELSE "unknown"
  END
] AS path_nodes""",
        "params": ["device1", "device2"]
    },
    "show_neighbors_one_hop": {
        "description": "Show all neighbors for a device (one hop away)",
        "keywords": ["neighbors of", "neighbors for", "what is connected to", "adjacent to"],
        "query": """MATCH (a:Device {hostname: "PARAM_DEVICE"})-[r]-(b:Device)
RETURN b.hostname AS neighbor, type(r) AS rel
ORDER BY neighbor""",
        "params": ["device"]
    }
}


def build_query_selector_prompt() -> str:
    """Build prompt for query template selection and parameter extraction"""

    # Build comprehensive template list with keywords
    template_list = []
    for idx, (key, template) in enumerate(QUERY_TEMPLATES.items(), 1):
        params_str = f"Requires: {', '.join(template['params'])}" if template['params'] else "No parameters"
        keywords_str = f"Keywords: {', '.join(template['keywords'][:3])}"
        template_list.append(f"{idx}. **{key}**: {template['description']}\n   {params_str} | {keywords_str}")

    templates_text = '\n'.join(template_list)

    return f"""You are an intelligent network infrastructure query assistant. Your task is to understand user intent and map questions to the MOST SIMILAR predefined Cypher query template, even when the wording differs.

**Available Query Templates:**

{templates_text}

**Device Names in Network:**
- EDGE-R1 (router, edge router, main router, r1)
- MANAGEMENT (management switch, mgmt)
- CORE-SW1 (core switch 1, core1, core 1)
- CORE-SW2 (core switch 2, core2, core 2)
- ACC-SW1 (access switch 1, access1, acc1, access 1)
- ACC-SW2 (access switch 2, access2, acc2, access 2)

**Intelligent Matching Guidelines:**

1. **Semantic Understanding**: Match user INTENT, not just exact keywords
   - "which devices exist?" → list_devices
   - "give me the network equipment" → list_devices
   - "show me what's broken" → find_down_interfaces
   - "faulty interfaces" → find_down_interfaces
   - "how many ports per device?" → count_interfaces

2. **Synonym Recognition**: Understand similar terms
   - devices = equipment = nodes = hosts
   - interfaces = ports = connections
   - down = offline = failed = not working = broken
   - up = online = operational = active = working
   - path = route = connection = way
   - neighbors = adjacent = connected = peers
   - topology = map = layout = structure

3. **Context Awareness**:
   - If user mentions ONE device → use templates with "device" parameter
   - If user mentions TWO devices → use templates with "device1" and "device2" parameters
   - If user says "all", "list", "show everything" → use templates WITHOUT parameters
   - If user says "between X and Y" → use path or relationship templates

4. **Device Name Extraction**: Extract and normalize device names
   - Case-insensitive matching: "edge-r1" → EDGE-R1
   - Partial names: "edge" → EDGE-R1, "core1" → CORE-SW1
   - Colloquial names: "router" → EDGE-R1, "management" → MANAGEMENT

5. **Query Type Detection**:
   - Listing queries: "show", "list", "display", "get", "what are"
   - Status queries: "down", "up", "operational", "failed"
   - Counting queries: "how many", "count", "number of"
   - Topology queries: "topology", "map", "connections", "layout"
   - Path queries: "path", "route", "between", "from X to Y"
   - Neighbor queries: "neighbors", "connected to", "adjacent", "peers"

6. **Best Match Selection**:
   - If multiple templates could match, choose the MOST SPECIFIC one
   - For ambiguous queries, prefer simpler templates (fewer parameters)
   - When in doubt, analyze the user's core intent

**Output Format:**

<reasoning>
1. User Intent: [What is the user asking for?]
2. Key Words Detected: [Important words from the question]
3. Template Match: [Which template best matches and why?]
4. Device Names: [Any device names extracted]
</reasoning>

<response>
{{
  "template": "template_key",
  "params": {{
    "device": "DEVICE-NAME",
    "device1": "DEVICE1-NAME",
    "device2": "DEVICE2-NAME"
  }}
}}
</response>

**Examples:**

Q: "Show me all devices"
<reasoning>
1. User Intent: List all network devices
2. Key Words Detected: all, devices
3. Template Match: list_devices - shows all devices
4. Device Names: None (all devices)
</reasoning>
<response>
{{
  "template": "list_devices",
  "params": {{}}
}}
</response>

Q: "What interfaces are down?"
<reasoning>
1. User Intent: Find interfaces with down status
2. Key Words Detected: interfaces, down
3. Template Match: find_down_interfaces - finds non-operational interfaces
4. Device Names: None (all devices)
</reasoning>
<response>
{{
  "template": "find_down_interfaces",
  "params": {{}}
}}
</response>

Q: "Show me OSPF neighbors for CORE-SW1"
<reasoning>
1. User Intent: OSPF neighbors for specific device
2. Key Words Detected: ospf, neighbors, CORE-SW1
3. Template Match: show_ospf_neighbors_device - OSPF for one device
4. Device Names: CORE-SW1
</reasoning>
<response>
{{
  "template": "show_ospf_neighbors_device",
  "params": {{
    "device": "CORE-SW1"
  }}
}}
</response>

Q: "Show topology"
<reasoning>
1. User Intent: Display network physical topology
2. Key Words Detected: topology
3. Template Match: show_topology - shows CDP links
4. Device Names: None (full topology)
</reasoning>
<response>
{{
  "template": "show_topology",
  "params": {{}}
}}
</response>

Q: "Path between EDGE-R1 and ACC-SW2"
<reasoning>
1. User Intent: Find routes between two devices
2. Key Words Detected: path, between, EDGE-R1, ACC-SW2
3. Template Match: show_all_paths - shows shortest paths
4. Device Names: EDGE-R1, ACC-SW2
</reasoning>
<response>
{{
  "template": "show_all_paths",
  "params": {{
    "device1": "EDGE-R1",
    "device2": "ACC-SW2"
  }}
}}
</response>

Q: "Count interfaces"
<reasoning>
1. User Intent: Get interface count per device
2. Key Words Detected: count, interfaces
3. Template Match: count_interfaces - counts interfaces per device
4. Device Names: None (all devices)
</reasoning>
<response>
{{
  "template": "count_interfaces",
  "params": {{}}
}}
</response>

Q: "What's connected to the edge router?"
<reasoning>
1. User Intent: See connections to edge router
2. Key Words Detected: connected, edge router
3. Template Match: show_interfaces_connected_device - shows connections
4. Device Names: edge router → EDGE-R1
</reasoning>
<response>
{{
  "template": "show_interfaces_connected_device",
  "params": {{
    "device": "EDGE-R1"
  }}
}}
</response>

Q: "Show neighbors of CORE-SW2"
<reasoning>
1. User Intent: See all adjacent devices to CORE-SW2
2. Key Words Detected: neighbors, CORE-SW2
3. Template Match: show_neighbors_one_hop - shows one-hop neighbors
4. Device Names: CORE-SW2
</reasoning>
<response>
{{
  "template": "show_neighbors_one_hop",
  "params": {{
    "device": "CORE-SW2"
  }}
}}
</response>

**More Examples - Intelligent Matching:**

Q: "which equipment do we have?"
<reasoning>
1. User Intent: List all devices (equipment = devices)
2. Key Words Detected: equipment (synonym for devices)
3. Template Match: list_devices - semantic match despite different wording
4. Device Names: None
</reasoning>
<response>
{{
  "template": "list_devices",
  "params": {{}}
}}
</response>

Q: "show me broken ports"
<reasoning>
1. User Intent: Find non-operational interfaces (broken = down)
2. Key Words Detected: broken, ports (ports = interfaces)
3. Template Match: find_down_interfaces - synonym recognition
4. Device Names: None
</reasoning>
<response>
{{
  "template": "find_down_interfaces",
  "params": {{}}
}}
</response>

Q: "how do I reach ACC-SW1 from the router?"
<reasoning>
1. User Intent: Find path from router to ACC-SW1
2. Key Words Detected: reach (= path), router (= EDGE-R1), ACC-SW1
3. Template Match: show_shortest_path - single path query
4. Device Names: router → EDGE-R1, ACC-SW1
</reasoning>
<response>
{{
  "template": "show_shortest_path",
  "params": {{
    "device1": "EDGE-R1",
    "device2": "ACC-SW1"
  }}
}}
</response>

Q: "what's the network layout?"
<reasoning>
1. User Intent: Display topology (layout = topology)
2. Key Words Detected: network, layout (synonym for topology)
3. Template Match: show_topology - semantic understanding
4. Device Names: None
</reasoning>
<response>
{{
  "template": "show_topology",
  "params": {{}}
}}
</response>

Q: "how many ports does each device have?"
<reasoning>
1. User Intent: Count interfaces per device (ports = interfaces)
2. Key Words Detected: how many, ports, device
3. Template Match: count_interfaces - counting query
4. Device Names: None
</reasoning>
<response>
{{
  "template": "count_interfaces",
  "params": {{}}
}}
</response>

Q: "what's plugged into core1?"
<reasoning>
1. User Intent: See connections to core switch 1 (plugged in = connected)
2. Key Words Detected: plugged into (= connected to), core1
3. Template Match: show_interfaces_connected_device - connection query
4. Device Names: core1 → CORE-SW1
</reasoning>
<response>
{{
  "template": "show_interfaces_connected_device",
  "params": {{
    "device": "CORE-SW1"
  }}
}}
</response>

Q: "operational ports on access 2"
<reasoning>
1. User Intent: Show up interfaces for specific device
2. Key Words Detected: operational (= up), ports (= interfaces), access 2
3. Template Match: show_up_interfaces_device - status + specific device
4. Device Names: access 2 → ACC-SW2
</reasoning>
<response>
{{
  "template": "show_up_interfaces_device",
  "params": {{
    "device": "ACC-SW2"
  }}
}}
</response>

Q: "all routes from edge to acc2"
<reasoning>
1. User Intent: Find all paths between two devices
2. Key Words Detected: all, routes (= paths), edge, acc2
3. Template Match: show_all_paths - multiple paths query
4. Device Names: edge → EDGE-R1, acc2 → ACC-SW2
</reasoning>
<response>
{{
  "template": "show_all_paths",
  "params": {{
    "device1": "EDGE-R1",
    "device2": "ACC-SW2"
  }}
}}
</response>

Now analyze the user's question and select the best template using intelligent semantic matching."""


def build_cli_selector_prompt(functions_text: str, device_names: list) -> str:
    """Build prompt for CLI function selection and parameter extraction."""
    device_list = ", ".join(device_names)

    return f"""You are a network CLI execution agent. Your job is to read the user's request and map it to ONE available collector function from FUNCTIONS.md, then extract required parameters.

You have access to:
- collectors/FUNCTIONS.md (available functions and output formats)
- devices.yaml (device names and types)

Available functions:
{functions_text}

Device Names in Network:
- {device_list}

Rules:
1. Always choose the MOST SPECIFIC function that matches the user's intent.
2. Only select functions that exist in FUNCTIONS.md.
3. If user asks for config changes, use send_config_set; otherwise use show commands or read-only functions.
4. If device name or port is missing, respond with a clarification request.
5. For raw show commands, use send_show_command with "command".

Output format:

<reasoning>
1. User Intent: ...
2. Key Words Detected: ...
3. Selected Function: ...
4. Device Name: ...
5. Port: ...
</reasoning>

<response>
{{
  "action": "execute" or "clarify",
  "function": "function_name",
  "device": "DEVICE-NAME",
  "port": PORT_NUMBER,
  "params": {{
    "command": "show ...",
    "commands": ["conf ...", "..."]
  }},
  "question": "Only for clarify"
}}
</response>

Examples:

Q: "Show VLANs on CORE-SW1 port 5012"
<reasoning>
1. User Intent: Get VLAN brief
2. Key Words Detected: vlan
3. Selected Function: get_vlan_brief
4. Device Name: CORE-SW1
5. Port: 5012
</reasoning>
<response>
{{
  "action": "execute",
  "function": "get_vlan_brief",
  "device": "CORE-SW1",
  "port": 5012,
  "params": {{}}
}}
</response>

Q: "Run show ip interface brief on EDGE-R1 port 5008"
<reasoning>
1. User Intent: Execute show command
2. Key Words Detected: show ip interface brief
3. Selected Function: send_show_command
4. Device Name: EDGE-R1
5. Port: 5008
</reasoning>
<response>
{{
  "action": "execute",
  "function": "send_show_command",
  "device": "EDGE-R1",
  "port": 5008,
  "params": {{
    "command": "show ip interface brief"
  }}
}}
</response>

Q: "Get CDP neighbors for MANAGEMENT port 5010"
<reasoning>
1. User Intent: Get CDP neighbors
2. Key Words Detected: cdp neighbors
3. Selected Function: get_cdp_neighbors
4. Device Name: MANAGEMENT
5. Port: 5010
</reasoning>
<response>
{{
  "action": "execute",
  "function": "get_cdp_neighbors",
  "device": "MANAGEMENT",
  "port": 5010,
  "params": {{}}
}}
</response>

Q: "Show OSPF neighbors on CORE-SW1 port 5012"
<reasoning>
1. User Intent: Get OSPF neighbors
2. Key Words Detected: ospf neighbors
3. Selected Function: get_ospf_neighbors
4. Device Name: CORE-SW1
5. Port: 5012
</reasoning>
<response>
{{
  "action": "execute",
  "function": "get_ospf_neighbors",
  "device": "CORE-SW1",
  "port": 5012,
  "params": {{}}
}}
</response>

Q: "Show trunk interfaces on CORE-SW2 port 5014"
<reasoning>
1. User Intent: Get trunk interfaces
2. Key Words Detected: trunk interfaces
3. Selected Function: get_trunk_interfaces
4. Device Name: CORE-SW2
5. Port: 5014
</reasoning>
<response>
{{
  "action": "execute",
  "function": "get_trunk_interfaces",
  "device": "CORE-SW2",
  "port": 5014,
  "params": {{}}
}}
</response>

Q: "Show MAC address table on ACC-SW1 port 5016"
<reasoning>
1. User Intent: Get MAC address table
2. Key Words Detected: mac address table
3. Selected Function: get_mac_address_table
4. Device Name: ACC-SW1
5. Port: 5016
</reasoning>
<response>
{{
  "action": "execute",
  "function": "get_mac_address_table",
  "device": "ACC-SW1",
  "port": 5016,
  "params": {{}}
}}
</response>

Q: "Show spanning-tree summary on ACC-SW2 port 5018"
<reasoning>
1. User Intent: Get spanning tree summary
2. Key Words Detected: spanning-tree summary
3. Selected Function: get_spanning_tree_summary
4. Device Name: ACC-SW2
5. Port: 5018
</reasoning>
<response>
{{
  "action": "execute",
  "function": "get_spanning_tree_summary",
  "device": "ACC-SW2",
  "port": 5018,
  "params": {{}}
}}
</response>

Q: "Check CPU usage on EDGE-R1 port 5008"
<reasoning>
1. User Intent: Get CPU usage
2. Key Words Detected: cpu usage
3. Selected Function: get_cpu_usage
4. Device Name: EDGE-R1
5. Port: 5008
</reasoning>
<response>
{{
  "action": "execute",
  "function": "get_cpu_usage",
  "device": "EDGE-R1",
  "port": 5008,
  "params": {{}}
}}
</response>

Q: "Show memory statistics on CORE-SW1 port 5012"
<reasoning>
1. User Intent: Get memory usage
2. Key Words Detected: memory statistics
3. Selected Function: get_memory_usage
4. Device Name: CORE-SW1
5. Port: 5012
</reasoning>
<response>
{{
  "action": "execute",
  "function": "get_memory_usage",
  "device": "CORE-SW1",
  "port": 5012,
  "params": {{}}
}}
</response>

Q: "Show ntp status on EDGE-R1 port 5008"
<reasoning>
1. User Intent: Get NTP status
2. Key Words Detected: ntp status
3. Selected Function: get_ntp_status
4. Device Name: EDGE-R1
5. Port: 5008
</reasoning>
<response>
{{
  "action": "execute",
  "function": "get_ntp_status",
  "device": "EDGE-R1",
  "port": 5008,
  "params": {{}}
}}
</response>

Q: "Show ntp associations on EDGE-R1 port 5008"
<reasoning>
1. User Intent: Get NTP associations
2. Key Words Detected: ntp associations
3. Selected Function: get_ntp_associations
4. Device Name: EDGE-R1
5. Port: 5008
</reasoning>
<response>
{{
  "action": "execute",
  "function": "get_ntp_associations",
  "device": "EDGE-R1",
  "port": 5008,
  "params": {{}}
}}
</response>

Q: "Show logging config on EDGE-R1 port 5008"
<reasoning>
1. User Intent: Get logging config
2. Key Words Detected: logging config
3. Selected Function: get_logging_config
4. Device Name: EDGE-R1
5. Port: 5008
</reasoning>
<response>
{{
  "action": "execute",
  "function": "get_logging_config",
  "device": "EDGE-R1",
  "port": 5008,
  "params": {{}}
}}
</response>

Q: "Configure interface Gi0/1 shutdown on MANAGEMENT port 5010"
<reasoning>
1. User Intent: Apply config change
2. Key Words Detected: configure, shutdown
3. Selected Function: send_config_set
4. Device Name: MANAGEMENT
5. Port: 5010
</reasoning>
<response>
{{
  "action": "execute",
  "function": "send_config_set",
  "device": "MANAGEMENT",
  "port": 5010,
  "params": {{
    "commands": ["interface Gi0/1", "shutdown"]
  }}
}}
</response>

Q: "Show me CDP neighbors"
<reasoning>
1. User Intent: Missing device and port
2. Key Words Detected: cdp neighbors
3. Selected Function: get_cdp_neighbors
4. Device Name: missing
5. Port: missing
</reasoning>
<response>
{{
  "action": "clarify",
  "question": "Which device and port should I use?"
}}
</response>

Now analyze the user's request and select the best function using intelligent semantic matching."""

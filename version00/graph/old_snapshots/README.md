# Graph-Based Network Topology System

## Overview
This system builds a dynamic network topology graph in Neo4j using:
1. **YAML-based skeleton** - Device inventory and configuration
2. **Node collectors** - Device-specific data collection (router/switch)
3. **Snapshot orchestrator** - Manages temporal snapshots for anomaly detection

---

## Directory Structure

```
graph/
├── config/
│   ├── devices.yaml           # Device inventory (connection info, features)
│   └── neo4j.yaml            # Neo4j database connection settings
│
├── collectors/               # (To be created)
│   ├── router_node_collector.py
│   └── switch_node_collector.py
│
├── baseline_builder.py       # (To be created) Creates skeleton from YAML
├── orchestrator.py           # (To be created) Manages snapshots
├── schema.cypher            # (To be created) Neo4j schema
├── test_yaml.py             # Test YAML configuration
└── README.md                # This file
```

---

## Configuration Files

### 1. devices.yaml

Defines all network devices with:
- **Device metadata**: hostname, type, IP, model
- **Management access**: IP, port, credentials
- **Features**: layer2, layer3, ospf
- **Config file reference**: Link to IOS config

**Current devices:**
- EDGE-R1 (Router) - 192.168.56.101:5008
- MANAGEMENT (Switch) - 192.168.56.101:5010
- CORE-SW1 (L3 Switch) - 192.168.56.101:5012
- CORE-SW2 (L3 Switch) - 192.168.56.101:5014
- ACC-SW1 (L2 Switch) - 192.168.56.101:5016
- ACC-SW2 (L2 Switch) - 192.168.56.101:5018

### 2. neo4j.yaml

Neo4j database connection settings:
- URI: bolt://localhost:7687
- Authentication
- Connection pool settings
- Query timeouts

---

## Testing

Run the test script to validate YAML files:

```bash
cd graph
python test_yaml.py
```

Expected output:
```
[OK] devices.yaml loaded successfully
[OK] neo4j.yaml loaded successfully
[OK] ALL YAML CONFIGURATION FILES ARE VALID
```

---

## Next Steps

1. ✅ YAML configuration (DONE)
2. ⏳ Create baseline_builder.py (Creates Device nodes from YAML)
3. ⏳ Create router_node_collector.py (Router-specific data collection)
4. ⏳ Create switch_node_collector.py (Switch-specific data collection)
5. ⏳ Create orchestrator.py (Snapshot management)
6. ⏳ Create schema.cypher (Neo4j indexes and constraints)

---

## Usage (Planned)

```bash
# Step 1: Create skeleton from YAML
python graph/baseline_builder.py

# Step 2: Collect snapshot for specific device
python graph/orchestrator.py --device EDGE-R1

# Step 3: Collect snapshot for all devices
python graph/orchestrator.py --all
```

---

## Graph Schema (Planned)

```cypher
// Nodes
(:Device {hostname, type, mgmt_ip, mgmt_port, ip_address, model, os_version})
(:Interface {id, name, ip_address, description, status, protocol})
(:VLAN {id, name, subnet})
(:Snapshot {id, timestamp, device})

// Relationships
(:Device)-[:HAS_INTERFACE]->(:Interface)
(:Device)-[:HAS_VLAN]->(:VLAN)
(:Interface)-[:TRUNKS_VLAN]->(:VLAN)
(:Interface)-[:CONNECTED_TO]->(:Interface)  // CDP
(:Device)-[:OSPF_NEIGHBOR]->(:Device)       // OSPF
(:Device)-[:SNAPSHOT_AT]->(:Snapshot)       // Temporal
```

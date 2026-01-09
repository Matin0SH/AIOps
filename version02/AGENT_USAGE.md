# Network Configuration Agent - Usage Guide

## Overview

The Network Configuration Agent is a ReAct agent that orchestrates 11 tools across 3 categories:
- **Scholar Tools**: Search configuration notebooks (RAG)
- **Executor Tools**: Execute configurations on devices
- **Cypher Tools**: Query network topology (Neo4j)

Built with **LangChain 0.3+ (2026) best practices** using the new `create_agent` API.

---

## Quick Start

### 1. Basic Usage (No Device Connection)

For read-only queries (topology, search):

```python
from agents import NetworkAgent

# Create agent (no device needed for queries)
agent = NetworkAgent(device=None, verbose=True)

# Query network topology
response = agent.run("Show me all devices in the network")
print(response['output'])

# Search for configurations
response = agent.run("How do I enable SSH?")
print(response['output'])

# Find paths
response = agent.run("What's the shortest path between R1 and R3?")
print(response['output'])
```

### 2. With Device Connection (For Execution)

To execute configurations:

```python
from agents import NetworkAgent
from tools.base import BaseDeviceCollector

# Connect to device
device = BaseDeviceCollector(
    host="10.0.0.1",
    username="admin",
    password="cisco",
    device_type="cisco_ios"
)

# Create agent with device
agent = NetworkAgent(device=device, verbose=True)

# Execute configuration
response = agent.run("Set hostname to CORE-SW-01")
print(response['output'])

# Multi-step task
response = agent.run("Enable SSH and create VLAN 10 named Engineering")
print(response['output'])
```

### 3. Using Factory Function

For more control:

```python
from agents import create_network_agent
from tools.executor import set_device_connection

# Create custom agent
agent_executor = create_network_agent(
    model_name="gemini-2.0-flash-exp",
    temperature=0,
    max_iterations=15,
    verbose=True,
    memory=True
)

# Set device (if needed)
# set_device_connection(device)

# Run
result = agent_executor.invoke({"input": "Show OSPF neighbors"})
print(result['output'])
```

### 4. CLI Usage

```bash
python agents/network_agent.py "Show me all devices"
python agents/network_agent.py "What's the path from R1 to R3?"
```

---

## Example Scenarios

### Scenario 1: Topology Discovery
```python
agent = NetworkAgent()

# List all devices
agent.run("Show me all devices")

# Check OSPF neighbors
agent.run("Show all OSPF neighbors")

# Find paths
agent.run("Show all paths between CORE-R1 and EDGE-R2")
```

### Scenario 2: Configuration Search
```python
agent = NetworkAgent()

# Search notebooks
agent.run("How do I configure OSPF?")
agent.run("What notebooks are available for VLANs?")
agent.run("Show me SSH configuration options")
```

### Scenario 3: Execute Configurations
```python
# With device connection
agent = NetworkAgent(device=device)

# Single config
agent.run("Set hostname to SW-CORE-01")

# Multi-step
agent.run("Enable SSH and configure OSPF area 0")

# With parameters
agent.run("Create VLAN 10 named Engineering")
```

### Scenario 4: Topology-Aware Configuration
```python
agent = NetworkAgent(device=device)

# Agent uses both cypher + executor tools
agent.run("Show devices connected to CORE-SW-01, then enable SSH on all of them")
```

### Scenario 5: Troubleshooting
```python
agent = NetworkAgent()

agent.run("Why can't R1 reach R3?")
# Agent will:
# 1. Check path (show_shortest_path)
# 2. Check OSPF neighbors
# 3. Check interfaces
# 4. Diagnose issue
# 5. Suggest fix (with scholar_search)
```

---

## Agent Capabilities

### Tools Available

1. **scholar_search** - Search 26 config notebooks
2. **execute_notebook** - Execute configs on device
3. **get_notebook_info** - Get parameter schemas
4. **list_devices_tool** - List all devices
5. **show_ospf_neighbors_tool** - Global OSPF adjacencies
6. **show_interfaces_connected_device_tool** - Device connections
7. **show_cdp_neighbors_device_tool** - CDP neighbors
8. **show_ospf_neighbors_device_tool** - OSPF neighbors per device
9. **show_shortest_path_tool** - Path between devices
10. **show_all_paths_tool** - All paths (redundancy)

### Agent Features

- ✅ **ReAct Loop**: Thought → Action → Observation
- ✅ **Conversation Memory**: Remembers context
- ✅ **Parameter Extraction**: Natural language → params
- ✅ **Clarification**: Asks for missing params
- ✅ **Multi-step Tasks**: Handles complex workflows
- ✅ **Error Handling**: Graceful failures
- ✅ **Risk Awareness**: Warns on HIGH risk notebooks

---

## Advanced Usage

### Memory Management
```python
agent = NetworkAgent(memory=True)

# First query
agent.run("Show me device CORE-SW-01")

# Follow-up (agent remembers context)
agent.run("Show its OSPF neighbors")
agent.run("What's connected to it?")

# Clear memory
agent.clear_memory()
```

### Update Device Connection
```python
agent = NetworkAgent(device=device1)

# Later, switch to different device
agent.set_device(device2)
agent.run("Set hostname to SW-EDGE-01")
```

### List Available Tools
```python
agent = NetworkAgent()
tools = agent.get_tools()
print(f"Available tools: {tools}")
```

### Async Support (Future)
```python
# Placeholder for future async
# response = await agent.run_async("Show devices")
```

---

## Configuration

### Environment Setup

1. Create `tools/configs/.env`:
```env
GOOGLE_API_KEY=your_gemini_api_key_here
```

2. Ensure Neo4j is running (for cypher tools)
3. Ensure FAISS index is built (for scholar_search)

### Model Selection
```python
# Fast + cheap (default)
agent = NetworkAgent(model_name="gemini-2.0-flash-exp")

# More powerful
agent = NetworkAgent(model_name="gemini-2.0-pro")
```

### Iteration Limits
```python
# Default: 15 iterations
agent = NetworkAgent(max_iterations=20)  # For complex tasks
```

---

## Best Practices

1. **Start with queries** (no device) before executing configs
2. **Use dry_run** for testing: `agent.run("Execute notebook dry_run=True")`
3. **Clear memory** between different contexts
4. **Check logs** with `verbose=True` for debugging
5. **Handle errors** gracefully - agent returns error in output

---

## Troubleshooting

### "No device connection" error
```python
# Make sure to set device before executing
agent.set_device(device)
```

### FAISS index not found
```python
# Rebuild vector store
python tools/rebuild_vdb_langchain.py
```

### Neo4j connection error
```python
# Check Neo4j is running
# Check credentials in graph/base.py
```

---

## Architecture

```
NetworkAgent (Facade)
    ↓
AgentExecutor (LangChain)
    ↓
ReAct Agent (create_react_agent)
    ↓
Tools (11 total)
    ├── scholar_search (RAG)
    ├── execute_notebook (Executor)
    ├── get_notebook_info (Executor)
    └── cypher_* (Neo4j)
```

**Built with:**
- LangChain 0.3.x
- Gemini 2.0 Flash/Pro
- FAISS (vector store)
- Neo4j (graph database)
- Pydantic (schemas)

---

## Next Steps

1. Test with read-only queries
2. Connect to device for execution
3. Build custom workflows
4. Integrate into your automation pipeline

**Questions?** Check source code in `agents/network_agent.py`

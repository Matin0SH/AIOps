"""
Demo: Build Network Graph from Live Data
Connects to all 6 devices and builds complete Neo4j graph
"""
from graph.live_builder import LiveGraphBuilder

print("=" * 80)
print("NETWORK GRAPH BUILDER - LIVE DATA DEMO")
print("=" * 80)

# Initialize builder
builder = LiveGraphBuilder(
    neo4j_uri="bolt://localhost:7687",
    neo4j_user="neo4j",
    neo4j_password="123456789"  # UPDATE THIS!
)

# Device credentials
creds = {"username": "", "password": "", "enable_secret": "cisco"}

# Add all 6 devices
builder.add_device("EDGE-R1", "router", "192.168.56.101", 5008, creds)
builder.add_device("MANAGEMENT", "switch", "192.168.56.101", 5010, creds)
builder.add_device("CORE-SW1", "switch", "192.168.56.101", 5012, creds)
builder.add_device("CORE-SW2", "switch", "192.168.56.101", 5014, creds)
builder.add_device("ACC-SW1", "switch", "192.168.56.101", 5016, creds)
builder.add_device("ACC-SW2", "switch", "192.168.56.101", 5018, creds)

# Build the graph!
builder.run()

# Cleanup
builder.close()

print("\n" + "=" * 80)
print("DONE! Graph is ready in Neo4j.")
print("Open Neo4j Browser at http://localhost:7474")
print("Try this query: MATCH (n) RETURN n LIMIT 50")
print("=" * 80)

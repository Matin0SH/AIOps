"""
Test routing table parsing on CORE-SW1 (L3 switch with OSPF routes)
"""
from collectors.switch_collector import SwitchCollector
import json

print("=" * 80)
print("Testing Routing Table Parsing on CORE-SW1")
print("=" * 80)

creds = {"username": "", "password": "", "enable_secret": "cisco"}
switch = SwitchCollector("CORE-SW1", "192.168.56.103", 5000, creds)

switch.connect()
routes = switch.get_routing_table()
print(f"\nFound {len(routes)} routes in routing table:")
print(json.dumps(routes, indent=2))
switch.disconnect()

print("\n" + "=" * 80)
print(f"✅ Routing table parsing captured {len(routes)} routes!")
print("=" * 80)

# Pretty print summary
print("\n📊 Route Summary by Protocol:")
protocols = {}
for route in routes:
    proto = route['protocol']
    protocols[proto] = protocols.get(proto, 0) + 1

for proto, count in sorted(protocols.items()):
    proto_names = {
        'O': 'OSPF',
        'C': 'Connected',
        'L': 'Local',
        'S': 'Static',
        'R': 'RIP',
        'B': 'BGP',
        'D': 'EIGRP'
    }
    print(f"  {proto_names.get(proto, proto)}: {count} routes")

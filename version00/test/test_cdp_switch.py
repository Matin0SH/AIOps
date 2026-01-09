"""
Test CDP neighbors parsing on CORE-SW2 (should capture all 4 neighbors)
"""
from collectors.switch_collector import SwitchCollector
import json

# Test on CORE-SW2 (Switch with 4 CDP neighbors)
print("=" * 80)
print("Testing CDP on CORE-SW2 (Switch)")
print("=" * 80)

creds = {"username": "", "password": "", "enable_secret": "cisco"}
switch = SwitchCollector("CORE-SW2", "192.168.56.103", 5002, creds)

switch.connect()
neighbors = switch.get_cdp_neighbors()
print(f"\nFound {len(neighbors)} CDP neighbors:")
print(json.dumps(neighbors, indent=2))
switch.disconnect()

print("\n" + "=" * 80)
print(f"✅ CDP parsing captured {len(neighbors)} neighbors!")
print("=" * 80)

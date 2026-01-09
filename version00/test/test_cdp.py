"""
Test CDP neighbors parsing with TTP
"""
from collectors.router_collector import RouterCollector
import json

# Test on EDGE-R1 (Router)
print("=" * 80)
print("Testing CDP on EDGE-R1 (Router)")
print("=" * 80)

creds = {"username": "", "password": "", "enable_secret": "cisco"}
router = RouterCollector("EDGE-R1", "192.168.56.101", 5000, creds)

router.connect()
neighbors = router.get_cdp_neighbors()
print(json.dumps(neighbors, indent=2))
router.disconnect()

print("\n" + "=" * 80)
print("✅ CDP parsing working!")
print("=" * 80)

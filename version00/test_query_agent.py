"""
Test the query agent with different queries
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from agents.query_agent import NetworkQueryAgent
import json

agent = NetworkQueryAgent()

# Test 1: Show all devices
print("="*70)
print("TEST 1: Show me all devices")
print("="*70)
result = agent.ask("Show me all devices")
print(f"\nReasoning: [hidden for display]")
print(f"\nCypher:\n{result['cypher']}")
print(f"\nCount: {result['count']}")
print(f"\nFirst result:")
if result['count'] > 0:
    print(json.dumps(result['results'][0], indent=2))

# Test 2: OSPF neighbors
print("\n" + "="*70)
print("TEST 2: Which devices have OSPF neighbors?")
print("="*70)
result = agent.ask("Which devices have OSPF neighbors?")
print(f"\nReasoning: [hidden for display]")
print(f"\nCypher:\n{result['cypher']}")
print(f"\nCount: {result['count']}")
print(f"\nFirst result:")
if result['count'] > 0:
    print(json.dumps(result['results'][0], indent=2))

# Test 3: Down interfaces
print("\n" + "="*70)
print("TEST 3: Show all down interfaces")
print("="*70)
result = agent.ask("Show all down interfaces")
print(f"\nReasoning: [hidden for display]")
print(f"\nCypher:\n{result['cypher']}")
print(f"\nCount: {result['count']}")
print(f"\nFirst result:")
if result['count'] > 0:
    print(json.dumps(result['results'][0], indent=2))

agent.close()
print("\n" + "="*70)
print("TESTS COMPLETE")
print("="*70)

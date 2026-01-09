"""
ULTRA SIMPLE - Skip enable mode if not needed
"""

from netmiko import ConnectHandler
import json
from datetime import datetime

# Device
device = {
    'device_type': 'cisco_ios_telnet',
    'host': '127.0.0.1',
    'port': 5000,
}

# Commands
commands = [
    'show cdp neighbors detail',
    'show ip interface brief',
    'show ip route',
    'show processes cpu'
]

# Connect
print("Connecting...")
connection = ConnectHandler(**device)

# Check mode
prompt = connection.find_prompt()
print(f"Prompt: {prompt}")

# Collect data
results = {'device': 'EDGE-R1', 'commands': {}}

for cmd in commands:
    print(f"Running: {cmd}")
    try:
        output = connection.send_command(cmd)
        results['commands'][cmd] = output
        print(f"  OK ({len(output)} chars)")
    except Exception as e:
        print(f"  FAILED: {e}")
        results['commands'][cmd] = f"ERROR: {e}"

# Save
connection.disconnect()

filename = 'edge_r1.json'
with open(filename, 'w') as f:
    json.dump(results, f, indent=2)

print(f"\nSaved to: {filename}")

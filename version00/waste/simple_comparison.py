"""
SIMPLE COMPARISON: Netmiko vs pyATS Control Methods
Shows exactly how each framework controls the device
"""

print("="*70)
print("METHOD 1: NETMIKO (Simple CLI Automation)")
print("="*70)

# ============================================================
# NETMIKO APPROACH (What you're using)
# ============================================================

from netmiko import ConnectHandler

# Step 1: Define connection
device = {
    'device_type': 'cisco_ios',
    'host': 'devnetsandboxiosxe.cisco.com',
    'username': 'admin',
    'password': 'C1sco12345',
    'port': 22,
}

print("\n1️⃣  Connecting to device...")
connection = ConnectHandler(**device)

print("2️⃣  Checking current MODE...")
prompt = connection.find_prompt()
print(f"   Current prompt: {prompt}")

if '#' in prompt:
    print("   ✅ In PRIVILEGED EXEC mode (can run all commands)")
elif '>' in prompt:
    print("   ⚠️  In USER EXEC mode (entering enable...)")
    connection.enable()
    print(f"   New prompt: {connection.find_prompt()}")

print("\n3️⃣  Running commands (gets RAW TEXT)...")

# Command 1
print("\n   Command: show ip interface brief")
output1 = connection.send_command('show ip interface brief')
print(f"   Output type: {type(output1)}")
print(f"   Output length: {len(output1)} characters")
print(f"   First 200 chars: {output1[:200]}...")

# Command 2
print("\n   Command: show version")
output2 = connection.send_command('show version')
print(f"   Output type: {type(output2)}")
print(f"   Lines: {len(output2.split(chr(10)))}")

# Command 3 with delay (for slow commands)
print("\n   Command: show running-config")
output3 = connection.send_command('show running-config', delay_factor=2)
print(f"   Output length: {len(output3)} characters")

print("\n4️⃣  Disconnecting...")
connection.disconnect()

print("\n✅ NETMIKO Summary:")
print("   - Simple: Just send commands, get text back")
print("   - You must parse the text yourself (regex, string splitting)")
print("   - Good for: Basic automation, simple scripts")
print("   - Returns: Plain text strings")


print("\n" + "="*70)
print("METHOD 2: pyATS (Advanced with Auto-Parsing)")
print("="*70)

# ============================================================
# pyATS APPROACH (What ReACT script uses)
# ============================================================

from pyats.topology import loader

print("\n1️⃣  Loading testbed configuration...")
# Note: testbed.yaml contains connection details
testbed = loader.load('ReACT_AI_Agent_for_Cisco_IOS_XE/react_ai_agent_cisco_ios_xe/testbed.yaml')

print("2️⃣  Selecting device...")
device = testbed.devices['Cat8000V']
print(f"   Device: {device.name}")
print(f"   OS: {device.os}")
print(f"   Platform: {device.platform}")

print("\n3️⃣  Connecting...")
device.connect()
prompt = device.execute('show clock')  # Quick test command
print(f"   ✅ Connected! Time: {prompt.strip()}")

print("\n4️⃣  Running commands (gets STRUCTURED JSON)...")

# Command 1 - Parsed automatically
print("\n   Command: show ip interface brief")
parsed_output1 = device.parse('show ip interface brief')
print(f"   Output type: {type(parsed_output1)}")
print(f"   Structure: {list(parsed_output1.keys())}")
print(f"   Sample data: {list(parsed_output1['interface'].keys())[:3]}")

# Command 2 - Parsed automatically
print("\n   Command: show ip route summary")
parsed_output2 = device.parse('show ip route summary')
print(f"   Output type: {type(parsed_output2)}")
print(f"   VRFs: {list(parsed_output2.keys())}")

# Command 3 - Raw execution (like netmiko)
print("\n   Command: show clock (raw)")
raw_output = device.execute('show clock')
print(f"   Output type: {type(raw_output)}")
print(f"   Content: {raw_output.strip()}")

print("\n5️⃣  Disconnecting...")
device.disconnect()

print("\n✅ pyATS Summary:")
print("   - Advanced: Automatically parses output to JSON/dict")
print("   - 3,266 parsers available (Genie)")
print("   - Good for: Complex automation, data analysis, AIOps")
print("   - Returns: Structured dictionaries (easy to use)")


print("\n" + "="*70)
print("SIDE-BY-SIDE COMPARISON")
print("="*70)

comparison = """
╔══════════════════╦═══════════════════════╦═══════════════════════╗
║ Feature          ║ Netmiko               ║ pyATS                 ║
╠══════════════════╬═══════════════════════╬═══════════════════════╣
║ Output Format    ║ Raw text string       ║ Structured JSON       ║
║ Parsing Required ║ YES (you do it)       ║ NO (automatic)        ║
║ Learning Curve   ║ Easy                  ║ Moderate              ║
║ Best For         ║ Simple scripts        ║ AIOps, ML, analytics  ║
║ Multi-vendor     ║ Manual adaptation     ║ Built-in support      ║
║ Speed            ║ Fast                  ║ Slower (parsing)      ║
║ Data Analysis    ║ Hard (text parsing)   ║ Easy (JSON/dict)      ║
╚══════════════════╩═══════════════════════╩═══════════════════════╝
"""
print(comparison)

print("\n" + "="*70)
print("WHEN TO USE WHICH?")
print("="*70)

print("""
🔹 Use NETMIKO when:
   - Simple data collection
   - One-off scripts
   - Text-based searching (grep-like)
   - Speed is critical
   - You control the parsing

🔹 Use pyATS when:
   - Building AIOps systems (like yours!)
   - Need structured data for ML/analysis
   - Multi-vendor environments
   - Automated baseline comparisons
   - Complex state tracking

💡 Pro Tip: You can use BOTH!
   - Use netmiko for speed
   - Use pyATS parsers on the output
   - Best of both worlds
""")

print("="*70)
print("DONE!")
print("="*70)

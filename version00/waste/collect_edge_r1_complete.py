"""
EDGE-R1 Data Collection Script
Collects Phil's 7 layers of state from a Cisco device using Netmiko
"""

import json
from datetime import datetime
from netmiko import ConnectHandler

# ============================================================
# DEVICE CONNECTION CONFIGURATION
# ============================================================

# Cat8000V DevNet Sandbox (use this for testing)
cat8000_device = {
    'device_type': 'cisco_ios',  # Changed from telnet to SSH
    'host': 'devnetsandboxiosxe.cisco.com',
    'port': 22,
    'username': 'admin',
    'password': 'C1sco12345',
    'secret': 'C1sco12345',  # Enable password (if needed)
    'timeout': 60,
    'session_log': 'session_log.txt',  # Save all commands to file
    'verbose': True  # Show what's happening
}

# Your local Packet Tracer device (if you set up telnet)
local_device = {
    'device_type': 'cisco_ios_telnet',
    'host': '127.0.0.1',
    'port': 5000,
    'timeout': 60,
    'session_log': 'session_log.txt',
    'verbose': True
}

# ============================================================
# COMMANDS TO COLLECT (Phil's 7 Layers)
# ============================================================

COMMANDS = {
    # Layer 1: Topology & Adjacency
    'topology': [
        'show cdp neighbors detail',
        'show lldp neighbors detail',
        'show interfaces',
        'show interfaces status',
        'show interfaces counters errors',
    ],

    # Layer 3: Routing
    'routing': [
        'show ip interface brief',
        'show ip route',
        'show ip route summary',
        'show ip ospf neighbor',
        'show ip bgp summary',
        'show ip protocols',
    ],

    # Layer 4: HSRP/VRRP
    'redundancy': [
        'show standby',
        'show standby brief',
    ],

    # Layer 5: Control Plane Health
    'control_plane': [
        'show processes cpu',
        'show processes memory sorted',
        'show memory statistics',
    ],

    # Layer 6: Support Services
    'services': [
        'show ntp status',
        'show ntp associations',
        'show logging',
    ],

    # Layer 7: User Experience
    'user_experience': [
        'show ip sla statistics',
        'show ip sla summary',
    ],

    # Configuration & Logs
    'config': [
        'show running-config',
        'show version',
    ]
}

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def connect_to_device(device_config):
    """
    Connect to Cisco device and return connection object
    Shows MODE before connecting
    """
    print(f"\n{'='*60}")
    print(f"🔌 CONNECTING TO DEVICE")
    print(f"{'='*60}")
    print(f"Host: {device_config['host']}:{device_config['port']}")
    print(f"Type: {device_config['device_type']}")
    print(f"User: {device_config.get('username', 'N/A')}")

    try:
        connection = ConnectHandler(**device_config)
        print(f"✅ Connected successfully!")

        # Show current prompt (MODE indicator)
        prompt = connection.find_prompt()
        print(f"📍 Current prompt: {prompt}")

        # Determine mode
        if '#' in prompt:
            mode = "PRIVILEGED EXEC MODE (enable mode)"
        elif '>' in prompt:
            mode = "USER EXEC MODE (need to enter 'enable')"
        elif '(config)' in prompt:
            mode = "GLOBAL CONFIG MODE"
        else:
            mode = "UNKNOWN MODE"

        print(f"🎯 Current mode: {mode}")

        # Enter enable mode if needed
        if '>' in prompt:
            print("⬆️  Entering enable mode...")
            connection.enable()
            new_prompt = connection.find_prompt()
            print(f"📍 New prompt: {new_prompt}")

        return connection

    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return None

def run_command_with_feedback(connection, command):
    """
    Run a single command with visual feedback
    """
    print(f"\n{'─'*60}")
    print(f"▶️  Running: {command}")
    print(f"{'─'*60}")

    try:
        # Check current mode before command
        prompt = connection.find_prompt()

        # Show command execution in real-time
        output = connection.send_command(command, delay_factor=2)

        # Show first few lines of output
        lines = output.split('\n')
        preview_lines = min(5, len(lines))
        print(f"📄 Output preview (first {preview_lines} lines):")
        for line in lines[:preview_lines]:
            print(f"   {line}")

        if len(lines) > preview_lines:
            print(f"   ... ({len(lines) - preview_lines} more lines)")

        print(f"✅ Command completed ({len(output)} chars)")

        return output

    except Exception as e:
        print(f"❌ Command failed: {e}")
        return None

def collect_all_state(connection):
    """
    Collect all state data organized by Phil's 7 layers
    """
    print(f"\n{'='*60}")
    print(f"📊 COLLECTING DEVICE STATE")
    print(f"{'='*60}")

    state_data = {
        'timestamp': datetime.now().isoformat(),
        'device': connection.find_prompt().strip('#>'),
        'layers': {}
    }

    # Collect each layer
    for layer_name, commands in COMMANDS.items():
        print(f"\n🔍 Layer: {layer_name.upper()}")
        state_data['layers'][layer_name] = {}

        for command in commands:
            output = run_command_with_feedback(connection, command)

            if output:
                # Store raw output
                state_data['layers'][layer_name][command] = {
                    'output': output,
                    'lines': len(output.split('\n')),
                    'chars': len(output)
                }

    return state_data

def save_to_json(data, filename):
    """
    Save collected data to JSON file
    """
    print(f"\n{'='*60}")
    print(f"💾 SAVING DATA")
    print(f"{'='*60}")

    try:
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)

        print(f"✅ Saved to: {filename}")
        print(f"📦 File size: {len(json.dumps(data))} bytes")

        # Show summary
        print(f"\n📊 Collection Summary:")
        for layer, commands in data['layers'].items():
            print(f"   {layer}: {len(commands)} commands collected")

        return True

    except Exception as e:
        print(f"❌ Save failed: {e}")
        return False

def show_session_log():
    """
    Show what was logged to session file
    """
    print(f"\n{'='*60}")
    print(f"📝 SESSION LOG")
    print(f"{'='*60}")
    print("All commands and outputs have been logged to: session_log.txt")
    print("You can review the full terminal session there!")

# ============================================================
# MAIN EXECUTION
# ============================================================

def main():
    """
    Main collection workflow
    """
    print(f"\n{'#'*60}")
    print(f"#  CISCO DEVICE STATE COLLECTOR")
    print(f"#  Phil's 7-Layer AIOps Data Collection")
    print(f"{'#'*60}")

    # Choose device (Cat8000V sandbox for testing)
    device_config = cat8000_device  # Change to local_device for Packet Tracer

    # Connect
    connection = connect_to_device(device_config)
    if not connection:
        print("❌ Exiting due to connection failure")
        return

    try:
        # Collect all state
        state_data = collect_all_state(connection)

        # Save to JSON
        filename = f"edge_r1_state_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        save_to_json(state_data, filename)

        # Show session log info
        show_session_log()

    finally:
        # Always disconnect
        print(f"\n{'='*60}")
        print(f"🔌 DISCONNECTING")
        print(f"{'='*60}")
        connection.disconnect()
        print("✅ Disconnected")

    print(f"\n{'#'*60}")
    print(f"#  COLLECTION COMPLETE!")
    print(f"{'#'*60}\n")

# ============================================================
# RUN SCRIPT
# ============================================================

if __name__ == "__main__":
    main()

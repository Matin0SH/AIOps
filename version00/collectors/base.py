"""
Base Device Collector
Clean, minimal base class for network device interaction
"""
from abc import ABC, abstractmethod
from netmiko import ConnectHandler
import json
import re


class BaseDeviceCollector(ABC):
    """Base class for network device interaction with prompt detection and config support"""

    def __init__(self, device_id, host, port, credentials=None):
        self.device_id = device_id
        self.host = host
        self.port = port
        self.credentials = credentials or {}
        self.connection = None
        self.current_prompt = None
        self._is_connected = False

    @property
    @abstractmethod
    def device_type(self):
        """Netmiko device type (e.g., 'cisco_ios', 'cisco_nxos')"""
        pass

    @property
    def connection_params(self):
        """Netmiko connection parameters"""
        return {
            "device_type": self.device_type,
            "host": self.host,
            "port": self.port,
            "username": self.credentials.get("username", ""),
            "password": self.credentials.get("password", ""),
            "secret": self.credentials.get("enable_secret", ""),
            "global_delay_factor": self.credentials.get("delay_factor", 1),
            "timeout": self.credentials.get("timeout", 60),
            "fast_cli": False,  # Disable for cleaner output
        }

    # ============================================================================
    # Connection Management
    # ============================================================================

    def connect(self):
        """Establish connection to device and return result dict"""
        if self._is_connected:
            return {
                "action": "connect",
                "status": "already_connected",
                "device": self.device_id
            }

        self.connection = ConnectHandler(**self.connection_params)
        self._is_connected = True

        if self.credentials.get("enable_secret"):
            self.connection.enable()

        # Get prompt and cache it
        self.current_prompt = self.connection.find_prompt()

        return {
            "action": "connect",
            "status": "connected",
            "device": self.device_id,
            "prompt": self.current_prompt,
        }

    def disconnect(self):
        """Close connection to device and return result dict"""
        if not self._is_connected:
            return {
                "action": "disconnect",
                "status": "not_connected",
                "device": self.device_id
            }

        # Check if in config mode and exit if needed
        if self.connection:
            prompt = self.connection.find_prompt()
            if 'config' in prompt.lower():
                self.connection.exit_config_mode()

        self.connection.disconnect()
        self._is_connected = False

        return {
            "action": "disconnect",
            "status": "disconnected",
            "device": self.device_id
        }

    def is_connected(self):
        """Check if currently connected - returns bool for simple checks"""
        return self._is_connected and self.connection is not None



    # ============================================================================
    # Command Execution
    # ============================================================================

    def send_show_command(self, command):
        """
        Execute a show command (read-only, safe)

        Netmiko's send_command() works in privileged exec mode.
        Does NOT require config mode.

        Args:
            command: The show command to execute

        Returns:
            Raw command output as string
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to device")

        try:
            output = self.connection.send_command(
                command,
                read_timeout=self.credentials.get("read_timeout", 60)
            )
            return output
        except Exception as e:
            raise Exception(f"Show command failed: {str(e)}")

    def send_config_set(self, commands):
        """
        Execute configuration commands

        Netmiko's send_config_set() automatically:
        - Enters config mode
        - Executes all commands
        - Exits config mode

        This is the ONLY method you need for config changes.

        Args:
            commands: Single command (string) or list of commands

        Returns:
            Combined output from all commands
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to device")

        # Accept both single command and list
        if isinstance(commands, str):
            commands = [commands]

        try:
            output = self.connection.send_config_set(
                commands,
                read_timeout=self.credentials.get("read_timeout", 60)
            )

            # Update cached prompt
            self.current_prompt = self.connection.find_prompt()

            return output
        except Exception as e:
            raise Exception(f"Config command failed: {str(e)}")

    # ============================================================================
    # Network Discovery (Common for Routers & Switches)
    # ============================================================================

    def get_cdp_neighbors(self):
        """
        Get CDP neighbors with full details

        Works on both routers and switches - output format is identical.
        Uses regex for reliable parsing.

        Returns:
            list[dict]: List of CDP neighbors with connection details
            [
                {
                    'neighbor_device': 'CORE-SW1',
                    'neighbor_ip': '10.10.10.10',
                    'platform': 'Cisco',
                    'capabilities': 'Router Switch IGMP',
                    'local_interface': 'GigabitEthernet0/0',
                    'neighbor_interface': 'GigabitEthernet0/1'
                },
                ...
            ]
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to device")

        try:
            # Get raw CDP output
            raw_output = self.send_show_command("show cdp neighbors detail")

            # Split by "-------------------------" separators or "Device ID:" to get individual entries
            entries = re.split(r'-{20,}|(?=Device ID:)', raw_output)

            neighbors = []
            for entry in entries:
                if 'Device ID:' not in entry:
                    continue

                neighbor = {}

                # Extract Device ID
                device_match = re.search(r'Device ID:\s*(\S+)', entry)
                if device_match:
                    neighbor['neighbor_device'] = device_match.group(1)

                # Extract IP address
                ip_match = re.search(r'IP address:\s*(\d+\.\d+\.\d+\.\d+)', entry)
                if ip_match:
                    neighbor['neighbor_ip'] = ip_match.group(1)

                # Extract Platform and Capabilities
                platform_match = re.search(r'Platform:\s*([^,]+),\s*Capabilities:\s*(.+)', entry)
                if platform_match:
                    neighbor['platform'] = platform_match.group(1).strip()
                    neighbor['capabilities'] = platform_match.group(2).strip()

                # Extract Interface and Port ID (local and neighbor interfaces)
                interface_match = re.search(r'Interface:\s*(\S+),\s*Port ID \(outgoing port\):\s*(\S+)', entry)
                if interface_match:
                    neighbor['local_interface'] = interface_match.group(1)
                    neighbor['neighbor_interface'] = interface_match.group(2)

                # Only add if we got the essential fields
                if 'neighbor_device' in neighbor and 'local_interface' in neighbor and 'neighbor_interface' in neighbor:
                    neighbors.append(neighbor)

            return neighbors

        except Exception as e:
            raise Exception(f"Failed to get CDP neighbors: {str(e)}")

    def get_ospf_neighbors(self):
        """
        Get OSPF neighbor adjacencies

        Works on both routers and L3 switches - output format is identical.
        Uses regex parsing to handle all OSPF neighbor states.

        Returns:
            list[dict]: List of OSPF neighbors
            [
                {
                    'neighbor_id': '1.1.1.1',
                    'priority': '1',
                    'state': 'FULL/DR',
                    'dead_time': '00:00:33',
                    'address': '10.10.10.1',
                    'interface': 'Vlan10'
                },
                ...
            ]
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to device")

        try:
            import re

            # Get raw OSPF neighbor output
            raw_output = self.send_show_command("show ip ospf neighbor")

            # Only parse the table section (tolerates syslog/prompt noise before/after)
            lines = raw_output.splitlines()
            header_index = None
            for idx, line in enumerate(lines):
                if "Neighbor ID" in line and "State" in line:
                    header_index = idx
                    break
            if header_index is None:
                return []

            # Extract data lines (no separator line in OSPF output)
            data_lines = []
            for line in lines[header_index + 1:]:
                stripped = line.strip()
                if not stripped:
                    continue
                # Stop at prompt
                if stripped.endswith("#"):
                    break
                # Skip syslog messages
                if stripped.startswith(("%", "*", "^", "--More--")):
                    continue
                data_lines.append(line)

            # Regex pattern: neighbor_id, priority, state, dead_time, address, interface
            ospf_re = re.compile(
                r"^(?P<neighbor_id>\d+\.\d+\.\d+\.\d+)\s+"
                r"(?P<priority>\d+)\s+"
                r"(?P<state>\S+)\s+"
                r"(?P<dead_time>\S+)\s+"
                r"(?P<address>\d+\.\d+\.\d+\.\d+)\s+"
                r"(?P<interface>\S+)\s*$"
            )

            ospf_neighbors = []
            for line in data_lines:
                match = ospf_re.match(line)
                if not match:
                    continue
                neighbor_dict = match.groupdict()
                ospf_neighbors.append(neighbor_dict)

            return ospf_neighbors

        except Exception as e:
            raise Exception(f"Failed to get OSPF neighbors: {str(e)}")

    def get_interface_brief(self):
        """
        Get concise interface status (IP addresses and up/down).

        Returns:
            list[dict]: [
                {
                    'interface': 'GigabitEthernet0/1',
                    'ip_address': '10.10.10.3',
                    'ok': 'YES',
                    'method': 'NVRAM',
                    'status': 'up',
                    'protocol': 'up'
                },
                ...
            ]
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to device")

        raw_output = self.send_show_command("show ip interface brief")

        # Only parse the table section (tolerates syslog/prompt noise before/after).
        lines = raw_output.splitlines()
        header_index = None
        for idx, line in enumerate(lines):
            if line.strip().startswith("Interface") and "IP-Address" in line:
                header_index = idx
                break
        if header_index is None:
            return []

        data_lines = []
        for line in lines[header_index + 1:]:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.endswith("#"):
                break
            if stripped.startswith(("%", "*", "^", "--More--")):
                continue
            data_lines.append(line)

        row_re = re.compile(
            r"^(?P<interface>\S+)\s+"
            r"(?P<ip_address>\S+)\s+"
            r"(?P<ok>\S+)\s+"
            r"(?P<method>\S+)\s+"
            r"(?P<status>.+?)\s+"
            r"(?P<protocol>\S+)\s*$"
        )

        interfaces = []
        for line in data_lines:
            match = row_re.match(line)
            if not match:
                continue
            interfaces.append(match.groupdict())

        return interfaces


    # ============================================================================
    # Safety Features
    # ============================================================================

    def save_config(self):
        """
        Save running config to startup config

        Uses Netmiko's built-in save_config() which handles everything automatically.

        Returns:
            Result dict with status
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to device")

        try:
            output = self.connection.save_config()
            return {
                "action": "save_config",
                "status": "success",
                "device": self.device_id,
                "output": output
            }
        except Exception as e:
            return {
                "action": "save_config",
                "status": "failed",
                "device": self.device_id,
                "error": str(e)
            }

    # ============================================================================
    # Utility Methods
    # ============================================================================

    def __enter__(self):
        """Context manager support - auto connect"""
        self.connect()
        return self

    def __exit__(self, _exc_type, _exc_val, _exc_tb):
        """Context manager support - auto disconnect"""
        self.disconnect()
        return False  # Don't suppress exceptions

    def __repr__(self):
        """String representation"""
        status = "connected" if self._is_connected else "disconnected"
        return f"<{self.__class__.__name__} {self.device_id} ({status})>"

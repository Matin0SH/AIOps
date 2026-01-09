"""
Router, Switch Collector
Cisco IOS Router, Switch collector with observability and configuration tools
"""
from pathlib import Path
from tools.base import BaseDeviceCollector
import re


_REGEX_CACHE = {}


def _load_regex_pattern(section_name, pattern_name=None):
    """Load a regex pattern from regex.md by section and optional pattern name."""
    cache_key = (section_name, pattern_name)
    if cache_key in _REGEX_CACHE:
        return _REGEX_CACHE[cache_key]

    regex_path = Path(__file__).parent / "regex.md"
    try:
        content = regex_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None

    header = f"## {section_name}"
    if header not in content:
        return None

    section_text = content.split(header, 1)[1]
    if pattern_name:
        fenced_re = rf"```regex\s+{re.escape(pattern_name)}\s*(.+?)\s*```"
    else:
        fenced_re = r"```regex\s*(.+?)\s*```"

    match = re.search(fenced_re, section_text, re.DOTALL)
    if not match:
        return None

    pattern = match.group(1).strip()
    compiled = re.compile(pattern)
    _REGEX_CACHE[cache_key] = compiled
    return compiled


class Collector(BaseDeviceCollector):
    """Collector for Cisco IOS routers and switches with Layer 1-7 observability"""

    @property
    def device_type(self):
        """
        Return the Netmiko device type.
        Auto-detects telnet vs SSH based on port number.
        """
        # Check if telnet port is being used (GNS3 uses 5000-5020)
        if self.port == 23 or (5000 <= self.port <= 5020):
            return "cisco_ios_telnet"
        return "cisco_ios"
    



    def get_interface_brief(self, clean: bool = True):
        """
        Get concise interface status (IP addresses and up/down).

        Returns:
            list[dict] | dict: When clean=True, returns a list of parsed rows:
            [
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
            When clean=False, returns:
                {"lines": ["line1", "line2", ...]}
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to device")

        raw_output = self.send_show_command("show ip interface brief")
        if not clean:
            return {"lines": raw_output.splitlines()}

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

        row_re = _load_regex_pattern("get_interface_brief")
        if row_re is None:
            raise ValueError("Regex pattern 'get_interface_brief' not found in regex.md")

        interfaces = []
        for line in data_lines:
            match = row_re.match(line)
            if not match:
                continue
            interfaces.append(match.groupdict())

        return interfaces





    def get_cdp_neighbors(self, clean: bool = True):
        """
        Get CDP neighbors with full details

        Works on both routers and switches - output format is identical.
        Uses regex for reliable parsing.

        Returns:
            list[dict] | dict: List of CDP neighbors with connection details when clean=True.
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
            if not clean:
                return {"lines": raw_output.splitlines()}

            # Split by "-------------------------" separators or "Device ID:" to get individual entries
            split_re = _load_regex_pattern("get_cdp_neighbors", "split")
            if split_re is None:
                raise ValueError("Regex pattern 'get_cdp_neighbors split' not found in regex.md")

            entries = split_re.split(raw_output)

            neighbors = []
            for entry in entries:
                if 'Device ID:' not in entry:
                    continue

                neighbor = {}

                # Extract Device ID
                device_re = _load_regex_pattern("get_cdp_neighbors", "device")
                if device_re is None:
                    raise ValueError("Regex pattern 'get_cdp_neighbors device' not found in regex.md")

                device_match = device_re.search(entry)
                if device_match:
                    neighbor['neighbor_device'] = device_match.group(1)

                # Extract IP address
                ip_re = _load_regex_pattern("get_cdp_neighbors", "ip")
                if ip_re is None:
                    raise ValueError("Regex pattern 'get_cdp_neighbors ip' not found in regex.md")

                ip_match = ip_re.search(entry)
                if ip_match:
                    neighbor['neighbor_ip'] = ip_match.group(1)

                # Extract Platform and Capabilities
                platform_re = _load_regex_pattern("get_cdp_neighbors", "platform")
                if platform_re is None:
                    raise ValueError("Regex pattern 'get_cdp_neighbors platform' not found in regex.md")

                platform_match = platform_re.search(entry)
                if platform_match:
                    neighbor['platform'] = platform_match.group(1).strip()
                    neighbor['capabilities'] = platform_match.group(2).strip()

                # Extract Interface and Port ID (local and neighbor interfaces)
                interface_re = _load_regex_pattern("get_cdp_neighbors", "interface")
                if interface_re is None:
                    raise ValueError("Regex pattern 'get_cdp_neighbors interface' not found in regex.md")

                interface_match = interface_re.search(entry)
                if interface_match:
                    neighbor['local_interface'] = interface_match.group(1)
                    neighbor['neighbor_interface'] = interface_match.group(2)

                    # Only add if we got the essential fields
                    if 'neighbor_device' in neighbor and 'local_interface' in neighbor and 'neighbor_interface' in neighbor:
                        neighbors.append(neighbor)

            return neighbors

        except Exception as e:
            raise Exception(f"Failed to get CDP neighbors: {str(e)}")








    def get_ospf_neighbors(self, clean: bool = True):
        """
        Get OSPF neighbor adjacencies

        Works on both routers and L3 switches - output format is identical.
        Uses regex parsing to handle all OSPF neighbor states.

        Returns:
            list[dict] | dict: List of OSPF neighbors when clean=True.
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
            # Get raw OSPF neighbor output
            raw_output = self.send_show_command("show ip ospf neighbor")
            if not clean:
                return {"lines": raw_output.splitlines()}

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
            ospf_re = _load_regex_pattern("get_ospf_neighbors")
            if ospf_re is None:
                raise ValueError("Regex pattern 'get_ospf_neighbors' not found in regex.md")

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






    def get_vlan_brief(self, clean: bool = True):
        """
        Get VLAN information (Layer 2 switches)

        Parses 'show vlan brief' output using regex.
        Handles VLANs with or without ports assigned.

        Returns:
            list[dict] | dict: List of VLANs with details when clean=True.
            [
                {
                    'vlan_id': '1',
                    'name': 'default',
                    'status': 'active',
                    'ports': 'Gi0/0, Gi1/0, Gi1/1, Gi1/2, Gi1/3'
                },
                {
                    'vlan_id': '10',
                    'name': 'MANAGEMENT',
                    'status': 'active',
                    'ports': ''
                },
                ...
            ]
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to device")

        try:
            # Get raw VLAN output
            raw_output = self.send_show_command("show vlan brief")
            if not clean:
                return {"lines": raw_output.splitlines()}

            # Only parse the table section (tolerates syslog/prompt noise before/after)
            lines = raw_output.splitlines()
            header_index = None
            for idx, line in enumerate(lines):
                if line.strip().startswith("VLAN") and "Name" in line:
                    header_index = idx
                    break
            if header_index is None:
                return []

            # Find separator line (----)
            separator_index = None
            for idx in range(header_index + 1, len(lines)):
                if lines[idx].strip().startswith("----"):
                    separator_index = idx
                    break
            if separator_index is None:
                return []

            # Extract data lines (skip header and separator)
            data_lines = []
            for line in lines[separator_index + 1:]:
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

            # Regex pattern: vlan_id (digits), name (non-whitespace), status (non-whitespace), ports (rest of line, optional)
            vlan_re = _load_regex_pattern("get_vlan_brief")
            if vlan_re is None:
                raise ValueError("Regex pattern 'get_vlan_brief' not found in regex.md")

            vlans = []
            for line in data_lines:
                match = vlan_re.match(line)
                if not match:
                    continue
                vlan_dict = match.groupdict()
                # Clean up ports field - strip whitespace
                vlan_dict['ports'] = vlan_dict['ports'].strip()
                vlans.append(vlan_dict)

            return vlans

        except Exception as e:
            raise Exception(f"Failed to get VLAN brief: {str(e)}")





    def get_trunk_interfaces(self, clean: bool = True):
        """
        Get trunk interface status and VLAN information

        Parses 'show interfaces trunk' output using regex.
        Captures trunk configuration, allowed VLANs, active VLANs, and forwarding state.

        Returns:
            list[dict] | dict: List of trunk interfaces with full details when clean=True.
            [
                {
                    'port': 'Gi0/1',
                    'mode': 'on',
                    'encapsulation': '802.1q',
                    'status': 'trunking',
                    'native_vlan': '1',
                    'vlans_allowed': '10',
                    'vlans_active': '10',
                    'vlans_forwarding': '10'
                },
                ...
            ]
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to device")

        try:
            # Get raw trunk output
            raw_output = self.send_show_command("show interfaces trunk")
            if not clean:
                return {"lines": raw_output.splitlines()}
            lines = raw_output.splitlines()

            # Dictionary to store trunk data by port
            trunk_data = {}

            # Section 1: Port Mode Encapsulation Status Native vlan
            section1_re = _load_regex_pattern("get_trunk_interfaces", "config")
            if section1_re is None:
                raise ValueError("Regex pattern 'get_trunk_interfaces config' not found in regex.md")

            # Section 2: Port Vlans allowed on trunk
            section2_re = _load_regex_pattern("get_trunk_interfaces", "vlans")
            if section2_re is None:
                raise ValueError("Regex pattern 'get_trunk_interfaces vlans' not found in regex.md")

            # Track which section we're in
            current_section = None
            for line in lines:
                stripped = line.strip()

                # Identify sections
                if "Mode" in stripped and "Encapsulation" in stripped:
                    current_section = "config"
                    continue
                elif "Vlans allowed on trunk" in stripped:
                    current_section = "allowed"
                    continue
                elif "Vlans allowed and active" in stripped:
                    current_section = "active"
                    continue
                elif "spanning tree forwarding state" in stripped:
                    current_section = "forwarding"
                    continue

                # Skip empty lines, headers, prompts
                if not stripped or stripped.startswith("-") or stripped.endswith("#"):
                    continue
                if stripped.startswith(("%", "*", "^", "Port")):
                    continue

                # Parse based on current section
                if current_section == "config":
                    match = section1_re.match(line)
                    if match:
                        port_data = match.groupdict()
                        port = port_data['port']
                        trunk_data[port] = port_data
                        # Initialize other fields
                        trunk_data[port]['vlans_allowed'] = ''
                        trunk_data[port]['vlans_active'] = ''
                        trunk_data[port]['vlans_forwarding'] = ''

                elif current_section in ("allowed", "active", "forwarding"):
                    match = section2_re.match(line)
                    if match:
                        port = match.group('port')
                        vlans = match.group('vlans').strip()

                        # Create port entry if it doesn't exist
                        if port not in trunk_data:
                            trunk_data[port] = {
                                'port': port,
                                'mode': '',
                                'encapsulation': '',
                                'status': '',
                                'native_vlan': '',
                                'vlans_allowed': '',
                                'vlans_active': '',
                                'vlans_forwarding': ''
                            }

                        # Add VLANs to appropriate field
                        if current_section == "allowed":
                            trunk_data[port]['vlans_allowed'] = vlans
                        elif current_section == "active":
                            trunk_data[port]['vlans_active'] = vlans
                        elif current_section == "forwarding":
                            trunk_data[port]['vlans_forwarding'] = vlans

            # Convert dictionary to list
            trunk_list = list(trunk_data.values())
            return trunk_list

        except Exception as e:
            raise Exception(f"Failed to get trunk interfaces: {str(e)}")

    def get_mac_address_table(self, clean: bool = True):
        """
        Get MAC address table

        Parses 'show mac address-table' output using regex.
        Captures all MAC addresses learned on all VLANs and ports.

        Returns:
            list[dict] | dict: List of MAC address entries when clean=True.
            [
                {
                    'vlan': '10',
                    'mac_address': '0cb8.63c3.0002',
                    'type': 'DYNAMIC',
                    'port': 'Gi0/1'
                },
                {
                    'vlan': '10',
                    'mac_address': '0cb8.63c3.800a',
                    'type': 'DYNAMIC',
                    'port': 'Gi0/1'
                },
                ...
            ]
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to device")

        try:
            # Get raw MAC address table output
            raw_output = self.send_show_command("show mac address-table")
            if not clean:
                return {"lines": raw_output.splitlines()}

            # Only parse the table section (tolerates syslog/prompt noise before/after)
            lines = raw_output.splitlines()
            header_index = None
            for idx, line in enumerate(lines):
                if "Vlan" in line and "Mac Address" in line and "Type" in line:
                    header_index = idx
                    break
            if header_index is None:
                return []

            # Find separator line (----)
            separator_index = None
            for idx in range(header_index + 1, len(lines)):
                if lines[idx].strip().startswith("----"):
                    separator_index = idx
                    break
            if separator_index is None:
                return []

            # Extract data lines (skip header and separator)
            data_lines = []
            for line in lines[separator_index + 1:]:
                stripped = line.strip()
                if not stripped:
                    continue
                # Stop at "Total Mac Addresses" or prompt
                if stripped.startswith("Total") or stripped.endswith("#"):
                    break
                # Skip syslog messages
                if stripped.startswith(("%", "*", "^", "--More--")):
                    continue
                data_lines.append(line)

            # Regex pattern: vlan (digits), mac_address (xxxx.xxxx.xxxx), type (word), port (interface name)
            mac_re = _load_regex_pattern("get_mac_address_table")
            if mac_re is None:
                raise ValueError("Regex pattern 'get_mac_address_table' not found in regex.md")

            mac_entries = []
            for line in data_lines:
                match = mac_re.match(line)
                if not match:
                    continue
                mac_dict = match.groupdict()
                mac_entries.append(mac_dict)

            return mac_entries

        except Exception as e:
            raise Exception(f"Failed to get MAC address table: {str(e)}")

    def get_spanning_tree_summary(self, clean: bool = True):
        """
        Get spanning tree summary

        Parses 'show spanning-tree summary' output using regex.
        Captures STP configuration settings and per-VLAN statistics.

        Returns:
            dict: Spanning tree configuration and statistics when clean=True.
            {
                'config': {
                    'mode': 'rapid-pvst',
                    'root_bridge_for': 'VLAN0001',
                    'extended_system_id': 'enabled',
                    'portfast_default': 'disabled',
                    'portfast_bpdu_guard': 'disabled',
                    'portfast_bpdu_filter': 'disabled',
                    'loopguard': 'disabled',
                    'bridge_assurance': 'enabled',
                    'etherchannel_misconfig_guard': 'enabled',
                    'pathcost_method': 'short',
                    'uplinkfast': 'disabled',
                    'backbonefast': 'disabled'
                },
                'vlan_stats': [
                    {
                        'vlan': 'VLAN0001',
                        'blocking': '0',
                        'listening': '0',
                        'learning': '0',
                        'forwarding': '11',
                        'stp_active': '11'
                    },
                    ...
                ]
            }
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to device")

        try:
            # Get raw STP output
            raw_output = self.send_show_command("show spanning-tree summary")
            if not clean:
                return {"lines": raw_output.splitlines()}
            lines = raw_output.splitlines()

            # Initialize result structure
            result = {
                'config': {},
                'vlan_stats': []
            }

            # Parse configuration section (key-value pairs)
            mode_re = _load_regex_pattern("get_spanning_tree_summary", "mode")
            root_bridge_re = _load_regex_pattern("get_spanning_tree_summary", "root_bridge")
            extended_system_id_re = _load_regex_pattern("get_spanning_tree_summary", "extended_system_id")
            portfast_default_re = _load_regex_pattern("get_spanning_tree_summary", "portfast_default")
            portfast_bpdu_guard_re = _load_regex_pattern("get_spanning_tree_summary", "portfast_bpdu_guard")
            portfast_bpdu_filter_re = _load_regex_pattern("get_spanning_tree_summary", "portfast_bpdu_filter")
            loopguard_re = _load_regex_pattern("get_spanning_tree_summary", "loopguard")
            bridge_assurance_re = _load_regex_pattern("get_spanning_tree_summary", "bridge_assurance")
            etherchannel_misconfig_re = _load_regex_pattern("get_spanning_tree_summary", "etherchannel_misconfig")
            pathcost_re = _load_regex_pattern("get_spanning_tree_summary", "pathcost")
            uplinkfast_re = _load_regex_pattern("get_spanning_tree_summary", "uplinkfast")
            backbonefast_re = _load_regex_pattern("get_spanning_tree_summary", "backbonefast")
            vlan_stats_re = _load_regex_pattern("get_spanning_tree_summary", "vlan_stats")

            if not all([
                mode_re, root_bridge_re, extended_system_id_re, portfast_default_re,
                portfast_bpdu_guard_re, portfast_bpdu_filter_re, loopguard_re,
                bridge_assurance_re, etherchannel_misconfig_re, pathcost_re,
                uplinkfast_re, backbonefast_re, vlan_stats_re
            ]):
                raise ValueError("Regex patterns for 'get_spanning_tree_summary' not found in regex.md")

            # Parse VLAN statistics table
            # Track if we're in the table section
            in_table_section = False

            for line in lines:
                stripped = line.strip()

                # Skip empty lines, prompts, syslog
                if not stripped or stripped.endswith("#"):
                    continue
                if stripped.startswith(("%", "*", "^", "--More--")):
                    continue

                # Parse configuration lines
                match = mode_re.search(line)
                if match:
                    result['config']['mode'] = match.group(1)
                    continue

                match = root_bridge_re.search(line)
                if match:
                    result['config']['root_bridge_for'] = match.group(1).strip()
                    continue

                match = extended_system_id_re.search(line)
                if match:
                    result['config']['extended_system_id'] = match.group(1)
                    continue

                match = portfast_default_re.search(line)
                if match:
                    result['config']['portfast_default'] = match.group(1)
                    continue

                match = portfast_bpdu_guard_re.search(line)
                if match:
                    result['config']['portfast_bpdu_guard'] = match.group(1)
                    continue

                match = portfast_bpdu_filter_re.search(line)
                if match:
                    result['config']['portfast_bpdu_filter'] = match.group(1)
                    continue

                match = loopguard_re.search(line)
                if match:
                    result['config']['loopguard'] = match.group(1)
                    continue

                match = bridge_assurance_re.search(line)
                if match:
                    result['config']['bridge_assurance'] = match.group(1)
                    continue

                match = etherchannel_misconfig_re.search(line)
                if match:
                    result['config']['etherchannel_misconfig_guard'] = match.group(1)
                    continue

                match = pathcost_re.search(line)
                if match:
                    result['config']['pathcost_method'] = match.group(1)
                    continue

                match = uplinkfast_re.search(line)
                if match:
                    result['config']['uplinkfast'] = match.group(1)
                    continue

                match = backbonefast_re.search(line)
                if match:
                    result['config']['backbonefast'] = match.group(1)
                    continue

                # Detect start of table section
                if "Blocking" in line and "Listening" in line and "Learning" in line:
                    in_table_section = True
                    continue

                # Skip separator lines
                if stripped.startswith("----"):
                    continue

                # Skip summary line (e.g., "2 vlans")
                if "vlans" in stripped.lower() and not stripped.startswith("VLAN"):
                    continue

                # Parse VLAN statistics
                if in_table_section:
                    match = vlan_stats_re.match(line)
                    if match:
                        result['vlan_stats'].append(match.groupdict())

            return result

        except Exception as e:
            raise Exception(f"Failed to get spanning tree summary: {str(e)}")




    def get_device_info(self):
        """
        Get device hardware and software information

        Returns:
            str: Raw output from 'show version'
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to device")

        try:
            output = self.send_show_command("show version")
            return output
        except Exception as e:
            raise Exception(f"Failed to get device info: {str(e)}")

    def get_cpu_usage(self):
        """
        Get CPU utilization statistics

        Returns:
            str: Raw output from 'show processes cpu'
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to device")

        try:
            output = self.send_show_command("show processes cpu")
            return output
        except Exception as e:
            raise Exception(f"Failed to get CPU usage: {str(e)}")

    def get_memory_usage(self):
        """
        Get memory utilization statistics

        Returns:
            str: Raw output from 'show memory statistics'
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to device")

        try:
            output = self.send_show_command("show memory statistics")
            return output
        except Exception as e:
            raise Exception(f"Failed to get memory usage: {str(e)}")
"""
Switch Collector
Cisco IOS Switch specific collector with Layer 2/3 observability tools
"""
from collectors.base import BaseDeviceCollector


class SwitchCollector(BaseDeviceCollector):
    """Collector for Cisco IOS switches with Layer 2/3 observability"""

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


    # ============================================================================
    # LAYER 2: Data Link (VLANs, Trunks, MAC Tables)
    # ============================================================================

    def get_vlan_brief(self):
        """
        Get VLAN information (Layer 2 switches)

        Parses 'show vlan brief' output using regex.
        Handles VLANs with or without ports assigned.

        Returns:
            list[dict]: List of VLANs with details
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
            import re

            # Get raw VLAN output
            raw_output = self.send_show_command("show vlan brief")

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
            vlan_re = re.compile(
                r"^(?P<vlan_id>\d+)\s+"
                r"(?P<name>\S+)\s+"
                r"(?P<status>\S+)\s*"
                r"(?P<ports>.*)$"
            )

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

    def get_trunk_interfaces(self):
        """
        Get trunk interface status and VLAN information

        Parses 'show interfaces trunk' output using regex.
        Captures trunk configuration, allowed VLANs, active VLANs, and forwarding state.

        Returns:
            list[dict]: List of trunk interfaces with full details
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
            import re

            # Get raw trunk output
            raw_output = self.send_show_command("show interfaces trunk")
            lines = raw_output.splitlines()

            # Dictionary to store trunk data by port
            trunk_data = {}

            # Section 1: Port Mode Encapsulation Status Native vlan
            section1_re = re.compile(
                r"^(?P<port>\S+)\s+"
                r"(?P<mode>\S+)\s+"
                r"(?P<encapsulation>\S+)\s+"
                r"(?P<status>\S+)\s+"
                r"(?P<native_vlan>\S+)\s*$"
            )

            # Section 2: Port Vlans allowed on trunk
            section2_re = re.compile(
                r"^(?P<port>\S+)\s+"
                r"(?P<vlans>.*)$"
            )

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

    def get_mac_address_table(self):
        """
        Get MAC address table

        Parses 'show mac address-table' output using regex.
        Captures all MAC addresses learned on all VLANs and ports.

        Returns:
            list[dict]: List of MAC address entries
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
            import re

            # Get raw MAC address table output
            raw_output = self.send_show_command("show mac address-table")

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
            mac_re = re.compile(
                r"^\s*(?P<vlan>\d+)\s+"
                r"(?P<mac_address>[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4})\s+"
                r"(?P<type>\S+)\s+"
                r"(?P<port>\S+)\s*$"
            )

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

    def get_spanning_tree_summary(self):
        """
        Get spanning tree summary

        Parses 'show spanning-tree summary' output using regex.
        Captures STP configuration settings and per-VLAN statistics.

        Returns:
            dict: Spanning tree configuration and statistics
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
            import re

            # Get raw STP output
            raw_output = self.send_show_command("show spanning-tree summary")
            lines = raw_output.splitlines()

            # Initialize result structure
            result = {
                'config': {},
                'vlan_stats': []
            }

            # Parse configuration section (key-value pairs)
            mode_re = re.compile(r"Switch is in (\S+) mode")
            root_bridge_re = re.compile(r"Root bridge for:\s+(.+)")
            extended_system_id_re = re.compile(r"Extended system ID\s+is (\S+)")
            portfast_default_re = re.compile(r"Portfast Default\s+is (\S+)")
            portfast_bpdu_guard_re = re.compile(r"Portfast Edge BPDU Guard Default\s+is (\S+)")
            portfast_bpdu_filter_re = re.compile(r"Portfast Edge BPDU Filter Default\s+is (\S+)")
            loopguard_re = re.compile(r"Loopguard Default\s+is (\S+)")
            bridge_assurance_re = re.compile(r"Bridge Assurance\s+is (\S+)")
            etherchannel_misconfig_re = re.compile(r"EtherChannel misconfig guard\s+is (\S+)")
            pathcost_re = re.compile(r"Configured Pathcost method used is (\S+)")
            uplinkfast_re = re.compile(r"UplinkFast\s+is (\S+)")
            backbonefast_re = re.compile(r"BackboneFast\s+is (\S+)")

            # Parse VLAN statistics table
            vlan_stats_re = re.compile(
                r"^(?P<vlan>VLAN\d+)\s+"
                r"(?P<blocking>\d+)\s+"
                r"(?P<listening>\d+)\s+"
                r"(?P<learning>\d+)\s+"
                r"(?P<forwarding>\d+)\s+"
                r"(?P<stp_active>\d+)\s*$"
            )

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

    # ============================================================================
    # LAYER 3: Network (IP Routing)
    # ============================================================================

    # NOTE: get_cdp_neighbors(), get_ospf_neighbors(), get_interface_brief(),
    #       get_routing_table() all inherited from BaseDeviceCollector
    #       (work identically on both routers and L3 switches)

    # ============================================================================
    # LAYER 4-5: Control Plane Health & Performance
    # ============================================================================

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

"""
Router Collector
Cisco IOS Router specific collector with observability and configuration tools
"""
from collectors.base import BaseDeviceCollector
import re


class RouterCollector(BaseDeviceCollector):
    """Collector for Cisco IOS routers with Layer 1-7 observability"""

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

    # ============================================================================
    # LAYER 6-7: Support Services & Application
    # ============================================================================

    def get_ntp_status(self):
        """
        Get NTP synchronization status

        Returns:
            str: Raw output from 'show ntp status'
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to device")

        try:
            output = self.send_show_command("show ntp status")
            return output
        except Exception as e:
            raise Exception(f"Failed to get NTP status: {str(e)}")

    def get_ntp_associations(self):
        """
        Get NTP peer associations

        Returns:
            str: Raw output from 'show ntp associations'
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to device")

        try:
            output = self.send_show_command("show ntp associations")
            return output
        except Exception as e:
            raise Exception(f"Failed to get NTP associations: {str(e)}")

    def get_logging_config(self):
        """
        Get logging configuration and buffer

        Returns:
            str: Raw output from 'show running-config | include logging'
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to device")

        try:
            output = self.send_show_command("show running-config | include logging")
            return output
        except Exception as e:
            raise Exception(f"Failed to get logging config: {str(e)}")

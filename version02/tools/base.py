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

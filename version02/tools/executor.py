"""
Dynamic Config Executor for Cisco IOS devices.
Loads all notebook definitions from notebooks.json and applies them dynamically.
No per-notebook methods - one generic apply_notebook() handles all 26 notebooks.

This implementation:
- ConfigExecutor class for direct usage
- @tool decorated functions for LangChain agent integration
- Same structure as scholar.py
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional
import logging

from langchain_core.tools import tool
from tools.base import BaseDeviceCollector


# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Global notebook cache
_NOTEBOOK_CACHE = {}


def _load_all_notebooks() -> Dict[str, Dict]:
    """
    Load all notebook definitions from notebooks.json once.
    Parse and cache by notebook ID for O(1) lookup.
    
    Returns:
        dict: {notebook_id: notebook_definition}
        Example:
        {
            "cfg_set_hostname": {...},
            "cfg_set_domain_name": {...},
            ...all 26 notebooks...
        }
    """
    global _NOTEBOOK_CACHE
    
    if _NOTEBOOK_CACHE:
        return _NOTEBOOK_CACHE
    
    # Load notebooks.json from tools directory
    notebooks_path = Path(__file__).parent.parent / "tools" / "notebooks.json"
    
    try:
        with open(notebooks_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"notebooks.json not found at {notebooks_path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in notebooks.json: {e}")
    
    # Extract notebooks array and build cache dict by ID
    notebooks = data.get("notebooks", [])
    
    for notebook in notebooks:
        notebook_id = notebook.get("id")
        if not notebook_id:
            raise ValueError("Notebook missing 'id' field")
        _NOTEBOOK_CACHE[notebook_id] = notebook
    
    return _NOTEBOOK_CACHE


class ConfigExecutor:
    """
    Dynamic executor for CONFIG-SET notebooks on Cisco IOS devices.
    
    One generic apply_notebook() method handles all notebook types.
    No code duplication - pure function-based approach like collector.py
    """
    
    def __init__(self, device: BaseDeviceCollector):
        """
        Initialize executor and load all notebooks into memory.
        
        Args:
            device_connection: SSH/Telnet connection object (from BaseDeviceExecutor)
        """
        self.device = device
        self.notebooks = _load_all_notebooks()
    
    def apply_notebook(
        self,
        notebook_id: str,
        dry_run: bool = False,
        auto_disconnect: bool = True,
        **params
    ) -> Dict[str, Any]:
        """
        Apply ANY notebook dynamically.
        
        This is the ONLY execution method needed.
        Works for all 26 notebooks - no per-notebook methods required.
        
        Args:
            notebook_id: ID of notebook to apply (e.g., "cfg_set_hostname")
            dry_run: If True, render commands but don't execute (default: False)
            **params: Notebook-specific parameters
                Example for cfg_set_hostname:
                    executor.apply_notebook("cfg_set_hostname", hostname="router-01")
                
                Example for cfg_ospf_network_statement:
                    executor.apply_notebook(
                        "cfg_ospf_network_statement",
                        process_id=1,
                        network="10.0.0.0",
                        wildcard="0.0.0.255",
                        area=0
                    )
        
        Returns:
            dict: ExecutionResult
            {
                "success": bool,
                "notebook_id": str,
                "title": str,
                "description": str,
                "risk": str,
                "commands_sent": list[str],
                "device_output": str,
                "dry_run": bool,
                "validated": bool,
                "changes_summary": str,
                "rollback_available": bool,
                "error": Optional[str]
            }
        """
        result = {
            "success": False,
            "notebook_id": notebook_id,
            "title": None,
            "description": None,
            "risk": None,
            "commands_sent": [],
            "device_output": "",
            "dry_run": dry_run,
            "validated": False,
            "changes_summary": "",
            "rollback_available": False,
            "error": None
        }
        
        connected_here = False
        try:

            # Step 1: Load notebook definition
            notebook = self._get_notebook(notebook_id)
            result["title"] = notebook.get("title")
            result["description"] = notebook.get("description")
            result["risk"] = notebook.get("risk")
            
            # Step 2: Validate parameters against schema
            self._validate_params(params, notebook.get("params_schema", {}))
            
            # Step 3: Render config commands
            commands = self._render_commands(
                notebook.get("config_commands", []),
                params
            )
            result["commands_sent"] = commands
            
            # Step 4: Execute (or dry-run)
            if dry_run:
                result["device_output"] = "[DRY RUN - Commands rendered but not executed]"
                result["success"] = True
                result["validated"] = True
                result["changes_summary"] = f"[DRY RUN] Would execute {len(commands)} commands"
            else:
                if not self.device.is_connected():
                    self.device.connect()
                    connected_here = True

                # Actually send commands to device
                output = self.device.send_config_set(commands)
                result["device_output"] = output
                
                # Step 5: Verify execution
                verified = self._verify_execution(notebook, commands, output, params)
                result["validated"] = verified
                result["success"] = verified
                
                if verified:
                    result["changes_summary"] = f"Applied {notebook_id}: {notebook.get('title')}"
                    result["rollback_available"] = len(notebook.get("rollback_commands", [])) > 0
                else:
                    result["error"] = "Execution verification failed"

        except Exception as e:
            result["success"] = False
            result["error"] = str(e)
        finally:
            if auto_disconnect and not dry_run and connected_here:
                self.device.disconnect()
        
        return result

    def print_schema(self, notebook_id: str) -> None:
        """Print the JSON schema for a notebook without executing anything."""
        notebook = self._get_notebook(notebook_id)
        schema = notebook.get("params_schema", {})
        print(json.dumps(schema, indent=2))
    
    def _get_notebook(self, notebook_id: str) -> Dict:
        """
        Lookup notebook by ID in cache.
        
        Args:
            notebook_id: Notebook identifier
        
        Returns:
            dict: Notebook definition
        
        Raises:
            ValueError: If notebook not found
        """
        if notebook_id not in self.notebooks:
            available = ", ".join(self.notebooks.keys())
            raise ValueError(
                f"Notebook '{notebook_id}' not found. Available: {available}"
            )
        return self.notebooks[notebook_id]
    
    def _validate_params(self, params: Dict[str, Any], schema: Dict) -> None:
        """
        Validate parameters against JSON Schema from notebook.
        
        Uses the same pattern as collector.py regex validation.
        Strict validation before execution - fail fast.
        
        Args:
            params: User-provided parameters
            schema: JSON Schema from notebook
        
        Raises:
            ValueError: If validation fails
        """
        # Check if schema is empty (no params required)
        if not schema or not schema.get("properties"):
            return
        
        # Check required fields
        required = schema.get("required", [])
        for field in required:
            if field not in params:
                raise ValueError(f"Missing required parameter: {field}")
        
        # Validate each parameter
        properties = schema.get("properties", {})
        for param_name, param_value in params.items():
            if param_name not in properties:
                raise ValueError(f"Unknown parameter: {param_name}")
            
            prop_schema = properties[param_name]
            self._validate_param_value(param_name, param_value, prop_schema)
    
    def _validate_param_value(self, name: str, value: Any, schema: Dict) -> None:
        """
        Validate a single parameter against its schema.
        
        Args:
            name: Parameter name (for error messages)
            value: Parameter value
            schema: Parameter schema definition
        
        Raises:
            ValueError: If validation fails
        """
        param_type = schema.get("type")
        
        # Type validation
        if param_type == "string":
            if not isinstance(value, str):
                raise ValueError(f"{name}: must be string, got {type(value).__name__}")
            
            # Length validation
            min_length = schema.get("minLength")
            if min_length and len(value) < min_length:
                raise ValueError(f"{name}: minimum length is {min_length}")
            
            max_length = schema.get("maxLength")
            if max_length and len(value) > max_length:
                raise ValueError(f"{name}: maximum length is {max_length}")
            
            # Regex pattern validation
            pattern = schema.get("pattern")
            if pattern:
                if not re.match(pattern, value):
                    raise ValueError(f"{name}: '{value}' does not match pattern {pattern}")
        
        elif param_type == "integer":
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"{name}: must be integer, got {type(value).__name__}")
            
            # Range validation
            minimum = schema.get("minimum")
            if minimum is not None and value < minimum:
                raise ValueError(f"{name}: minimum value is {minimum}")
            
            maximum = schema.get("maximum")
            if maximum is not None and value > maximum:
                raise ValueError(f"{name}: maximum value is {maximum}")
            
            # Enum validation
            enum_values = schema.get("enum")
            if enum_values and value not in enum_values:
                raise ValueError(f"{name}: must be one of {enum_values}")
    
    def _render_commands(self, commands: List[str], params: Dict) -> List[str]:
        """
        Render config command templates by substituting parameters.
        
        Replace ${variable_name} with actual values.
        Pure string substitution - no LLM, no magic.
        
        Args:
            commands: List of command templates (e.g., "hostname ${hostname}")
            params: Parameter dict (e.g., {"hostname": "router-01"})
        
        Returns:
            list: Rendered commands ready to execute
        """
        rendered = []
        for cmd in commands:
            rendered_cmd = cmd
            for param_name, param_value in params.items():
                placeholder = f"${{{param_name}}}"
                rendered_cmd = rendered_cmd.replace(placeholder, str(param_value))
            rendered.append(rendered_cmd)
        return rendered
    
    def _verify_execution(
        self,
        notebook: Dict,
        commands: List[str],
        device_output: str,
        params: Dict
    ) -> bool:
        """
        Verify that configuration was actually applied to device.
        
        Uses regex parsing like collector.py does for output parsing.
        Post-execution validation - ensure change took effect.
        
        Args:
            notebook: Notebook definition
            commands: Commands that were sent
            device_output: Raw device output from command execution
            params: Parameters used (for rendering verification commands)
        
        Returns:
            bool: True if verification passed, False otherwise
        """
        # For now, simple heuristic: if no error in output, assume success
        # TODO: Add post_execution_validation commands from notebook
        # if notebook has "post_execution_validation" field with verification commands
        
        # Check for common error indicators
        error_indicators = [
            "% Invalid command",
            "% Incomplete command",
            "% Ambiguous command",
            "error",
            "ERROR"
        ]
        
        for indicator in error_indicators:
            if indicator in device_output:
                return False
        
        return True


# ============================================================================
# DEVICE CONNECTION MANAGEMENT (for @tool integration)
# ============================================================================

# Global device connection cache (singleton pattern)
_DEVICE_CONNECTION: Optional[BaseDeviceCollector] = None


def set_device_connection(device: BaseDeviceCollector) -> None:
    """
    Set the global device connection for executor tools.

    This must be called BEFORE using execute_notebook tool.

    Args:
        device: Connected BaseDeviceCollector instance

    Example:
        >>> from tools.base import BaseDeviceCollector
        >>> from tools.executor import set_device_connection
        >>> device = BaseDeviceCollector(host="192.168.1.1", username="admin", password="cisco")
        >>> set_device_connection(device)
        >>> # Now execute_notebook tool can use this connection
    """
    global _DEVICE_CONNECTION
    _DEVICE_CONNECTION = device
    logger.info(f"Device connection set: {device.host if hasattr(device, 'host') else 'Unknown'}")


def get_device_connection() -> BaseDeviceCollector:
    """
    Get the current device connection.

    Returns:
        BaseDeviceCollector instance

    Raises:
        RuntimeError: If connection not set
    """
    if _DEVICE_CONNECTION is None:
        raise RuntimeError(
            "No device connection set. Call set_device_connection() first.\n"
            "Example:\n"
            "  from tools.base import BaseDeviceCollector\n"
            "  from tools.executor import set_device_connection\n"
            "  device = BaseDeviceCollector(...)\n"
            "  set_device_connection(device)"
        )
    return _DEVICE_CONNECTION


# ============================================================================
# TOOL DEFINITION (AGENT-READY)
# ============================================================================

@tool
def execute_notebook(
    notebook_id: str,
    params: Optional[Dict[str, Any]] = None,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Execute a Cisco IOS configuration notebook on the connected device.

    This tool applies configuration changes to network devices using pre-defined
    notebooks from the configuration knowledge base. Each notebook contains
    validated commands and parameter schemas.

    Args:
        notebook_id: Notebook identifier (e.g., "cfg_set_hostname", "cfg_create_vlan")
        params: Notebook parameters as dict (e.g., {"hostname": "router-01"})
        dry_run: If True, validate and render commands without executing (default: False)

    Returns:
        Dict with execution result:
        {
            "success": bool,
            "notebook_id": str,
            "title": str,
            "risk": str,
            "commands_sent": List[str],
            "device_output": str,
            "dry_run": bool,
            "validated": bool,
            "changes_summary": str,
            "error": Optional[str]
        }

    Examples:
        >>> # Set hostname
        >>> execute_notebook("cfg_set_hostname", {"hostname": "router-01"})

        >>> # Create VLAN
        >>> execute_notebook("cfg_create_vlan", {"vlan_id": 10, "vlan_name": "Engineering"})

        >>> # Dry run (validate without executing)
        >>> execute_notebook("cfg_ospf_network_statement", {"process_id": 1, ...}, dry_run=True)

    Raises:
        RuntimeError: If device connection not set
        ValueError: If notebook_id not found or params invalid
    """
    if params is None:
        params = {}

    try:
        # Get device connection
        device = get_device_connection()

        # Create executor instance
        executor = ConfigExecutor(device)

        # Execute notebook
        result = executor.apply_notebook(
            notebook_id=notebook_id,
            dry_run=dry_run,
            auto_disconnect=False,  # Let agent manage connection lifecycle
            **params
        )

        logger.info(
            f"Executed notebook '{notebook_id}' - "
            f"Success: {result['success']}, Dry Run: {dry_run}"
        )

        return result

    except Exception as e:
        logger.error(f"execute_notebook failed: {e}", exc_info=True)
        return {
            "success": False,
            "notebook_id": notebook_id,
            "title": None,
            "risk": None,
            "commands_sent": [],
            "device_output": "",
            "dry_run": dry_run,
            "validated": False,
            "changes_summary": "",
            "error": str(e)
        }


@tool
def get_notebook_info(notebook_id: str) -> Dict[str, Any]:
    """
    Get detailed information about a specific notebook including parameter schema.

    Use this tool to understand what parameters a notebook requires before execution.

    Args:
        notebook_id: Notebook identifier (e.g., "cfg_set_hostname")

    Returns:
        Dict with notebook metadata:
        {
            "id": str,
            "title": str,
            "description": str,
            "risk": str,
            "params_schema": dict,
            "requires_params": bool
        }

    Examples:
        >>> get_notebook_info("cfg_set_hostname")
        {
            "id": "cfg_set_hostname",
            "title": "Set device hostname",
            "risk": "LOW",
            "params_schema": {
                "required": ["hostname"],
                "properties": {"hostname": {"type": "string", ...}}
            },
            "requires_params": True
        }
    """
    try:
        notebooks = _load_all_notebooks()
        if notebook_id not in notebooks:
            available = ", ".join(notebooks.keys())
            raise ValueError(f"Notebook '{notebook_id}' not found. Available: {available}")

        notebook = notebooks[notebook_id]
        return {
            "id": notebook_id,
            "title": notebook.get("title"),
            "description": notebook.get("description"),
            "risk": notebook.get("risk"),
            "params_schema": notebook.get("params_schema", {}),
            "requires_params": bool(notebook.get("params_schema", {}).get("required", []))
        }

    except Exception as e:
        logger.error(f"get_notebook_info failed: {e}", exc_info=True)
        return {
            "id": notebook_id,
            "title": None,
            "description": None,
            "risk": None,
            "params_schema": {},
            "requires_params": False,
            "error": str(e)
        }


@tool
def list_available_notebooks() -> Dict[str, Dict[str, Any]]:
    """
    List all available configuration notebooks with their metadata.

    Use this tool to discover what configuration notebooks are available
    before searching with scholar_search or executing with execute_notebook.

    Returns:
        Dict mapping notebook_id to metadata:
        {
            "cfg_set_hostname": {
                "title": "Set device hostname",
                "risk": "LOW",
                "requires_params": True
            },
            "cfg_create_vlan": {
                "title": "Create VLAN",
                "risk": "MEDIUM",
                "requires_params": True
            },
            ...
        }

    Example:
        >>> notebooks = list_available_notebooks()
        >>> print(f"Found {len(notebooks)} notebooks")
        >>> for nb_id, meta in notebooks.items():
        ...     print(f"{nb_id}: {meta['title']} (Risk: {meta['risk']})")
    """
    try:
        notebooks = _load_all_notebooks()
        return {
            nb_id: {
                "title": nb.get("title"),
                "description": nb.get("description"),
                "risk": nb.get("risk"),
                "requires_params": bool(nb.get("params_schema", {}).get("required", []))
            }
            for nb_id, nb in notebooks.items()
        }

    except Exception as e:
        logger.error(f"list_available_notebooks failed: {e}", exc_info=True)
        return {}


# ============================================================================
# CLI INTERFACE
# ============================================================================

def main():
    """CLI interface for testing tools."""
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python executor.py list              # List all notebooks")
        print("  python executor.py info <notebook_id>  # Get notebook schema")
        sys.exit(1)

    command = sys.argv[1]

    if command == "list":
        notebooks = list_available_notebooks.invoke({})
        print(json.dumps(notebooks, indent=2))

    elif command == "info" and len(sys.argv) >= 3:
        notebook_id = sys.argv[2]
        info = get_notebook_info.invoke({"notebook_id": notebook_id})
        print(json.dumps(info, indent=2))

    else:
        print("Invalid command. Use 'list' or 'info <notebook_id>'")
        sys.exit(1)


if __name__ == "__main__":
    main()

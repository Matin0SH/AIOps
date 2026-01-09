"""
Network CLI Agent
Natural language to collector function execution.
Uses Google Gemini Flash 2.5 for function selection and parameter extraction.
"""
import os
import json
import sys
from pathlib import Path
import yaml
import google.generativeai as genai
from dotenv import load_dotenv

sys.path.append(str(Path(__file__).parent.parent))

from collectors.router_collector import RouterCollector
from collectors.switch_collector import SwitchCollector
from .prompts import build_cli_selector_prompt


def load_yaml(file_path):
    """Load YAML configuration"""
    with open(file_path, "r") as f:
        return yaml.safe_load(f)


class NetworkCLIAgent:
    """Agent that maps natural language requests to collector functions."""

    def __init__(self):
        load_dotenv()

        # Load device configs
        config_dir = Path(__file__).parent.parent / "graph" / "config"
        self.devices = load_yaml(config_dir / "devices.yaml")["devices"]

        # Load available functions list
        functions_path = Path(__file__).parent.parent / "collectors" / "FUNCTIONS.md"
        self.functions_text = functions_path.read_text(encoding="utf-8")
        self.allowed_functions = self._parse_functions(self.functions_text)

        # Initialize Gemini
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable not set in .env file")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel("gemini-2.5-flash")

    def _parse_functions(self, text):
        """Extract function names from FUNCTIONS.md."""
        functions = set()
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("- "):
                name = line[2:].split("(", 1)[0].strip()
                if name and not name.startswith("__"):
                    functions.add(name)
        return sorted(functions)

    def _build_system_prompt(self):
        """Build system prompt for function selection"""
        device_names = sorted(self.devices.keys())
        return build_cli_selector_prompt(self.functions_text, device_names)

    def select_action(self, request: str) -> dict:
        """Select function and extract parameters from user request."""
        prompt = f"{self._build_system_prompt()}\n\nRequest: {request}"
        response = self.model.generate_content(prompt)
        full_response = response.text.strip()

        reasoning = ""
        if "<reasoning>" in full_response and "</reasoning>" in full_response:
            start = full_response.index("<reasoning>") + len("<reasoning>")
            end = full_response.index("</reasoning>")
            reasoning = full_response[start:end].strip()

        if "<response>" not in full_response or "</response>" not in full_response:
            raise ValueError("No valid response found in LLM output")

        response_start = full_response.index("<response>") + len("<response>")
        response_end = full_response.index("</response>")
        response_json_str = full_response[response_start:response_end].strip()

        try:
            response_data = json.loads(response_json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse response JSON: {e}")

        response_data["reasoning"] = reasoning
        return response_data

    def _resolve_device(self, name):
        """Resolve device name case-insensitively."""
        if name in self.devices:
            return name
        for key in self.devices.keys():
            if key.lower() == str(name).lower():
                return key
        return None

    def _build_collector(self, device_name, port_override=None):
        """Create a collector for the device."""
        device_cfg = self.devices[device_name]
        device_type = device_cfg.get("type", "").lower()
        host = device_cfg["mgmt_ip"]
        port = port_override if port_override else device_cfg["mgmt_port"]
        creds = device_cfg.get("credentials", {})

        if device_type == "router":
            return RouterCollector(device_name, host, port, creds)
        return SwitchCollector(device_name, host, port, creds)

    def execute(self, action: dict) -> dict:
        """Execute selected function with parameters."""
        if action.get("action") == "clarify":
            return {
                "success": False,
                "needs_clarification": True,
                "question": action.get("question", "Please clarify your request."),
                "reasoning": action.get("reasoning", ""),
            }

        func_name = action.get("function", "")
        device_name = action.get("device", "")
        port = action.get("port")
        params = action.get("params", {}) or {}

        if func_name not in self.allowed_functions:
            return {
                "success": False,
                "error": f"Function not allowed: {func_name}",
                "reasoning": action.get("reasoning", ""),
            }

        resolved_device = self._resolve_device(device_name)
        if not resolved_device:
            return {
                "success": False,
                "error": f"Unknown device: {device_name}",
                "reasoning": action.get("reasoning", ""),
            }

        collector = self._build_collector(resolved_device, port_override=port)

        try:
            collector.connect()
            if func_name == "send_show_command":
                command = params.get("command", "")
                if not command:
                    raise ValueError("Missing command for send_show_command")
                output = collector.send_show_command(command)
            elif func_name == "send_config_set":
                commands = params.get("commands", [])
                if not commands:
                    raise ValueError("Missing commands for send_config_set")
                output = collector.send_config_set(commands)
            else:
                if not hasattr(collector, func_name):
                    raise ValueError(f"Collector has no method: {func_name}")
                output = getattr(collector, func_name)()

            return {
                "success": True,
                "device": resolved_device,
                "function": func_name,
                "output": output,
                "reasoning": action.get("reasoning", ""),
            }
        except Exception as e:
            return {
                "success": False,
                "device": resolved_device,
                "function": func_name,
                "error": str(e),
                "reasoning": action.get("reasoning", ""),
            }
        finally:
            try:
                collector.disconnect()
            except Exception:
                pass

    def ask(self, request: str) -> dict:
        """End-to-end: select action then execute."""
        selection = self.select_action(request)
        return self.execute(selection)


def main():
    """Example usage"""
    agent = NetworkCLIAgent()
    examples = [
        "Show VLANs on CORE-SW1 port 5012",
        "Run show ip interface brief on EDGE-R1 port 5008",
        "Get CDP neighbors for MANAGEMENT port 5010",
    ]

    for req in examples:
        print(f"\n{'='*70}")
        print(f"Request: {req}")
        print("="*70)
        result = agent.ask(req)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

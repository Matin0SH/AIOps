"""
Network Configuration Agent

This module implements a network configuration agent using LangChain 0.3+ API.

Key features:
- create_agent API (LangChain 0.3+)
- Message-based architecture
- 11 tools (scholar, executor, cypher)
- Clean separation of concerns

Tools orchestrated:
- scholar_search: Find configuration notebooks (RAG)
- execute_notebook: Execute configs
- get_notebook_info: Get parameter schemas
- cypher tools: Query network topology (Neo4j)
"""
import os
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
import google.generativeai as genai

# LangChain imports
from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI

# Local imports
from tools.scholar import scholar_search
from tools.executor import execute_notebook, get_notebook_info, set_device_connection
from graph.cypher import (
    list_devices_tool,
    show_ospf_neighbors_tool,
    show_interfaces_connected_device_tool,
    show_cdp_neighbors_device_tool,
    show_ospf_neighbors_device_tool,
    show_shortest_path_tool,
    show_all_paths_tool,
)
from .prompts import SYSTEM_PROMPT_TEMPLATE, EXAMPLES


# Configuration
CONFIG_DIR = Path(__file__).parent.parent / "tools" / "configs"
ENV_PATH = CONFIG_DIR / ".env"
DEFAULT_MODEL = "gemini-2.5-flash"

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# SYSTEM PROMPT BUILDER
# ============================================================================

def _build_system_prompt() -> str:
    """
    Build complete system prompt from prompts.py template + examples.

    The new create_agent API only accepts a string for system_prompt,
    so we combine the base template with few-shot examples here.
    """
    # Add cypher tools to the base template
    cypher_tools_section = """
- list_devices_tool(): List all network devices
- show_ospf_neighbors_tool(): Show all OSPF adjacencies
- show_interfaces_connected_device_tool(device): Show connections for a device
- show_cdp_neighbors_device_tool(device): Show CDP neighbors for a device
- show_ospf_neighbors_device_tool(device): Show OSPF neighbors for a device
- show_shortest_path_tool(device1, device2): Find shortest path between two devices
- show_all_paths_tool(device1, device2): Show all shortest paths between two devices
"""

    # Build examples section from prompts.py EXAMPLES
    examples_section = "\n\nEXAMPLES OF CORRECT REASONING:\n\n"
    for i, ex in enumerate(EXAMPLES, 1):
        examples_section += f"Example {i}: {ex['input']}\n"
        examples_section += f"Thought: {ex['thought']}\n"
        examples_section += f"Action: {ex['action']}\n"
        examples_section += f"Observation: {ex['observation']}\n"
        examples_section += f"Answer: {ex['answer']}\n\n"

    # Combine: base template + cypher tools + examples
    full_prompt = SYSTEM_PROMPT_TEMPLATE + "\n" + cypher_tools_section + examples_section
    return full_prompt


# ============================================================================
# INITIALIZATION
# ============================================================================

def init_environment() -> None:
    """Load environment variables."""
    load_dotenv(ENV_PATH)
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY not set in configs/.env")
    genai.configure(api_key=api_key)


# ============================================================================
# AGENT FACTORY
# ============================================================================

def create_network_agent(
    model_name: str = DEFAULT_MODEL,
    temperature: float = 0,
    verbose: bool = True,
    checkpointer = None
):
    """
    Create a network configuration agent using LangChain 0.3+ API.

    Args:
        model_name: Gemini model to use (default: gemini-2.5-flash)
        temperature: LLM temperature (0 = deterministic)
        verbose: Enable detailed logging
        checkpointer: Optional checkpointer for memory persistence

    Returns:
        Compiled StateGraph ready to run

    Example:
        >>> agent = create_network_agent(verbose=True)
        >>> result = agent.invoke({"messages": [{"role": "user", "content": "Show all devices"}]})
        >>> print(result["messages"][-1].content)
    """
    # Initialize environment
    init_environment()

    # Create LLM
    llm = ChatGoogleGenerativeAI(
        model=model_name,
        temperature=temperature,
        convert_system_message_to_human=True  # Gemini compatibility
    )

    # Define tools (explicit list - best practice)
    tools = [
        # Configuration tools (scholar + executor)
        scholar_search,
        execute_notebook,
        get_notebook_info,

        # Topology tools (cypher)
        list_devices_tool,
        show_ospf_neighbors_tool,
        show_interfaces_connected_device_tool,
        show_cdp_neighbors_device_tool,
        show_ospf_neighbors_device_tool,
        show_shortest_path_tool,
        show_all_paths_tool,
    ]

    # Build system prompt from prompts.py
    system_prompt = _build_system_prompt()

    # Create agent using new LangChain 0.3+ API
    agent_graph = create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
        checkpointer=checkpointer,
        debug=verbose
    )

    logger.info(f"Network agent created: {model_name}, {len(tools)} tools")
    return agent_graph


# ============================================================================
# HIGH-LEVEL API (Facade Pattern)
# ============================================================================

class NetworkAgent:
    """
    High-level API for the network configuration agent.

    This wrapper provides a clean interface and manages device connections.

    Example:
        >>> from tools.base import BaseDeviceCollector
        >>> device = BaseDeviceCollector(host="10.0.0.1", username="admin", password="cisco")
        >>> agent = NetworkAgent(device=device)
        >>> response = agent.run("Enable SSH on this device")
        >>> print(response['output'])
    """

    def __init__(
        self,
        device: Optional[Any] = None,
        model_name: str = DEFAULT_MODEL,
        temperature: float = 0,
        verbose: bool = True,
        checkpointer = None
    ):
        """
        Initialize network agent with optional device connection.

        Args:
            device: BaseDeviceCollector instance (optional, can set later)
            model_name: Gemini model name
            temperature: LLM temperature
            verbose: Enable verbose logging
            checkpointer: Optional checkpointer for memory persistence
        """
        self.device = device
        if device:
            set_device_connection(device)

        self.agent_graph = create_network_agent(
            model_name=model_name,
            temperature=temperature,
            verbose=verbose,
            checkpointer=checkpointer
        )

        logger.info("NetworkAgent initialized")

    def set_device(self, device: Any) -> None:
        """
        Set or update the device connection.

        Args:
            device: BaseDeviceCollector instance
        """
        self.device = device
        set_device_connection(device)
        logger.info(f"Device connection updated: {device.host if hasattr(device, 'host') else 'Unknown'}")

    def run(self, query: str, thread_id: str = "default") -> Dict[str, Any]:
        """
        Run agent with a natural language query.

        Args:
            query: User's request in natural language
            thread_id: Thread ID for conversation memory (default: "default")

        Returns:
            Dict with 'output' key containing agent's final response

        Example:
            >>> response = agent.run("Set hostname to CORE-SW-01")
            >>> print(response['output'])
        """
        try:
            # New API uses message-based input
            config = {"configurable": {"thread_id": thread_id}}
            result = self.agent_graph.invoke(
                {"messages": [{"role": "user", "content": query}]},
                config=config
            )

            # Extract final message
            final_message = result["messages"][-1].content if result.get("messages") else "No response"

            return {
                "output": final_message,
                "messages": result.get("messages", []),
                "full_result": result
            }
        except Exception as e:
            logger.error(f"Agent execution failed: {e}", exc_info=True)
            return {
                "output": f"Error: {str(e)}",
                "error": str(e)
            }

    async def run_async(self, query: str, thread_id: str = "default"):
        """
        Run agent asynchronously.

        Args:
            query: User's request in natural language
            thread_id: Thread ID for conversation memory
        """
        try:
            config = {"configurable": {"thread_id": thread_id}}
            result = await self.agent_graph.ainvoke(
                {"messages": [{"role": "user", "content": query}]},
                config=config
            )

            final_message = result["messages"][-1].content if result.get("messages") else "No response"

            return {
                "output": final_message,
                "messages": result.get("messages", []),
                "full_result": result
            }
        except Exception as e:
            logger.error(f"Agent execution failed: {e}", exc_info=True)
            return {
                "output": f"Error: {str(e)}",
                "error": str(e)
            }

    def get_tools(self) -> List[str]:
        """Get list of available tool names."""
        return [
            "scholar_search",
            "execute_notebook",
            "get_notebook_info",
            "list_devices_tool",
            "show_ospf_neighbors_tool",
            "show_interfaces_connected_device_tool",
            "show_cdp_neighbors_device_tool",
            "show_ospf_neighbors_device_tool",
            "show_shortest_path_tool",
            "show_all_paths_tool"
        ]


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def run_agent_cli(query: str, device: Optional[Any] = None, verbose: bool = True) -> str:
    """
    Convenience function to run agent from command line or notebook.

    Args:
        query: Natural language query
        device: Optional device connection
        verbose: Enable verbose output

    Returns:
        Agent's response as string

    Example:
        >>> response = run_agent_cli("Show me all devices")
        >>> print(response)
    """
    agent = NetworkAgent(device=device, verbose=verbose)
    result = agent.run(query)
    return result.get("output", "No output generated")


# ============================================================================
# MAIN (for testing)
# ============================================================================

def main():
    """CLI interface for testing the agent."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python network_agent.py 'your query here'")
        print("\nExample:")
        print("  python network_agent.py 'Show me all devices'")
        print("  python network_agent.py 'Enable SSH on CORE-SW-01'")
        sys.exit(1)

    query = sys.argv[1]

    # Create agent (no device connection for read-only queries)
    agent = NetworkAgent(device=None, verbose=True)

    # Run query
    print(f"\n{'='*60}")
    print(f"Query: {query}")
    print(f"{'='*60}\n")

    result = agent.run(query)

    print(f"\n{'='*60}")
    print("Response:")
    print(f"{'='*60}")
    print(result.get("output", "No output"))
    print()


if __name__ == "__main__":
    main()

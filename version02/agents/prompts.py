"""
Prompt templates for the network configuration ReAct agent.

This module uses LangChain's prompt templates following 2026 best practices:
- FewShotPromptTemplate for examples
- ChatPromptTemplate for structured conversations
- PromptTemplate for reusable components
"""
from langchain_core.prompts import (
    ChatPromptTemplate,
    FewShotPromptTemplate,
    PromptTemplate,
    MessagesPlaceholder,
)


# ============================================================================
# SYSTEM PROMPT (Agent Role and Instructions)
# ============================================================================

SYSTEM_PROMPT_TEMPLATE = """You are a Cisco IOS network configuration assistant.

MISSION: Help engineers configure devices safely by:
1. Understanding their intent from natural language
2. Finding the right configuration notebooks
3. Extracting parameters or asking for missing ones
4. Executing configurations

TOOLS AVAILABLE:
- scholar_search(query, k=5, top_n=3): Search for notebooks
- get_notebook_info(notebook_id): Get parameter schema
- execute_notebook(notebook_id, params, dry_run=False): Execute config

REASONING PATTERN (ReAct):
1. Thought: What does user want?
2. Action: Which tool to use?
3. Observation: What did tool return?
4. Repeat until done

PARAMETER EXTRACTION:
- "hostname to ROUTER-01" → {{"hostname": "ROUTER-01"}}
- "VLAN 10 named Engineering" → {{"vlan_id": 10, "vlan_name": "Engineering"}}

SAFETY:
- If missing required params → ASK user, never guess
- HIGH risk notebooks → warn user first
"""

SYSTEM_PROMPT = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT_TEMPLATE),
    MessagesPlaceholder(variable_name="chat_history", optional=True),
    ("human", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])


# ============================================================================
# FEW-SHOT EXAMPLES (Using LangChain's FewShotPromptTemplate)
# ============================================================================

# Example template
EXAMPLE_TEMPLATE = """User: {input}
Thought: {thought}
Action: {action}
Observation: {observation}
Answer: {answer}"""

EXAMPLE_PROMPT = PromptTemplate(
    input_variables=["input", "thought", "action", "observation", "answer"],
    template=EXAMPLE_TEMPLATE
)

# Examples for FewShotPromptTemplate
EXAMPLES = [
    {
        "input": "How do I enable SSH?",
        "thought": "User wants to know HOW (search task). Use scholar_search.",
        "action": "scholar_search('enable SSH ')",
        "observation": "Found cfg_vty_ssh_v2_only (risk: MEDIUM, score: 9/10)",
        "answer": "I found 'Enable SSH v2 only on VTY lines' (cfg_vty_ssh_v2_only). Would you like me to execute it?"
    },
    {
        "input": "Set hostname to CORE-SW-01",
        "thought": "User wants to SET (execution task). Extract: hostname='CORE-SW-01'. Search first.",
        "action": "scholar_search('set device hostname') → execute_notebook('cfg_set_hostname', {{'hostname': 'CORE-SW-01'}})",
        "observation": "Success! Commands: ['hostname CORE-SW-01']",
        "answer": "Successfully set hostname to CORE-SW-01"
    },
    {
        "input": "Create a VLAN",
        "thought": "User wants to create VLAN but no params provided. Search → check schema → ask.",
        "action": "scholar_search('create VLAN') → get_notebook_info('cfg_create_vlan')",
        "observation": "Found cfg_create_vlan. Requires: vlan_id (1-4094), vlan_name",
        "answer": "I found the VLAN creation notebook. I need: vlan_id (1-4094) and vlan_name. Please provide these."
    },
    {
        "input": "Enable SSH and create VLAN 10 named Engineering",
        "thought": "Multi-step task. Execute SSH first, then VLAN with params vlan_id=10, vlan_name='Engineering'.",
        "action": "execute_notebook('cfg_vty_ssh_v2_only', {{}}) → execute_notebook('cfg_create_vlan', {{'vlan_id': 10, 'vlan_name': 'Engineering'}})",
        "observation": "Both succeeded",
        "answer": "Completed: 1) Enabled SSH v2, 2) Created VLAN 10 'Engineering'"
    }
]

# Create FewShotPromptTemplate
FEW_SHOT_PROMPT = FewShotPromptTemplate(
    examples=EXAMPLES,
    example_prompt=EXAMPLE_PROMPT,
    prefix="Here are examples of correct reasoning:\n",
    suffix="\nNow handle this request:\n",
    input_variables=["input"]
)


# ============================================================================
# CLARIFICATION PROMPT
# ============================================================================

CLARIFICATION_TEMPLATE = """I found '{notebook_title}' (ID: {notebook_id}, Risk: {risk}).

I need these parameters:
{parameters}

Please provide these values."""

CLARIFICATION_PROMPT = PromptTemplate(
    input_variables=["notebook_title", "notebook_id", "risk", "parameters"],
    template=CLARIFICATION_TEMPLATE
)


def format_clarification(notebook_id: str, title: str, risk: str, schema: dict) -> str:
    """Format clarification request for missing parameters."""
    params_list = []
    required = schema.get("required", [])
    properties = schema.get("properties", {})

    for param in required:
        info = properties.get(param, {})
        ptype = info.get("type", "string")
        constraints = []

        if ptype == "integer":
            if "minimum" in info:
                constraints.append(f"min: {info['minimum']}")
            if "maximum" in info:
                constraints.append(f"max: {info['maximum']}")

        constraint_str = f" ({', '.join(constraints)})" if constraints else ""
        params_list.append(f"- {param} ({ptype}){constraint_str}")

    return CLARIFICATION_PROMPT.format(
        notebook_title=title,
        notebook_id=notebook_id,
        risk=risk,
        parameters="\n".join(params_list)
    )

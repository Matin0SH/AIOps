"""
Pydantic schemas for the network configuration ReAct agent.

This module defines strict JSON schemas for:
- Agent responses and decisions
- Clarification requests
- Execution tracking

Following 2026 best practices:
- Rich Field descriptions guide the LLM
- Literal types prevent hallucinated actions
- Validation at boundaries (input/output)
"""
from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field, field_validator


# ============================================================================
# CLARIFICATION SCHEMAS
# ============================================================================

class ParameterRequest(BaseModel):
    """Schema for a single missing parameter."""
    name: str = Field(description="Parameter name (e.g., 'hostname', 'vlan_id')")
    type: str = Field(description="Parameter type (e.g., 'string', 'integer')")
    description: str = Field(description="Human-readable description of what this parameter does")
    required: bool = Field(default=True, description="Whether this parameter is required")
    constraints: Optional[str] = Field(None, description="Validation constraints (e.g., '1-4094', 'alphanumeric')")


class ClarificationRequest(BaseModel):
    """
    Request for missing information from user.

    The agent returns this when it cannot proceed without additional input.
    """
    notebook_id: str = Field(description="Notebook ID that needs parameters (e.g., 'cfg_create_vlan')")
    notebook_title: str = Field(description="Human-readable notebook title")
    missing_params: List[ParameterRequest] = Field(
        description="List of parameters that need to be provided"
    )
    context: str = Field(description="Explanation of why we need this information and what it will do")

    class Config:
        json_schema_extra = {
            "example": {
                "notebook_id": "cfg_create_vlan",
                "notebook_title": "Create VLAN",
                "missing_params": [
                    {
                        "name": "vlan_id",
                        "type": "integer",
                        "description": "VLAN ID to create",
                        "required": True,
                        "constraints": "1-4094"
                    },
                    {
                        "name": "vlan_name",
                        "type": "string",
                        "description": "VLAN name",
                        "required": True,
                        "constraints": "alphanumeric, max 32 chars"
                    }
                ],
                "context": "I found the VLAN creation notebook, but need the VLAN ID and name to proceed."
            }
        }


# ============================================================================
# EXECUTION TRACKING SCHEMAS
# ============================================================================

class ExecutionStep(BaseModel):
    """
    Single step in a multi-step execution plan.

    Tracks progress for tasks like "Enable SSH and create VLAN 10".
    """
    step_number: int = Field(ge=1, description="Step sequence number (1-indexed)")
    action: Literal["search", "execute", "clarify"] = Field(
        description="Type of action for this step"
    )
    description: str = Field(description="Human-readable description of what this step does")
    notebook_id: Optional[str] = Field(None, description="Notebook ID if known")
    notebook_title: Optional[str] = Field(None, description="Notebook title if known")
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Parameters extracted from user query or provided by user"
    )
    status: Literal["pending", "in_progress", "completed", "failed"] = Field(
        default="pending",
        description="Current status of this step"
    )
    result: Optional[Dict[str, Any]] = Field(None, description="Execution result if completed")
    error: Optional[str] = Field(None, description="Error message if failed")


class ExecutionPlan(BaseModel):
    """
    Complete execution plan for multi-step tasks.

    Example: "Enable SSH and create VLAN 10" → 2 steps
    """
    query: str = Field(description="Original user query")
    total_steps: int = Field(ge=1, description="Total number of steps in the plan")
    steps: List[ExecutionStep] = Field(description="Ordered list of execution steps")
    current_step: int = Field(default=1, ge=1, description="Currently executing step number")

    @field_validator('steps')
    @classmethod
    def validate_steps_count(cls, v, info):
        """Ensure steps list matches total_steps."""
        total_steps = info.data.get('total_steps')
        if total_steps and len(v) != total_steps:
            raise ValueError(f"steps list length ({len(v)}) must match total_steps ({total_steps})")
        return v


# ============================================================================
# AGENT RESPONSE SCHEMAS
# ============================================================================

class NotebookExecutionSummary(BaseModel):
    """Summary of a single notebook execution."""
    notebook_id: str = Field(description="Executed notebook ID")
    title: str = Field(description="Notebook title")
    success: bool = Field(description="Whether execution succeeded")
    risk: Optional[str] = Field(None, description="Risk level (LOW/MEDIUM/HIGH)")
    commands_sent: List[str] = Field(default_factory=list, description="Commands sent to device")
    error: Optional[str] = Field(None, description="Error message if failed")


class AgentResponse(BaseModel):
    """
    Final response from the network configuration agent.

    This is the structured output returned to the user.
    """
    success: bool = Field(description="Whether the overall task completed successfully")
    message: str = Field(description="Human-readable response message for the user")

    # Execution results
    executed_notebooks: List[NotebookExecutionSummary] = Field(
        default_factory=list,
        description="List of notebooks that were executed"
    )

    # Clarification handling
    needs_clarification: bool = Field(
        default=False,
        description="True if agent needs more information from user"
    )
    clarification: Optional[ClarificationRequest] = Field(
        None,
        description="Clarification request if needs_clarification is True"
    )

    # Multi-step tracking
    is_multi_step: bool = Field(
        default=False,
        description="True if this was a multi-step task"
    )
    execution_plan: Optional[ExecutionPlan] = Field(
        None,
        description="Execution plan for multi-step tasks"
    )

    # Error handling
    error: Optional[str] = Field(None, description="Error message if task failed")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Successfully configured SSH and created VLAN 10 'Engineering'",
                "executed_notebooks": [
                    {
                        "notebook_id": "cfg_vty_ssh_v2_only",
                        "title": "Enable SSH v2 only on VTY lines",
                        "success": True,
                        "risk": "MEDIUM",
                        "commands_sent": ["line vty 0 4", "transport input ssh", "exit"]
                    },
                    {
                        "notebook_id": "cfg_create_vlan",
                        "title": "Create VLAN",
                        "success": True,
                        "risk": "LOW",
                        "commands_sent": ["vlan 10", "name Engineering", "exit"]
                    }
                ],
                "needs_clarification": False,
                "is_multi_step": True,
                "execution_plan": {
                    "query": "Enable SSH and create VLAN 10 named Engineering",
                    "total_steps": 2,
                    "steps": [],
                    "current_step": 2
                }
            }
        }


# ============================================================================
# AGENT DECISION SCHEMAS (Internal)
# ============================================================================

class AgentThought(BaseModel):
    """
    Agent's internal reasoning before taking action.

    This helps with debugging and understanding agent decisions.
    Used internally, not shown to end users.
    """
    observation: str = Field(description="What the agent observed from the last action/user input")
    reasoning: str = Field(description="Agent's thought process (1-3 sentences)")
    next_action: Literal["search", "get_info", "execute", "clarify", "complete"] = Field(
        description="Next action the agent will take"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Agent's confidence in this decision (0.0 to 1.0)"
    )
    tool_input: Dict[str, Any] = Field(
        default_factory=dict,
        description="Input parameters for the next tool call"
    )


# ============================================================================
# VALIDATION HELPERS
# ============================================================================

class NotebookParameterValidation(BaseModel):
    """
    Validation schema for extracted parameters.

    Used to validate parameters extracted from user queries before execution.
    """
    notebook_id: str = Field(description="Target notebook ID")
    extracted_params: Dict[str, Any] = Field(description="Parameters extracted from user query")
    missing_required: List[str] = Field(
        default_factory=list,
        description="List of required parameters that are missing"
    )
    validation_passed: bool = Field(description="Whether all validations passed")
    validation_errors: List[str] = Field(
        default_factory=list,
        description="List of validation error messages"
    )


# ============================================================================
# RISK ASSESSMENT SCHEMAS
# ============================================================================

class RiskAssessment(BaseModel):
    """
    Risk assessment for notebook execution.

    Used when HIGH-risk notebooks require user confirmation.
    """
    notebook_id: str = Field(description="Notebook being assessed")
    risk_level: Literal["LOW", "MEDIUM", "HIGH"] = Field(description="Risk level from notebook metadata")
    requires_approval: bool = Field(description="Whether user approval is needed before execution")
    risk_explanation: str = Field(description="Explanation of what makes this risky")
    mitigation: str = Field(description="Recommended mitigation (e.g., 'test in staging first')")

    class Config:
        json_schema_extra = {
            "example": {
                "notebook_id": "cfg_reload_device",
                "risk_level": "HIGH",
                "requires_approval": True,
                "risk_explanation": "This will reload the device, causing downtime",
                "mitigation": "Schedule during maintenance window. Save config first."
            }
        }


# ============================================================================
# CONVERSATION MEMORY SCHEMAS (Optional)
# ============================================================================

class ConversationTurn(BaseModel):
    """
    Single turn in the conversation history.

    Optional: Use this if you want to track conversation context.
    """
    turn_number: int = Field(ge=1, description="Turn number in conversation (1-indexed)")
    user_message: str = Field(description="User's input message")
    agent_response: AgentResponse = Field(description="Agent's structured response")
    tools_used: List[str] = Field(
        default_factory=list,
        description="List of tool names used in this turn"
    )
    timestamp: Optional[str] = Field(None, description="ISO format timestamp")


class ConversationHistory(BaseModel):
    """
    Complete conversation history.

    Optional: Use this to maintain context across multiple turns.
    """
    session_id: str = Field(description="Unique session identifier")
    turns: List[ConversationTurn] = Field(default_factory=list, description="List of conversation turns")
    total_notebooks_executed: int = Field(default=0, description="Total notebooks executed in this session")

    def add_turn(self, user_message: str, agent_response: AgentResponse, tools_used: List[str]) -> None:
        """Add a new turn to the conversation history."""
        turn = ConversationTurn(
            turn_number=len(self.turns) + 1,
            user_message=user_message,
            agent_response=agent_response,
            tools_used=tools_used
        )
        self.turns.append(turn)

        # Update total notebooks executed
        self.total_notebooks_executed += len(agent_response.executed_notebooks)

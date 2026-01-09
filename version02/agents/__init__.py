"""
Network Configuration Agent Module

Exports:
- Schemas: Pydantic models for agent I/O
- Agent: ReAct agent implementation
- NetworkAgent: High-level API wrapper
"""
from .schemas import (
    # Clarification
    ParameterRequest,
    ClarificationRequest,

    # Execution tracking
    ExecutionStep,
    ExecutionPlan,
    NotebookExecutionSummary,

    # Agent responses
    AgentResponse,
    AgentThought,

    # Validation
    NotebookParameterValidation,
    RiskAssessment,

    # Optional: Conversation history
    ConversationTurn,
    ConversationHistory,
)

from .network_agent import (
    NetworkAgent,
    create_network_agent,
    run_agent_cli,
)

__all__ = [
    # Schemas
    "ParameterRequest",
    "ClarificationRequest",
    "ExecutionStep",
    "ExecutionPlan",
    "NotebookExecutionSummary",
    "AgentResponse",
    "AgentThought",
    "NotebookParameterValidation",
    "RiskAssessment",
    "ConversationTurn",
    "ConversationHistory",

    # Agent
    "NetworkAgent",
    "create_network_agent",
    "run_agent_cli",
]

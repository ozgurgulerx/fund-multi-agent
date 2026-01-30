"""
Multi-agent system for portfolio optimization using Microsoft Agent Framework.
Each agent is a ChatAgent with specialized tools decorated with @tool.
"""

# Agent factory functions (new Agent Framework pattern)
from backend.agents.market import create_market_agent, get_market_agent
from backend.agents.risk import create_risk_agent, get_risk_agent
from backend.agents.return_agent import create_return_agent, get_return_agent
from backend.agents.optimizer import create_optimizer_agent, get_optimizer_agent
from backend.agents.compliance import create_compliance_agent, get_compliance_agent

# Chat client factory
from backend.agents.client import (
    get_chat_client,
    get_shared_chat_client,
    get_orchestrator_chat_client,
    get_deployment_info,
)

__all__ = [
    # Agent factories
    "create_market_agent",
    "create_risk_agent",
    "create_return_agent",
    "create_optimizer_agent",
    "create_compliance_agent",
    # Backward-compatible getters
    "get_market_agent",
    "get_risk_agent",
    "get_return_agent",
    "get_optimizer_agent",
    "get_compliance_agent",
    # Chat clients
    "get_chat_client",
    "get_shared_chat_client",
    "get_orchestrator_chat_client",  # For orchestrator/manager (gpt-5-mini)
    "get_deployment_info",
]

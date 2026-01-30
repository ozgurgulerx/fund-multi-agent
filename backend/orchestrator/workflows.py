"""
Workflow definitions using Microsoft Agent Framework patterns.

This module implements various orchestration patterns:
- SequentialBuilder: For linear task execution
- ConcurrentBuilder: For parallel/fan-out execution
- HandoffBuilder: For agent-to-agent handoffs
- MagenticBuilder: For LLM-powered dynamic orchestration
- WorkflowBuilder: For custom DAG-based workflows
"""

from typing import Any, Callable, Dict, List, Optional
from datetime import datetime, timezone

from agent_framework import (
    ChatAgent,
    Workflow,
    WorkflowBuilder,
    SequentialBuilder,
    ConcurrentBuilder,
    HandoffBuilder,
    MagenticBuilder,
    GroupChatBuilder,
    Executor,
    WorkflowContext,
    handler,
    AgentExecutorResponse,
    ChatMessage,
)
import structlog

from backend.agents import (
    create_market_agent,
    create_risk_agent,
    create_return_agent,
    create_optimizer_agent,
    create_compliance_agent,
)
from backend.orchestrator.executors import (
    WorkflowState,
    PolicyParserExecutor,
    RiskReturnAggregatorExecutor,
    PortfolioFinalizerExecutor,
    ComplianceGateExecutor,
)

logger = structlog.get_logger()


# =============================================================================
# SEQUENTIAL WORKFLOW
# For simple linear execution: Market → Risk → Return → Optimizer → Compliance
# =============================================================================

def create_sequential_workflow(
    name: str = "sequential_portfolio_optimization"
) -> Workflow:
    """
    Create a sequential workflow where agents execute in order.

    Flow: Market Agent → Risk Agent → Return Agent → Optimizer Agent → Compliance Agent

    Each agent receives the conversation history from previous agents,
    building up context as the workflow progresses.
    """
    logger.info("creating_sequential_workflow", name=name)

    # Create agents
    market_agent = create_market_agent(name="market_agent")
    risk_agent = create_risk_agent(name="risk_agent")
    return_agent = create_return_agent(name="return_agent")
    optimizer_agent = create_optimizer_agent(name="optimizer_agent")
    compliance_agent = create_compliance_agent(name="compliance_agent")

    workflow = (
        SequentialBuilder()
        .participants([
            market_agent,
            risk_agent,
            return_agent,
            optimizer_agent,
            compliance_agent,
        ])
        .build()
    )

    logger.info(
        "sequential_workflow_created",
        name=name,
        participant_count=5,
    )

    return workflow


# =============================================================================
# CONCURRENT WORKFLOW (Fan-out/Fan-in)
# For parallel execution with aggregation
# =============================================================================

def create_concurrent_risk_return_workflow(
    name: str = "concurrent_risk_return_analysis"
) -> Workflow:
    """
    Create a concurrent workflow where risk and return agents run in parallel.

    Fan-out: Input → [Risk Agent, Return Agent] (parallel)
    Fan-in: Results aggregated into combined analysis

    This pattern is useful when analyses are independent and can run simultaneously.
    """
    logger.info("creating_concurrent_workflow", name=name)

    # Create agents for parallel execution
    risk_agent = create_risk_agent(name="risk_agent")
    return_agent = create_return_agent(name="return_agent")

    # Custom aggregator that combines risk and return results
    def aggregate_risk_return(results: List[AgentExecutorResponse]) -> Dict[str, Any]:
        """Aggregate parallel results from risk and return agents."""
        combined = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_results": [],
        }

        for result in results:
            agent_name = result.agent_run_response.agent_name or "unknown"
            messages = result.agent_run_response.messages
            last_message = messages[-1] if messages else None

            combined["agent_results"].append({
                "agent": agent_name,
                "response": last_message.text if last_message else "",
                "message_count": len(messages),
            })

            logger.info(
                "concurrent_agent_completed",
                agent=agent_name,
                message_count=len(messages),
            )

        combined["analysis_count"] = len(results)
        return combined

    workflow = (
        ConcurrentBuilder()
        .participants([risk_agent, return_agent])
        .with_aggregator(aggregate_risk_return)
        .build()
    )

    logger.info(
        "concurrent_workflow_created",
        name=name,
        participant_count=2,
    )

    return workflow


# =============================================================================
# HANDOFF WORKFLOW
# For coordinator-based delegation to specialists
# =============================================================================

def create_handoff_workflow(
    name: str = "handoff_portfolio_advisor",
    interaction_mode: str = "autonomous"
) -> Workflow:
    """
    Create a handoff workflow with a coordinator and specialist agents.

    The coordinator (market agent) acts as the frontline and can hand off to:
    - Risk Agent: For risk assessment questions
    - Return Agent: For return/performance questions
    - Optimizer Agent: For allocation optimization
    - Compliance Agent: For regulatory/policy compliance

    Args:
        name: Workflow name
        interaction_mode: "autonomous" or "human_in_loop"
    """
    logger.info("creating_handoff_workflow", name=name, mode=interaction_mode)

    # Create coordinator - the market agent serves as the entry point
    coordinator = create_market_agent(name="coordinator_agent")

    # Update coordinator instructions to understand handoff capabilities
    coordinator_instructions = """You are the Portfolio Advisor Coordinator.

Your role is to:
1. Understand the investor's policy and requirements
2. Gather market data and build the investment universe
3. Delegate to specialist agents when needed:
   - Hand off to 'risk_agent' for risk analysis, VaR calculations, stress testing
   - Hand off to 'return_agent' for return forecasting, theme evaluation
   - Hand off to 'optimizer_agent' for portfolio optimization, rebalancing
   - Hand off to 'compliance_agent' for regulatory checks, ESG verification

When you need specialist analysis, use the appropriate handoff tool.
After receiving specialist input, synthesize the information and continue.
"""
    coordinator._instructions = coordinator_instructions

    # Create specialist agents
    risk_agent = create_risk_agent(name="risk_agent")
    return_agent = create_return_agent(name="return_agent")
    optimizer_agent = create_optimizer_agent(name="optimizer_agent")
    compliance_agent = create_compliance_agent(name="compliance_agent")

    # Build handoff workflow
    builder = HandoffBuilder(
        name=name,
        participants=[coordinator, risk_agent, return_agent, optimizer_agent, compliance_agent],
    ).set_coordinator(coordinator)

    # Set interaction mode
    if interaction_mode == "autonomous":
        builder = builder.with_interaction_mode("autonomous")
    else:
        builder = builder.with_interaction_mode("human_in_loop")

    # Add termination condition - complete after optimization and compliance
    def should_terminate(conversation: List[ChatMessage]) -> bool:
        """Terminate when we have both optimization and compliance results."""
        text = " ".join(m.text or "" for m in conversation[-5:]).lower()
        return (
            "portfolio" in text and
            ("compliant" in text or "allocation" in text) and
            len(conversation) > 10
        )

    builder = builder.with_termination_condition(should_terminate)

    workflow = builder.build()

    logger.info(
        "handoff_workflow_created",
        name=name,
        coordinator="coordinator_agent",
        specialist_count=4,
    )

    return workflow


# =============================================================================
# MAGENTIC-ONE WORKFLOW
# For LLM-powered dynamic orchestration with planning
# =============================================================================

def create_magentic_workflow(
    name: str = "magentic_portfolio_optimization",
    max_rounds: int = 15,
    enable_plan_review: bool = False,
) -> Workflow:
    """
    Create a Magentic-One style workflow with LLM-powered orchestration.

    The Magentic pattern uses a manager that:
    1. Creates dynamic plans based on the task
    2. Selects appropriate agents for each step
    3. Monitors progress and adapts the plan
    4. Handles stalls and replanning

    This is the most flexible orchestration pattern, suitable for complex
    tasks where the execution path isn't predetermined.

    Args:
        name: Workflow name
        max_rounds: Maximum orchestration rounds
        enable_plan_review: Whether to pause for human plan review
    """
    logger.info(
        "creating_magentic_workflow",
        name=name,
        max_rounds=max_rounds,
        plan_review=enable_plan_review,
    )

    # Create specialized agents
    market_agent = create_market_agent(name="market_data_specialist")
    risk_agent = create_risk_agent(name="risk_analyst")
    return_agent = create_return_agent(name="return_forecaster")
    optimizer_agent = create_optimizer_agent(name="portfolio_optimizer")
    compliance_agent = create_compliance_agent(name="compliance_officer")

    # Create a manager agent for orchestrating the workflow
    # Uses orchestrator deployment (gpt-5-mini) for better planning capabilities
    from backend.agents.client import get_orchestrator_chat_client
    manager_agent = ChatAgent(
        chat_client=get_orchestrator_chat_client(),
        name="magentic_manager",
        instructions="""You are the Magentic Manager for portfolio optimization.
Your role is to plan and coordinate the execution of specialist agents to optimize a portfolio.
Create a plan, select appropriate agents for each step, and adapt based on results.""",
    )

    # Build Magentic workflow
    builder = (
        MagenticBuilder()
        .participants(
            market=market_agent,
            risk=risk_agent,
            returns=return_agent,
            optimizer=optimizer_agent,
            compliance=compliance_agent,
        )
        .with_standard_manager(
            agent=manager_agent,
            max_round_count=max_rounds,
            max_stall_count=3,
        )
    )

    workflow = builder.build()

    logger.info(
        "magentic_workflow_created",
        name=name,
        participant_count=5,
        max_rounds=max_rounds,
    )

    return workflow


# =============================================================================
# CUSTOM DAG WORKFLOW
# For complex workflows with specific execution paths
# =============================================================================

def create_dag_portfolio_workflow(
    name: str = "dag_portfolio_optimization"
) -> Workflow:
    """
    Create a custom DAG-based workflow with explicit execution paths.

    This workflow defines a directed acyclic graph:

                          ┌─────────────┐
                          │   Policy    │
                          │   Parser    │
                          └──────┬──────┘
                                 │
                          ┌──────▼──────┐
                          │   Market    │
                          │   Agent     │
                          └──────┬──────┘
                                 │
                    ┌────────────┼────────────┐
                    │            │            │
              ┌─────▼─────┐ ┌────▼────┐       │
              │   Risk    │ │ Return  │       │
              │   Agent   │ │  Agent  │       │
              └─────┬─────┘ └────┬────┘       │
                    │            │            │
                    └────────┬───┘            │
                             │                │
                      ┌──────▼──────┐         │
                      │ Aggregator  │         │
                      └──────┬──────┘         │
                             │                │
                      ┌──────▼──────┐         │
                      │ Optimizer   │◄────────┘
                      │   Agent     │
                      └──────┬──────┘
                             │
                      ┌──────▼──────┐
                      │ Compliance  │
                      │   Agent     │
                      └──────┬──────┘
                             │
                      ┌──────▼──────┐
                      │ Finalizer   │
                      └─────────────┘
    """
    logger.info("creating_dag_workflow", name=name)

    # Build the DAG workflow as a chain with sequential flow
    # Note: True fan-out/fan-in requires compatible message types between agents
    # For simplicity, we use a chain: Market → Risk → Return → Optimizer → Compliance
    workflow = (
        WorkflowBuilder(name=name, max_iterations=50)

        # Register agents (lazy initialization for proper workflow sharing)
        .register_agent(lambda: create_market_agent(name="market_agent"), name="MarketAgent")
        .register_agent(lambda: create_risk_agent(name="risk_agent"), name="RiskAgent")
        .register_agent(lambda: create_return_agent(name="return_agent"), name="ReturnAgent")
        .register_agent(lambda: create_optimizer_agent(name="optimizer_agent"), name="OptimizerAgent")
        .register_agent(lambda: create_compliance_agent(name="compliance_agent"), name="ComplianceAgent")

        # Set start point and chain: Market → Risk → Return → Optimizer → Compliance
        .set_start_executor("MarketAgent")
        .add_chain(["MarketAgent", "RiskAgent", "ReturnAgent", "OptimizerAgent", "ComplianceAgent"])

        .build()
    )

    logger.info(
        "dag_workflow_created",
        name=name,
        executor_count=3,
        agent_count=5,
    )

    return workflow


# =============================================================================
# GROUP CHAT WORKFLOW
# For multi-agent consensus discussions and collaborative decision-making
# =============================================================================

def create_group_chat_workflow(
    name: str = "group_chat_portfolio_consensus",
    max_rounds: int = 10,
) -> Workflow:
    """
    Create a group chat workflow for multi-agent consensus discussions.

    In this pattern, all agents participate in a round-robin discussion
    where they can see each other's responses and reach consensus on
    portfolio recommendations.

    This is useful when:
    - You need multiple perspectives on a complex decision
    - Agents need to debate and refine recommendations
    - Consensus-building is important (e.g., risk vs return tradeoffs)

    Args:
        name: Workflow name
        max_rounds: Maximum rounds of discussion before concluding
    """
    logger.info(
        "creating_group_chat_workflow",
        name=name,
        max_rounds=max_rounds,
    )

    # Create agents for the discussion
    risk_agent = create_risk_agent(name="risk_advisor")
    return_agent = create_return_agent(name="return_advisor")
    optimizer_agent = create_optimizer_agent(name="portfolio_architect")
    compliance_agent = create_compliance_agent(name="compliance_reviewer")

    # Define termination condition for consensus
    def has_reached_consensus(conversation: List[ChatMessage]) -> bool:
        """Check if agents have reached consensus."""
        if len(conversation) < 6:
            return False

        # Look for consensus signals in recent messages
        recent_text = " ".join(
            m.text or "" for m in conversation[-4:]
        ).lower()

        consensus_signals = [
            "agree with",
            "consensus",
            "aligned",
            "recommend",
            "final allocation",
            "approved",
        ]

        return any(signal in recent_text for signal in consensus_signals)

    # Create a manager agent for the group chat
    # Uses orchestrator deployment (gpt-5-mini) for better coordination capabilities
    from backend.agents.client import get_orchestrator_chat_client
    manager_agent = ChatAgent(
        chat_client=get_orchestrator_chat_client(),
        name="group_chat_manager",
        instructions="""You are the Group Chat Manager for portfolio optimization.
Your role is to facilitate discussion between specialist agents and select who speaks next.
Guide the conversation toward consensus on portfolio allocation decisions.
Select speakers based on the current topic and who has relevant expertise.""",
    )

    workflow = (
        GroupChatBuilder()
        .participants([
            risk_agent,
            return_agent,
            optimizer_agent,
            compliance_agent,
        ])
        .set_manager(manager_agent)
        .with_max_rounds(max_rounds)
        .with_termination_condition(has_reached_consensus)
        .build()
    )

    logger.info(
        "group_chat_workflow_created",
        name=name,
        participant_count=4,
        max_rounds=max_rounds,
    )

    return workflow


# =============================================================================
# WORKFLOW FACTORY
# Unified interface for creating workflows
# =============================================================================

class WorkflowType:
    """Available workflow types."""
    SEQUENTIAL = "sequential"
    CONCURRENT = "concurrent"
    HANDOFF = "handoff"
    MAGENTIC = "magentic"
    DAG = "dag"
    GROUP_CHAT = "group_chat"  # Multi-agent consensus discussions


def create_workflow(
    workflow_type: str,
    name: Optional[str] = None,
    **kwargs
) -> Workflow:
    """
    Factory function to create workflows of different types.

    Args:
        workflow_type: One of WorkflowType constants
        name: Optional workflow name
        **kwargs: Additional arguments for specific workflow types

    Returns:
        Configured Workflow instance
    """
    logger.info(
        "creating_workflow",
        workflow_type=workflow_type,
        name=name,
    )

    if workflow_type == WorkflowType.SEQUENTIAL:
        return create_sequential_workflow(name=name or "sequential_workflow")

    elif workflow_type == WorkflowType.CONCURRENT:
        return create_concurrent_risk_return_workflow(name=name or "concurrent_workflow")

    elif workflow_type == WorkflowType.HANDOFF:
        return create_handoff_workflow(
            name=name or "handoff_workflow",
            interaction_mode=kwargs.get("interaction_mode", "autonomous"),
        )

    elif workflow_type == WorkflowType.MAGENTIC:
        return create_magentic_workflow(
            name=name or "magentic_workflow",
            max_rounds=kwargs.get("max_rounds", 15),
            enable_plan_review=kwargs.get("enable_plan_review", False),
        )

    elif workflow_type == WorkflowType.DAG:
        return create_dag_portfolio_workflow(name=name or "dag_workflow")

    elif workflow_type == WorkflowType.GROUP_CHAT:
        return create_group_chat_workflow(
            name=name or "group_chat_workflow",
            max_rounds=kwargs.get("max_rounds", 10),
        )

    else:
        raise ValueError(f"Unknown workflow type: {workflow_type}")

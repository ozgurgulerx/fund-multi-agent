"""
Agent Registry for Dynamic Orchestration.

Defines all available agents with their inclusion/exclusion conditions
based on the Investor Policy Statement.
"""

from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel
from backend.schemas.policy import InvestorPolicyStatement


class AgentCondition(BaseModel):
    """Condition for agent inclusion/exclusion."""
    field: str  # Policy field to check
    operator: str  # eq, ne, gt, lt, gte, lte, in, not_in, contains
    value: Any
    reason: str  # Human-readable reason


class AgentDefinition(BaseModel):
    """Definition of an agent in the registry."""
    id: str
    name: str
    short_name: str
    category: str  # core, risk, optimization, compliance, conditional
    description: str

    # Conditions for inclusion (all must be true to include)
    include_conditions: List[AgentCondition] = []

    # Conditions for exclusion (any true will exclude)
    exclude_conditions: List[AgentCondition] = []

    # Default inclusion if no conditions match
    default_include: bool = True

    # Priority for execution order (lower = earlier)
    priority: int = 50


# ============================================================================
# AGENT REGISTRY
# ============================================================================

AGENT_REGISTRY: List[AgentDefinition] = [
    # -------------------------------------------------------------------------
    # CORE AGENTS (Always included)
    # -------------------------------------------------------------------------
    AgentDefinition(
        id="market_agent",
        name="Market Data Agent",
        short_name="Market",
        category="core",
        description="Fetches market data and builds investment universe",
        default_include=True,
        priority=10,
    ),
    AgentDefinition(
        id="risk_agent",
        name="Risk Analysis Agent",
        short_name="Risk",
        category="core",
        description="Computes VaR, volatility, and risk metrics",
        default_include=True,
        priority=20,
    ),
    AgentDefinition(
        id="return_agent",
        name="Return Forecasting Agent",
        short_name="Returns",
        category="core",
        description="Forecasts expected returns and evaluates themes",
        default_include=True,
        priority=30,
    ),
    AgentDefinition(
        id="optimizer_agent",
        name="Portfolio Optimizer Agent",
        short_name="Optimizer",
        category="core",
        description="Optimizes portfolio allocation using mean-variance",
        default_include=True,
        priority=40,
    ),
    AgentDefinition(
        id="compliance_agent",
        name="Compliance Agent",
        short_name="Compliance",
        category="core",
        description="Validates allocations against policy constraints",
        default_include=True,
        priority=50,
    ),

    # -------------------------------------------------------------------------
    # CONDITIONAL AGENTS (Based on policy)
    # -------------------------------------------------------------------------
    AgentDefinition(
        id="challenger_optimizer",
        name="Challenger Optimizer Agent",
        short_name="Challenger",
        category="optimization",
        description="Alternative solver for theme tilts and complex constraints",
        default_include=False,
        priority=45,
        include_conditions=[
            AgentCondition(
                field="preferences.preferred_themes",
                operator="not_empty",
                value=None,
                reason="Theme tilts benefit from alternative solvers",
            ),
        ],
    ),
    AgentDefinition(
        id="rebalance_planner",
        name="Rebalance Planner Agent",
        short_name="Rebalance",
        category="optimization",
        description="Plans trade execution for rebalancing",
        default_include=False,
        priority=55,
        include_conditions=[
            AgentCondition(
                field="constraints.rebalancing_frequency",
                operator="in",
                value=["monthly", "quarterly"],
                reason="Frequent rebalancing requires trade planning",
            ),
        ],
    ),
    AgentDefinition(
        id="liquidity_tc_agent",
        name="Liquidity & Transaction Cost Agent",
        short_name="Liquidity",
        category="risk",
        description="Analyzes liquidity and transaction costs",
        default_include=False,
        priority=35,
        include_conditions=[
            AgentCondition(
                field="constraints.rebalancing_frequency",
                operator="in",
                value=["monthly", "quarterly"],
                reason="Frequent rebalancing requires TC analysis",
            ),
            AgentCondition(
                field="investor_profile.portfolio_value",
                operator="gte",
                value=5_000_000,
                reason="Large portfolios need liquidity analysis",
            ),
        ],
    ),
    AgentDefinition(
        id="esg_screening_agent",
        name="ESG Screening Agent",
        short_name="ESG",
        category="compliance",
        description="Screens for ESG compliance and scores",
        default_include=False,
        priority=25,
        include_conditions=[
            AgentCondition(
                field="preferences.esg_focus",
                operator="eq",
                value=True,
                reason="ESG focus enabled in policy",
            ),
        ],
    ),
    AgentDefinition(
        id="scenario_stress_agent",
        name="Scenario Stress Agent",
        short_name="Stress",
        category="risk",
        description="Runs stress test scenarios",
        default_include=True,
        priority=60,
        exclude_conditions=[
            AgentCondition(
                field="risk_appetite.risk_tolerance",
                operator="in",
                value=["moderate", "aggressive"],
                reason="Not required for moderate/aggressive long-term profiles",
            ),
        ],
    ),
    AgentDefinition(
        id="hedge_tail_agent",
        name="Hedge Tail Agent",
        short_name="Hedge",
        category="risk",
        description="Recommends tail risk hedging strategies",
        default_include=False,
        priority=65,
        include_conditions=[
            AgentCondition(
                field="risk_appetite.risk_tolerance",
                operator="eq",
                value="conservative",
                reason="Conservative profiles benefit from tail hedging",
            ),
        ],
        exclude_conditions=[
            AgentCondition(
                field="risk_appetite.risk_tolerance",
                operator="in",
                value=["moderate", "aggressive"],
                reason="Tail hedging not required for risk-tolerant profiles",
            ),
        ],
    ),
    AgentDefinition(
        id="red_team_agent",
        name="Red Team Agent",
        short_name="RedTeam",
        category="compliance",
        description="Adversarial testing of portfolio robustness",
        default_include=False,
        priority=70,
        include_conditions=[
            AgentCondition(
                field="risk_appetite.risk_tolerance",
                operator="eq",
                value="aggressive",
                reason="Aggressive portfolios need adversarial testing",
            ),
            AgentCondition(
                field="investor_profile.portfolio_value",
                operator="gte",
                value=10_000_000,
                reason="Large portfolios warrant red team testing",
            ),
        ],
        exclude_conditions=[
            AgentCondition(
                field="risk_appetite.risk_tolerance",
                operator="in",
                value=["conservative", "moderate"],
                reason="Red team testing not required for conservative/moderate profiles",
            ),
        ],
    ),
    AgentDefinition(
        id="tax_optimizer_agent",
        name="Tax Optimizer Agent",
        short_name="Tax",
        category="optimization",
        description="Optimizes for tax efficiency",
        default_include=False,
        priority=56,
        include_conditions=[
            AgentCondition(
                field="preferences.tax_aware",
                operator="eq",
                value=True,
                reason="Tax-aware optimization requested",
            ),
        ],
    ),
]


def get_agent_registry() -> List[AgentDefinition]:
    """Get the full agent registry."""
    return AGENT_REGISTRY


def get_agent_by_id(agent_id: str) -> Optional[AgentDefinition]:
    """Get an agent definition by ID."""
    for agent in AGENT_REGISTRY:
        if agent.id == agent_id:
            return agent
    return None


def _get_nested_value(obj: Any, path: str) -> Any:
    """Get a nested value from an object using dot notation."""
    parts = path.split(".")
    current = obj

    for part in parts:
        if hasattr(current, part):
            current = getattr(current, part)
        elif isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None

    return current


def _evaluate_condition(policy: InvestorPolicyStatement, condition: AgentCondition) -> bool:
    """Evaluate a single condition against the policy."""
    value = _get_nested_value(policy, condition.field)

    if condition.operator == "eq":
        return value == condition.value
    elif condition.operator == "ne":
        return value != condition.value
    elif condition.operator == "gt":
        return value is not None and value > condition.value
    elif condition.operator == "lt":
        return value is not None and value < condition.value
    elif condition.operator == "gte":
        return value is not None and value >= condition.value
    elif condition.operator == "lte":
        return value is not None and value <= condition.value
    elif condition.operator == "in":
        return value in condition.value
    elif condition.operator == "not_in":
        return value not in condition.value
    elif condition.operator == "contains":
        return condition.value in (value or [])
    elif condition.operator == "not_empty":
        return value is not None and len(value) > 0
    elif condition.operator == "empty":
        return value is None or len(value) == 0

    return False


class AgentSelectionResult(BaseModel):
    """Result of agent selection process."""
    agent_id: str
    agent_name: str
    short_name: str
    category: str
    included: bool
    reason: str
    conditions_evaluated: List[str]
    priority: int


def select_agents_for_policy(
    policy: InvestorPolicyStatement
) -> tuple[List[AgentSelectionResult], List[AgentSelectionResult]]:
    """
    Select which agents to include/exclude based on the policy.

    Returns:
        Tuple of (included_agents, excluded_agents) with reasons
    """
    included = []
    excluded = []

    for agent in AGENT_REGISTRY:
        conditions_evaluated = []
        should_include = agent.default_include
        reason = "Default inclusion" if should_include else "Default exclusion"

        # Check exclusion conditions first (any true = exclude)
        for condition in agent.exclude_conditions:
            conditions_evaluated.append(f"exclude:{condition.field}")
            if _evaluate_condition(policy, condition):
                should_include = False
                reason = condition.reason
                break

        # If not excluded, check inclusion conditions (all must be true)
        if should_include or agent.include_conditions:
            inclusion_met = True
            for condition in agent.include_conditions:
                conditions_evaluated.append(f"include:{condition.field}")
                if _evaluate_condition(policy, condition):
                    should_include = True
                    reason = condition.reason
                else:
                    inclusion_met = False

            # For conditional agents, only include if at least one condition is met
            if agent.include_conditions and not any(
                _evaluate_condition(policy, c) for c in agent.include_conditions
            ):
                should_include = False
                reason = f"No inclusion conditions met for {agent.name}"

        result = AgentSelectionResult(
            agent_id=agent.id,
            agent_name=agent.name,
            short_name=agent.short_name,
            category=agent.category,
            included=should_include,
            reason=reason,
            conditions_evaluated=conditions_evaluated,
            priority=agent.priority,
        )

        if should_include:
            included.append(result)
        else:
            excluded.append(result)

    # Sort included by priority
    included.sort(key=lambda x: x.priority)

    return included, excluded

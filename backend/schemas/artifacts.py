"""
Artifact schemas for IC Autopilot workflow.
All artifacts include data classification, lineage tracking, and audit metadata.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, computed_field
import hashlib
import json


class DataClassification(str, Enum):
    """Data classification levels for artifacts."""
    PUBLIC = "public"
    DERIVED = "derived"
    RESTRICTED = "restricted"


class ArtifactBase(BaseModel):
    """
    Base class for all workflow artifacts.
    Includes lineage, classification, and audit metadata.
    """
    # Lineage
    artifact_id: str = Field(description="Unique artifact identifier")
    artifact_type: str = Field(description="Type of artifact")
    version: int = Field(default=1, description="Artifact version")
    parent_hashes: List[str] = Field(default_factory=list, description="Hashes of parent artifacts")

    # Classification
    data_classification: DataClassification = Field(default=DataClassification.DERIVED)
    pii: bool = Field(default=False, description="Contains PII flag")
    sources: List[str] = Field(default_factory=list, description="Data sources used")

    # Audit
    producer: str = Field(description="Agent/executor that produced this artifact")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    run_id: str = Field(description="Associated workflow run ID")
    stage_id: str = Field(description="Stage that produced this artifact")

    @computed_field
    @property
    def artifact_hash(self) -> str:
        """Compute deterministic hash of artifact content."""
        content = self.model_dump(exclude={"artifact_hash", "created_at"})
        content_str = json.dumps(content, sort_keys=True, default=str)
        return hashlib.sha256(content_str.encode()).hexdigest()[:16]


class MandateDSL(ArtifactBase):
    """
    Investment mandate specification in structured DSL format.
    Defines constraints, objectives, and risk parameters.
    """
    artifact_type: str = Field(default="mandate_dsl")

    # Mandate definition
    mandate_name: str = Field(description="Human-readable mandate name")
    mandate_id: str = Field(description="Unique mandate identifier")

    # Investment objectives
    primary_objective: str = Field(description="Primary investment objective (e.g., growth, income, preservation)")
    secondary_objectives: List[str] = Field(default_factory=list)
    benchmark: Optional[str] = Field(default=None, description="Benchmark index")

    # Risk parameters
    risk_budget: float = Field(ge=0, le=1, description="Risk budget as fraction")
    max_drawdown: float = Field(ge=0, le=1, description="Maximum acceptable drawdown")
    volatility_target: Optional[float] = Field(default=None, description="Target volatility")

    # Asset allocation constraints
    min_equity: float = Field(ge=0, le=1, default=0)
    max_equity: float = Field(ge=0, le=1, default=1)
    min_fixed_income: float = Field(ge=0, le=1, default=0)
    max_fixed_income: float = Field(ge=0, le=1, default=1)
    min_alternatives: float = Field(ge=0, le=1, default=0)
    max_alternatives: float = Field(ge=0, le=1, default=0.2)

    # Concentration limits
    max_single_position: float = Field(ge=0, le=1, default=0.10, description="Max single position size")
    max_sector_exposure: float = Field(ge=0, le=1, default=0.25, description="Max sector exposure")
    max_country_exposure: float = Field(ge=0, le=1, default=0.40, description="Max country exposure")

    # Liquidity requirements
    min_liquidity_ratio: float = Field(ge=0, le=1, default=0.80, description="Min % in liquid assets")

    # ESG constraints
    esg_exclusions: List[str] = Field(default_factory=list, description="Excluded sectors/companies")
    min_esg_score: Optional[float] = Field(default=None, description="Minimum ESG score")


class FundInfo(BaseModel):
    """Information about a single fund in the universe."""
    accession_number: str
    series_name: str
    series_id: str
    manager_name: str
    total_assets: float
    net_assets: float
    primary_asset_class: str
    holding_count: int
    equity_pct: float
    fixed_income_pct: float
    cash_pct: float
    other_pct: float


class Universe(ArtifactBase):
    """
    Investment universe - filtered set of eligible funds/securities.
    """
    artifact_type: str = Field(default="universe")

    # Universe definition
    universe_name: str = Field(description="Universe name/description")
    filter_criteria: Dict[str, Any] = Field(description="Filters applied to create universe")

    # Contents
    funds: List[FundInfo] = Field(default_factory=list, description="Funds in universe")
    total_fund_count: int = Field(default=0)
    total_aum: float = Field(default=0, description="Total AUM in universe")

    # Statistics
    asset_class_breakdown: Dict[str, float] = Field(default_factory=dict)
    manager_breakdown: Dict[str, int] = Field(default_factory=dict)


class FundFeatures(ArtifactBase):
    """
    Computed features for a fund - used for optimization and analysis.
    """
    artifact_type: str = Field(default="fund_features")

    # Fund reference
    accession_number: str
    series_name: str

    # Return features
    monthly_return_1: Optional[float] = None
    monthly_return_2: Optional[float] = None
    monthly_return_3: Optional[float] = None
    annualized_return: Optional[float] = None

    # Risk features
    volatility: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    max_drawdown: Optional[float] = None
    beta: Optional[float] = None

    # Allocation features
    equity_exposure: float = 0
    fixed_income_exposure: float = 0
    cash_exposure: float = 0
    alternative_exposure: float = 0

    # Concentration features
    top_10_concentration: float = 0
    sector_hhi: float = 0  # Herfindahl-Hirschman Index

    # Quality features
    avg_credit_rating: Optional[str] = None
    avg_duration: Optional[float] = None

    # Liquidity features
    avg_daily_volume: Optional[float] = None
    liquidity_score: float = 0.5


class HoldingAllocation(BaseModel):
    """Single holding in a portfolio candidate."""
    fund_accession: str
    fund_name: str
    weight: float = Field(ge=0, le=1)
    expected_contribution: float = 0


class PortfolioCandidate(ArtifactBase):
    """
    A candidate portfolio generated by the solver.
    Multiple candidates (A/B/C) are generated with enforced diversity.
    """
    artifact_type: str = Field(default="portfolio_candidate")

    # Candidate identification
    candidate_id: str = Field(description="Candidate identifier (A, B, C)")
    solver_config: str = Field(description="Solver configuration used")
    diversity_seed: int = Field(description="Random seed for diversity")

    # Holdings
    holdings: List[HoldingAllocation] = Field(default_factory=list)
    total_positions: int = 0

    # Expected metrics
    expected_return: float = 0
    expected_volatility: float = 0
    expected_sharpe: float = 0

    # Constraint satisfaction
    equity_allocation: float = 0
    fixed_income_allocation: float = 0
    cash_allocation: float = 0
    max_position_size: float = 0

    # Optimization metadata
    optimization_score: float = 0
    constraint_violations: List[str] = Field(default_factory=list)
    solver_iterations: int = 0
    solver_time_ms: int = 0


class ComplianceRule(BaseModel):
    """Individual compliance rule check result."""
    rule_id: str
    rule_name: str
    rule_category: str  # concentration, liquidity, esg, regulatory
    passed: bool
    actual_value: float
    limit_value: float
    message: str


class ComplianceReport(ArtifactBase):
    """
    Compliance verification report for a portfolio candidate.
    Deterministic rule-based checks.
    """
    artifact_type: str = Field(default="compliance_report")

    # Reference
    candidate_id: str

    # Results
    passed: bool = False
    rules_checked: int = 0
    rules_passed: int = 0
    rules_failed: int = 0

    # Detail
    rule_results: List[ComplianceRule] = Field(default_factory=list)

    # Critical failures
    critical_failures: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class ScenarioResult(BaseModel):
    """Result of a single stress scenario."""
    scenario_id: str
    scenario_name: str
    scenario_type: str  # historical, synthetic, adversarial
    description: str

    # Impact
    portfolio_return: float
    portfolio_drawdown: float
    var_breach: bool

    # Severity
    severity: str  # low, medium, high, critical
    passed: bool


class RedTeamReport(ArtifactBase):
    """
    Adversarial scenario search report.
    Attempts to find scenarios that break the portfolio.
    """
    artifact_type: str = Field(default="redteam_report")

    # Reference
    candidate_id: str

    # Search parameters
    seed: int = Field(description="Random seed for reproducibility")
    scenarios_tested: int = 0
    search_budget: int = 100

    # Results
    passed: bool = False
    worst_scenario: Optional[ScenarioResult] = None
    scenario_results: List[ScenarioResult] = Field(default_factory=list)

    # Metrics
    avg_drawdown: float = 0
    max_drawdown: float = 0
    var_95: float = 0
    cvar_95: float = 0

    # Breaking scenarios
    breaking_scenarios: List[str] = Field(default_factory=list)


class Decision(ArtifactBase):
    """
    Final selection decision with scoring and rationale.
    """
    artifact_type: str = Field(default="decision")

    # Winner
    selected_candidate: str = Field(description="Selected candidate ID (A, B, C)")
    selection_rationale: str = Field(description="Human-readable rationale")

    # Scoring
    candidate_scores: Dict[str, float] = Field(default_factory=dict)
    scoring_weights: Dict[str, float] = Field(default_factory=dict)

    # Comparison
    candidate_comparison: Dict[str, Dict[str, Any]] = Field(default_factory=dict)

    # Rejection reasons
    rejected_candidates: Dict[str, str] = Field(default_factory=dict)


class Trade(BaseModel):
    """Individual trade in rebalance plan."""
    fund_accession: str
    fund_name: str
    action: str  # BUY, SELL, HOLD
    current_weight: float
    target_weight: float
    trade_weight: float
    estimated_cost: float = 0


class RebalancePlan(ArtifactBase):
    """
    Rebalancing plan with trade list and execution guidance.
    """
    artifact_type: str = Field(default="rebalance_plan")

    # Reference
    candidate_id: str

    # Trades
    trades: List[Trade] = Field(default_factory=list)
    total_buys: int = 0
    total_sells: int = 0
    total_holds: int = 0

    # Cost estimates
    total_turnover: float = 0
    estimated_transaction_cost: float = 0
    estimated_market_impact: float = 0

    # Execution guidance
    execution_priority: List[str] = Field(default_factory=list)
    liquidity_warnings: List[str] = Field(default_factory=list)


class ICMemo(ArtifactBase):
    """
    Investment Committee Memo - final recommendation document.
    """
    artifact_type: str = Field(default="ic_memo")

    # Header
    memo_date: datetime = Field(default_factory=datetime.utcnow)
    memo_title: str
    prepared_by: str = "IC Autopilot"

    # Executive summary
    executive_summary: str
    recommendation: str

    # Sections
    mandate_summary: str
    market_context: str
    portfolio_overview: str
    risk_analysis: str
    compliance_summary: str
    implementation_plan: str

    # Appendix references
    appendix_refs: List[str] = Field(default_factory=list)


class RiskAppendix(ArtifactBase):
    """
    Risk appendix with detailed risk analytics.
    """
    artifact_type: str = Field(default="risk_appendix")

    # Reference
    candidate_id: str

    # Risk metrics
    var_95_1d: float = 0
    var_99_1d: float = 0
    cvar_95_1d: float = 0
    expected_shortfall: float = 0

    # Factor exposures
    factor_exposures: Dict[str, float] = Field(default_factory=dict)

    # Stress test results
    stress_test_results: Dict[str, float] = Field(default_factory=dict)

    # Concentration metrics
    position_hhi: float = 0
    sector_hhi: float = 0
    geography_hhi: float = 0

    # Liquidity metrics
    liquidity_coverage_ratio: float = 0
    days_to_liquidate_95: float = 0


class AuditEvent(ArtifactBase):
    """
    Immutable audit event for compliance and traceability.
    """
    artifact_type: str = Field(default="audit_event")

    # Event info
    event_id: str
    event_type: str
    event_timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Context
    actor: str  # agent/executor/user that triggered
    action: str
    target: Optional[str] = None

    # Details
    details: Dict[str, Any] = Field(default_factory=dict)

    # Outcome
    outcome: str  # success, failure, skipped
    error_message: Optional[str] = None

"""
Load Mandate Template Executor - Stage 1
Loads and validates mandate definition from templates or database.
"""

import uuid
from datetime import datetime
import structlog

from schemas.artifacts import MandateDSL, DataClassification
from worker.executors.base import BaseExecutor

logger = structlog.get_logger()

# Default mandate templates
MANDATE_TEMPLATES = {
    "balanced_growth": {
        "mandate_name": "Balanced Growth Fund",
        "primary_objective": "growth",
        "secondary_objectives": ["income", "capital_preservation"],
        "benchmark": "S&P 500 Total Return",
        "risk_budget": 0.15,
        "max_drawdown": 0.20,
        "volatility_target": 0.12,
        "min_equity": 0.40,
        "max_equity": 0.70,
        "min_fixed_income": 0.20,
        "max_fixed_income": 0.50,
        "min_alternatives": 0.0,
        "max_alternatives": 0.15,
        "max_single_position": 0.08,
        "max_sector_exposure": 0.25,
        "max_country_exposure": 0.40,
        "min_liquidity_ratio": 0.85,
        "esg_exclusions": ["tobacco", "weapons", "gambling"],
    },
    "conservative_income": {
        "mandate_name": "Conservative Income Fund",
        "primary_objective": "income",
        "secondary_objectives": ["capital_preservation"],
        "benchmark": "Bloomberg US Aggregate Bond Index",
        "risk_budget": 0.08,
        "max_drawdown": 0.10,
        "volatility_target": 0.06,
        "min_equity": 0.10,
        "max_equity": 0.30,
        "min_fixed_income": 0.50,
        "max_fixed_income": 0.80,
        "min_alternatives": 0.0,
        "max_alternatives": 0.10,
        "max_single_position": 0.05,
        "max_sector_exposure": 0.20,
        "max_country_exposure": 0.30,
        "min_liquidity_ratio": 0.90,
        "esg_exclusions": ["tobacco", "weapons"],
    },
    "aggressive_growth": {
        "mandate_name": "Aggressive Growth Fund",
        "primary_objective": "growth",
        "secondary_objectives": [],
        "benchmark": "Russell 2000 Growth Index",
        "risk_budget": 0.25,
        "max_drawdown": 0.35,
        "volatility_target": 0.20,
        "min_equity": 0.70,
        "max_equity": 1.0,
        "min_fixed_income": 0.0,
        "max_fixed_income": 0.20,
        "min_alternatives": 0.0,
        "max_alternatives": 0.20,
        "max_single_position": 0.10,
        "max_sector_exposure": 0.35,
        "max_country_exposure": 0.50,
        "min_liquidity_ratio": 0.75,
        "esg_exclusions": [],
    },
}


class LoadMandateExecutor(BaseExecutor):
    """
    Stage 1: Load Mandate Template

    Loads a mandate definition that specifies:
    - Investment objectives
    - Risk parameters
    - Asset allocation constraints
    - Concentration limits
    - ESG exclusions
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.stage_id = "load_mandate"

    async def execute(self, mandate_id: str) -> MandateDSL:
        """
        Load mandate template by ID.

        Args:
            mandate_id: Template ID or custom mandate identifier

        Returns:
            MandateDSL artifact
        """
        logger.info("loading_mandate", mandate_id=mandate_id)

        await self.emit_progress(f"Loading mandate template: {mandate_id}")

        # Check if it's a built-in template
        if mandate_id in MANDATE_TEMPLATES:
            template = MANDATE_TEMPLATES[mandate_id]
        else:
            # Default to balanced_growth
            logger.warning("mandate_not_found", mandate_id=mandate_id, using="balanced_growth")
            template = MANDATE_TEMPLATES["balanced_growth"]
            mandate_id = "balanced_growth"

        # Create MandateDSL artifact
        mandate = MandateDSL(
            artifact_id=f"mandate-{uuid.uuid4().hex[:8]}",
            run_id=self.run_id,
            stage_id=self.stage_id,
            producer=self.executor_name,
            data_classification=DataClassification.DERIVED,
            sources=["mandate_templates"],
            mandate_id=mandate_id,
            **template,
        )

        # Save artifact
        await self.save_artifact(mandate)

        logger.info("mandate_loaded", mandate_id=mandate_id, mandate_name=mandate.mandate_name)

        return mandate

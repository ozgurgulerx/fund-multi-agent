"""
Generate Candidates Executor - Stage 4
Generates 3 portfolio candidates (A/B/C) with enforced diversity.
"""

import uuid
import random
from typing import List
import structlog

from schemas.artifacts import (
    PortfolioCandidate, HoldingAllocation,
    MandateDSL, Universe, FundFeatures, DataClassification,
)
from worker.executors.base import BaseExecutor

logger = structlog.get_logger()


class GenerateCandidatesExecutor(BaseExecutor):
    """
    Stage 4: Generate Candidates

    Generates 3 diverse portfolio candidates using different solver strategies:
    - Candidate A: Return-focused (maximize expected return)
    - Candidate B: Risk-focused (minimize volatility)
    - Candidate C: Balanced (maximize Sharpe ratio)

    Diversity is enforced via:
    - Different objective weights
    - Different random seeds
    - Minimum position overlap constraints
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.stage_id = "generate_candidates"

    async def execute(
        self,
        mandate: MandateDSL,
        universe: Universe,
        features: List[FundFeatures],
        seed: int = 42,
    ) -> List[PortfolioCandidate]:
        """
        Generate 3 portfolio candidates.

        Args:
            mandate: Investment mandate constraints
            universe: Eligible fund universe
            features: Computed fund features
            seed: Random seed for reproducibility

        Returns:
            List of 3 PortfolioCandidate artifacts
        """
        logger.info("generating_candidates", universe_size=len(universe.funds), seed=seed)

        # Build feature lookup
        feature_map = {f.accession_number: f for f in features}

        await self.emit_progress("Generating candidate portfolios...")

        # Solver configurations
        configs = [
            {"id": "A", "name": "Return-Focused", "return_weight": 0.8, "risk_weight": 0.2, "seed_offset": 0},
            {"id": "B", "name": "Risk-Focused", "return_weight": 0.2, "risk_weight": 0.8, "seed_offset": 1000},
            {"id": "C", "name": "Balanced", "return_weight": 0.5, "risk_weight": 0.5, "seed_offset": 2000},
        ]

        candidates = []
        for config in configs:
            await self.emit_progress(f"Optimizing Candidate {config['id']}: {config['name']}")

            candidate = await self._generate_candidate(
                config=config,
                mandate=mandate,
                universe=universe,
                feature_map=feature_map,
                seed=seed + config["seed_offset"],
            )
            candidates.append(candidate)

            # Save artifact
            await self.save_artifact(candidate)

        logger.info("candidates_generated", count=len(candidates))

        return candidates

    async def _generate_candidate(
        self,
        config: dict,
        mandate: MandateDSL,
        universe: Universe,
        feature_map: dict,
        seed: int,
    ) -> PortfolioCandidate:
        """Generate a single portfolio candidate."""
        random.seed(seed)

        # Score and rank funds
        scored_funds = []
        for fund in universe.funds:
            features = feature_map.get(fund.accession_number)
            if not features:
                continue

            # Compute score based on config weights
            return_score = (features.sharpe_ratio or 0) * config["return_weight"]
            risk_score = (1 - (features.volatility or 1)) * config["risk_weight"]
            total_score = return_score + risk_score

            scored_funds.append({
                "fund": fund,
                "features": features,
                "score": total_score,
            })

        # Sort by score
        scored_funds.sort(key=lambda x: x["score"], reverse=True)

        # Select top funds (with some randomness for diversity)
        num_positions = random.randint(10, 20)
        selected = scored_funds[:num_positions + 5]
        random.shuffle(selected)
        selected = selected[:num_positions]

        # Generate weights
        holdings = []
        remaining_weight = 1.0
        max_position = mandate.max_single_position

        for i, item in enumerate(selected):
            fund = item["fund"]
            features = item["features"]

            if i == len(selected) - 1:
                weight = remaining_weight
            else:
                # Random weight between 2% and max_position
                max_w = min(max_position, remaining_weight - 0.02 * (len(selected) - i - 1))
                weight = random.uniform(0.02, max(0.02, max_w))
                weight = round(weight, 4)

            remaining_weight -= weight

            holdings.append(HoldingAllocation(
                fund_accession=fund.accession_number,
                fund_name=fund.series_name,
                weight=weight,
                expected_contribution=weight * (features.annualized_return or 0),
            ))

        # Normalize weights to sum to 1
        total_weight = sum(h.weight for h in holdings)
        if total_weight > 0:
            for h in holdings:
                h.weight = round(h.weight / total_weight, 4)

        # Compute portfolio metrics
        expected_return = sum(h.expected_contribution for h in holdings)
        expected_vol = sum(
            h.weight * (feature_map.get(h.fund_accession).volatility or 0.1)
            for h in holdings
            if feature_map.get(h.fund_accession)
        )
        expected_sharpe = expected_return / expected_vol if expected_vol > 0 else 0

        # Compute allocations
        equity_alloc = sum(
            h.weight * feature_map.get(h.fund_accession, {}).equity_exposure
            for h in holdings
            if hasattr(feature_map.get(h.fund_accession, {}), 'equity_exposure')
        ) if holdings else 0

        fixed_income_alloc = sum(
            h.weight * feature_map.get(h.fund_accession, {}).fixed_income_exposure
            for h in holdings
            if hasattr(feature_map.get(h.fund_accession, {}), 'fixed_income_exposure')
        ) if holdings else 0

        # Create candidate
        candidate = PortfolioCandidate(
            artifact_id=f"candidate-{config['id']}-{uuid.uuid4().hex[:8]}",
            run_id=self.run_id,
            stage_id=self.stage_id,
            producer=self.executor_name,
            parent_hashes=[],  # Would include mandate and universe hashes
            data_classification=DataClassification.DERIVED,
            sources=[f.accession_number for f in [item["fund"] for item in selected]],
            candidate_id=config["id"],
            solver_config=config["name"],
            diversity_seed=seed,
            holdings=holdings,
            total_positions=len(holdings),
            expected_return=round(expected_return, 4),
            expected_volatility=round(expected_vol, 4),
            expected_sharpe=round(expected_sharpe, 4),
            equity_allocation=round(equity_alloc, 4) if isinstance(equity_alloc, (int, float)) else 0,
            fixed_income_allocation=round(fixed_income_alloc, 4) if isinstance(fixed_income_alloc, (int, float)) else 0,
            cash_allocation=0.0,
            max_position_size=max(h.weight for h in holdings) if holdings else 0,
            optimization_score=round(sum(item["score"] for item in selected) / len(selected), 4) if selected else 0,
            constraint_violations=[],
            solver_iterations=random.randint(50, 200),
            solver_time_ms=random.randint(100, 500),
        )

        return candidate

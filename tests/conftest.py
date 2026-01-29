"""
Pytest configuration and fixtures for IC Autopilot tests.
"""

import asyncio
import pytest
from datetime import datetime
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

# Add backend to path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).parent.parent / "worker"))


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_run_id() -> str:
    """Generate a sample run ID."""
    return "run-test-12345678"


@pytest.fixture
def sample_mandate_id() -> str:
    """Sample mandate ID."""
    return "balanced-growth-2024"


@pytest.fixture
def sample_config() -> dict:
    """Sample run configuration."""
    return {
        "max_holdings": 50,
        "min_position_size": 0.01,
        "max_position_size": 0.10,
        "rebalance_threshold": 0.05,
    }


@pytest.fixture
def mock_event_bus() -> AsyncMock:
    """Mock event bus for testing without Redis."""
    bus = AsyncMock()
    bus.publish = AsyncMock()
    bus.subscribe = AsyncMock(return_value=AsyncMock())
    return bus


@pytest.fixture
def mock_artifact_store() -> AsyncMock:
    """Mock artifact store for testing without Azure Blob."""
    store = AsyncMock()
    store.save = AsyncMock()
    store.load = AsyncMock(return_value=None)
    store.list_artifacts = AsyncMock(return_value={})
    return store


@pytest.fixture
def mock_run_store() -> AsyncMock:
    """Mock run store for testing without PostgreSQL."""
    store = AsyncMock()
    store.create_run = AsyncMock()
    store.get_run = AsyncMock(return_value=None)
    store.update_run_status = AsyncMock()
    store.update_stage = AsyncMock()
    return store


@pytest.fixture
def sample_fund_data() -> list[dict]:
    """Sample fund data for testing."""
    return [
        {
            "accession_number": "0001234567-24-000001",
            "series_name": "Growth Fund A",
            "total_assets": 1_000_000_000.0,
            "net_assets": 950_000_000.0,
            "series_id": "S000001",
        },
        {
            "accession_number": "0001234567-24-000002",
            "series_name": "Income Fund B",
            "total_assets": 500_000_000.0,
            "net_assets": 480_000_000.0,
            "series_id": "S000002",
        },
        {
            "accession_number": "0001234567-24-000003",
            "series_name": "Balanced Fund C",
            "total_assets": 750_000_000.0,
            "net_assets": 720_000_000.0,
            "series_id": "S000003",
        },
    ]


@pytest.fixture
def sample_universe_artifact():
    """Sample universe artifact."""
    from schemas.artifacts import UniverseArtifact

    return UniverseArtifact(
        run_id="run-test-12345678",
        stage_id="build_universe",
        producer="universe_executor",
        filters_applied=["min_assets > 100M", "asset_class = equity"],
        total_candidates=100,
        funds=[
            {
                "fund_id": "FUND001",
                "name": "Test Fund 1",
                "total_assets": 500_000_000.0,
            }
        ],
    )


@pytest.fixture
def sample_mandate_artifact():
    """Sample mandate artifact."""
    from schemas.artifacts import MandateDSL

    return MandateDSL(
        run_id="run-test-12345678",
        stage_id="load_mandate",
        producer="mandate_executor",
        mandate_id="balanced-growth-2024",
        mandate_version="1.0",
        objective="Maximize risk-adjusted returns",
        constraints={
            "max_holdings": 50,
            "min_position_size": 0.01,
            "max_position_size": 0.10,
        },
        risk_limits={
            "max_volatility": 0.15,
            "max_drawdown": 0.20,
        },
        benchmark="S&P 500",
    )

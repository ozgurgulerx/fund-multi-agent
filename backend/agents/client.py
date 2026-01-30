"""
Shared Azure OpenAI chat client factory for Agent Framework agents.
Uses DefaultAzureCredential for Azure-native authentication.

Supports separate model deployments for:
- Agents: AZURE_OPENAI_AGENT_DEPLOYMENT (default: gpt-5-nano)
- Orchestrator: AZURE_OPENAI_ORCHESTRATOR_DEPLOYMENT (default: gpt-5-mini)
"""

import os
from functools import lru_cache
from typing import Literal, Optional

from azure.identity import DefaultAzureCredential, AzureCliCredential
from agent_framework.azure import AzureOpenAIChatClient
import structlog

logger = structlog.get_logger()

# Configuration from environment
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY", "")

# Separate deployments for agents vs orchestrator
# Agents use lighter model for individual tasks
AZURE_OPENAI_AGENT_DEPLOYMENT = os.getenv("AZURE_OPENAI_AGENT_DEPLOYMENT", "gpt-5-nano")
# Orchestrator uses more capable model for planning and coordination
AZURE_OPENAI_ORCHESTRATOR_DEPLOYMENT = os.getenv("AZURE_OPENAI_ORCHESTRATOR_DEPLOYMENT", "gpt-5-mini")

# Legacy fallback (for backward compatibility)
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", AZURE_OPENAI_AGENT_DEPLOYMENT)


def get_credential():
    """
    Get Azure credential for authentication.

    Tries DefaultAzureCredential first (works with managed identity, Azure CLI, etc.)
    Falls back to API key if DefaultAzureCredential fails and AZURE_OPENAI_KEY is set.
    """
    try:
        # Try DefaultAzureCredential first (managed identity, Azure CLI, etc.)
        credential = DefaultAzureCredential()
        logger.info("azure_credential_initialized", method="DefaultAzureCredential")
        return credential
    except Exception as e:
        logger.warning(
            "default_credential_failed",
            error=str(e),
            fallback="AzureCliCredential"
        )
        try:
            # Fall back to Azure CLI credential
            credential = AzureCliCredential()
            logger.info("azure_credential_initialized", method="AzureCliCredential")
            return credential
        except Exception as e2:
            logger.warning(
                "cli_credential_failed",
                error=str(e2),
            )
            return None


def get_chat_client(
    endpoint: Optional[str] = None,
    deployment: Optional[str] = None,
    api_version: Optional[str] = None,
    role: Literal["agent", "orchestrator"] = "agent",
) -> AzureOpenAIChatClient:
    """
    Factory for Azure OpenAI chat client.

    Args:
        endpoint: Azure OpenAI endpoint URL (uses env var if not provided)
        deployment: Model deployment name (uses env var if not provided)
        api_version: API version (uses env var if not provided)
        role: "agent" for individual agents (gpt-5-nano),
              "orchestrator" for orchestrator/manager (gpt-5-mini)

    Returns:
        Configured AzureOpenAIChatClient instance
    """
    _endpoint = endpoint or AZURE_OPENAI_ENDPOINT

    # Select deployment based on role
    if deployment:
        _deployment = deployment
    elif role == "orchestrator":
        _deployment = AZURE_OPENAI_ORCHESTRATOR_DEPLOYMENT
    else:
        _deployment = AZURE_OPENAI_AGENT_DEPLOYMENT

    _api_version = api_version or AZURE_OPENAI_API_VERSION

    if not _endpoint:
        raise ValueError(
            "Azure OpenAI endpoint not configured. "
            "Set AZURE_OPENAI_ENDPOINT environment variable."
        )

    credential = get_credential()

    if credential:
        # Use credential-based authentication
        client = AzureOpenAIChatClient(
            endpoint=_endpoint,
            credential=credential,
            deployment_name=_deployment,
            api_version=_api_version,
        )
        logger.info(
            "chat_client_created",
            endpoint=_endpoint,
            deployment=_deployment,
            auth="credential",
        )
    elif AZURE_OPENAI_KEY:
        # Fall back to API key authentication
        client = AzureOpenAIChatClient(
            endpoint=_endpoint,
            api_key=AZURE_OPENAI_KEY,
            deployment_name=_deployment,
            api_version=_api_version,
        )
        logger.info(
            "chat_client_created",
            endpoint=_endpoint,
            deployment=_deployment,
            auth="api_key",
        )
    else:
        raise ValueError(
            "No Azure authentication available. "
            "Set up DefaultAzureCredential or AZURE_OPENAI_KEY."
        )

    return client


@lru_cache(maxsize=1)
def get_shared_chat_client() -> AzureOpenAIChatClient:
    """
    Get a cached shared chat client instance for agents.

    Use this when you want to reuse the same client across multiple agents
    to reduce connection overhead. Note: This is cached, so configuration
    changes require a restart.

    Uses gpt-5-nano (agent deployment).
    """
    return get_chat_client(role="agent")


@lru_cache(maxsize=1)
def get_orchestrator_chat_client() -> AzureOpenAIChatClient:
    """
    Get a cached chat client for orchestrator/manager agents.

    Uses gpt-5-mini (orchestrator deployment) - more capable model
    for planning and coordination tasks.
    """
    return get_chat_client(role="orchestrator")


def get_deployment_info() -> dict:
    """Get current deployment configuration info (for debugging/logging)."""
    return {
        "agent_deployment": AZURE_OPENAI_AGENT_DEPLOYMENT,
        "orchestrator_deployment": AZURE_OPENAI_ORCHESTRATOR_DEPLOYMENT,
        "endpoint": AZURE_OPENAI_ENDPOINT[:50] + "..." if len(AZURE_OPENAI_ENDPOINT) > 50 else AZURE_OPENAI_ENDPOINT,
        "api_version": AZURE_OPENAI_API_VERSION,
    }

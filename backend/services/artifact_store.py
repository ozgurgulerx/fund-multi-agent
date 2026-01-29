"""
Azure Blob Storage-based artifact store for workflow artifacts.
Stores typed, hashed artifacts with full lineage tracking.
"""

import json
import os
from datetime import datetime
from typing import Optional, Type, TypeVar
import structlog
from azure.identity import DefaultAzureCredential
from azure.storage.blob.aio import BlobServiceClient, ContainerClient
from pydantic import BaseModel

from schemas.artifacts import ArtifactBase

logger = structlog.get_logger()

# Configuration
STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
STORAGE_ACCOUNT_NAME = os.getenv("AZURE_STORAGE_ACCOUNT_NAME", "icautopilotstore")
CONTAINER_NAME = os.getenv("ARTIFACT_CONTAINER_NAME", "ic-artifacts")

T = TypeVar("T", bound=ArtifactBase)


class ArtifactStore:
    """
    Azure Blob Storage-based artifact store.

    Storage structure:
        runs/{run_id}/artifacts/{artifact_type}/{version}.json
        runs/{run_id}/artifacts/{artifact_type}/latest.json (symlink/copy)

    Features:
    - Typed artifact storage with Pydantic validation
    - Versioned artifacts with hash verification
    - Lineage tracking via parent_hashes
    - Fast latest artifact lookup
    """

    def __init__(self, container_client: ContainerClient):
        self.container = container_client

    @classmethod
    async def create(cls) -> "ArtifactStore":
        """Factory method to create ArtifactStore with connection."""
        if STORAGE_CONNECTION_STRING:
            blob_service = BlobServiceClient.from_connection_string(STORAGE_CONNECTION_STRING)
        else:
            # Use managed identity
            credential = DefaultAzureCredential()
            blob_service = BlobServiceClient(
                account_url=f"https://{STORAGE_ACCOUNT_NAME}.blob.core.windows.net",
                credential=credential,
            )

        container = blob_service.get_container_client(CONTAINER_NAME)

        # Create container if not exists
        try:
            await container.create_container()
            logger.info("artifact_container_created", container=CONTAINER_NAME)
        except Exception:
            # Container already exists
            pass

        logger.info("artifact_store_connected", container=CONTAINER_NAME)
        return cls(container)

    def _artifact_path(self, run_id: str, artifact_type: str, version: int) -> str:
        """Get blob path for an artifact version."""
        return f"runs/{run_id}/artifacts/{artifact_type}/{version}.json"

    def _latest_path(self, run_id: str, artifact_type: str) -> str:
        """Get blob path for latest artifact."""
        return f"runs/{run_id}/artifacts/{artifact_type}/latest.json"

    async def save(self, artifact: ArtifactBase) -> str:
        """
        Save an artifact to blob storage.

        Args:
            artifact: Artifact to save

        Returns:
            Blob path where artifact was saved
        """
        # Serialize artifact
        artifact_json = artifact.model_dump_json(indent=2)

        # Save versioned artifact
        version_path = self._artifact_path(
            artifact.run_id,
            artifact.artifact_type,
            artifact.version,
        )

        blob_client = self.container.get_blob_client(version_path)
        await blob_client.upload_blob(
            artifact_json,
            overwrite=True,
            metadata={
                "artifact_type": artifact.artifact_type,
                "artifact_id": artifact.artifact_id,
                "artifact_hash": artifact.artifact_hash,
                "producer": artifact.producer,
                "created_at": artifact.created_at.isoformat(),
            },
        )

        # Also save as latest
        latest_path = self._latest_path(artifact.run_id, artifact.artifact_type)
        latest_blob = self.container.get_blob_client(latest_path)
        await latest_blob.upload_blob(artifact_json, overwrite=True)

        logger.info(
            "artifact_saved",
            run_id=artifact.run_id,
            type=artifact.artifact_type,
            version=artifact.version,
            hash=artifact.artifact_hash,
            path=version_path,
        )

        return version_path

    async def load(
        self,
        run_id: str,
        artifact_type: str,
        version: Optional[int] = None,
        model_class: Optional[Type[T]] = None,
    ) -> Optional[T]:
        """
        Load an artifact from blob storage.

        Args:
            run_id: Run ID
            artifact_type: Type of artifact
            version: Specific version (None for latest)
            model_class: Pydantic model class for validation

        Returns:
            Loaded artifact or None if not found
        """
        if version is not None:
            path = self._artifact_path(run_id, artifact_type, version)
        else:
            path = self._latest_path(run_id, artifact_type)

        try:
            blob_client = self.container.get_blob_client(path)
            download = await blob_client.download_blob()
            content = await download.readall()
            data = json.loads(content)

            if model_class:
                return model_class.model_validate(data)
            else:
                return data

        except Exception as e:
            logger.warning(
                "artifact_load_failed",
                run_id=run_id,
                type=artifact_type,
                version=version,
                error=str(e),
            )
            return None

    async def list_versions(self, run_id: str, artifact_type: str) -> list[int]:
        """List all versions of an artifact."""
        prefix = f"runs/{run_id}/artifacts/{artifact_type}/"
        versions = []

        async for blob in self.container.list_blobs(name_starts_with=prefix):
            name = blob.name.split("/")[-1]
            if name != "latest.json" and name.endswith(".json"):
                try:
                    version = int(name.replace(".json", ""))
                    versions.append(version)
                except ValueError:
                    continue

        return sorted(versions)

    async def list_artifacts(self, run_id: str) -> dict[str, int]:
        """
        List all artifact types and their latest versions for a run.

        Returns:
            Dict of artifact_type -> latest_version
        """
        prefix = f"runs/{run_id}/artifacts/"
        artifacts = {}

        async for blob in self.container.list_blobs(name_starts_with=prefix):
            parts = blob.name.split("/")
            if len(parts) >= 5:
                artifact_type = parts[3]
                filename = parts[4]
                if filename != "latest.json" and filename.endswith(".json"):
                    try:
                        version = int(filename.replace(".json", ""))
                        if artifact_type not in artifacts or version > artifacts[artifact_type]:
                            artifacts[artifact_type] = version
                    except ValueError:
                        continue

        return artifacts

    async def delete_run_artifacts(self, run_id: str) -> int:
        """
        Delete all artifacts for a run.

        Returns:
            Number of blobs deleted
        """
        prefix = f"runs/{run_id}/"
        deleted = 0

        async for blob in self.container.list_blobs(name_starts_with=prefix):
            blob_client = self.container.get_blob_client(blob.name)
            await blob_client.delete_blob()
            deleted += 1

        logger.info("run_artifacts_deleted", run_id=run_id, count=deleted)
        return deleted

    async def get_audit_bundle(self, run_id: str) -> dict:
        """
        Get complete artifact bundle for audit purposes.
        Includes all artifacts with hashes for integrity verification.
        """
        artifacts = await self.list_artifacts(run_id)
        bundle = {
            "run_id": run_id,
            "exported_at": datetime.utcnow().isoformat(),
            "artifacts": {},
        }

        for artifact_type, version in artifacts.items():
            artifact = await self.load(run_id, artifact_type, version)
            if artifact:
                bundle["artifacts"][artifact_type] = {
                    "version": version,
                    "data": artifact if isinstance(artifact, dict) else artifact.model_dump(),
                }

        return bundle


# Singleton instance
_artifact_store: Optional[ArtifactStore] = None


async def get_artifact_store() -> ArtifactStore:
    """Get or create the singleton ArtifactStore instance."""
    global _artifact_store
    if _artifact_store is None:
        _artifact_store = await ArtifactStore.create()
    return _artifact_store

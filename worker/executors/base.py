"""
Base executor class for workflow stages.
Provides common functionality for event emission, artifact storage, and tool calling.
"""

import time
from typing import Callable, Dict, Any, Optional
import structlog

from schemas import WorkflowEvent, EventKind, EventLevel
from services.artifact_store import ArtifactStore

logger = structlog.get_logger()


class BaseExecutor:
    """
    Base class for workflow stage executors.

    Provides:
    - Event emission via emit_fn callback
    - Artifact storage via artifact_store
    - Tool call tracking and event emission
    """

    def __init__(
        self,
        run_id: str,
        emit_fn: Callable,
        artifact_store: ArtifactStore,
        stage_id: str = None,
    ):
        self.run_id = run_id
        self.emit = emit_fn
        self.artifact_store = artifact_store
        self.stage_id = stage_id
        self.executor_name = self.__class__.__name__

    async def emit_tool_call(
        self,
        tool_name: str,
        inputs: Dict[str, Any] = None,
    ):
        """Emit tool called event."""
        await self.emit(
            EventKind.TOOL_CALLED,
            f"Tool '{tool_name}' called",
            stage_id=self.stage_id,
            payload={
                "tool": tool_name,
                "executor": self.executor_name,
                "inputs": inputs or {},
            },
        )

    async def emit_tool_completed(
        self,
        tool_name: str,
        duration_ms: int,
        outputs: Dict[str, Any] = None,
    ):
        """Emit tool completed event."""
        await self.emit(
            EventKind.TOOL_COMPLETED,
            f"Tool '{tool_name}' completed in {duration_ms}ms",
            stage_id=self.stage_id,
            duration_ms=duration_ms,
            payload={
                "tool": tool_name,
                "outputs": outputs or {},
            },
        )

    async def emit_progress(
        self,
        message: str,
        progress_pct: float = None,
        payload: Dict[str, Any] = None,
    ):
        """Emit progress update event."""
        await self.emit(
            EventKind.PROGRESS_UPDATE,
            message,
            stage_id=self.stage_id,
            payload={
                "progress_pct": progress_pct,
                **(payload or {}),
            },
        )

    async def call_tool(
        self,
        tool_name: str,
        tool_fn: Callable,
        *args,
        **kwargs,
    ):
        """
        Call a tool with event emission.

        Emits TOOL_CALLED before and TOOL_COMPLETED after execution.
        """
        await self.emit_tool_call(tool_name, kwargs)

        start = time.time()
        try:
            result = await tool_fn(*args, **kwargs)
            duration_ms = int((time.time() - start) * 1000)
            await self.emit_tool_completed(tool_name, duration_ms)
            return result
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            await self.emit(
                EventKind.TOOL_FAILED,
                f"Tool '{tool_name}' failed: {str(e)}",
                stage_id=self.stage_id,
                level=EventLevel.ERROR,
                duration_ms=duration_ms,
            )
            raise

    async def save_artifact(self, artifact):
        """Save an artifact and emit event."""
        path = await self.artifact_store.save(artifact)
        await self.emit(
            EventKind.ARTIFACT_PERSISTED,
            f"Artifact saved: {artifact.artifact_type}",
            stage_id=self.stage_id,
            payload={
                "artifact_type": artifact.artifact_type,
                "artifact_id": artifact.artifact_id,
                "path": path,
            },
        )
        return path

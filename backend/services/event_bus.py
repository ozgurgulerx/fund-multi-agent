"""
Redis-based event bus for workflow event streaming.
Supports pub/sub via Redis Streams for reliable, scalable event delivery.
Works across multiple pods in AKS.
"""

import asyncio
import json
import os
from datetime import datetime
from typing import AsyncGenerator, Optional
import redis.asyncio as redis
from redis.asyncio.client import Redis
import structlog

from schemas.events import WorkflowEvent, EventKind, heartbeat_event

logger = structlog.get_logger()

# Redis configuration
# Use BACKEND_REDIS_* to avoid K8s service discovery conflicts
# (K8s injects REDIS_PORT=tcp://... when a service named 'redis' exists)
REDIS_HOST = os.getenv("BACKEND_REDIS_HOST", os.getenv("REDIS_HOST", "localhost"))
_redis_port = os.getenv("BACKEND_REDIS_PORT", "6379")
# Handle case where K8s injects tcp://IP:PORT format
if _redis_port.startswith("tcp://"):
    REDIS_PORT = int(_redis_port.split(":")[-1])
else:
    REDIS_PORT = int(_redis_port)
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
REDIS_DB = int(os.getenv("REDIS_DB", "0"))

# Stream configuration
STREAM_PREFIX = "ic:events:"
MAX_STREAM_LEN = 10000  # Max events per run stream
HEARTBEAT_INTERVAL = 15  # Seconds


class EventBus:
    """
    Redis Streams-based event bus for workflow events.

    Features:
    - Persistent event storage in Redis Streams
    - Consumer group support for scaling
    - Last-Event-ID resume capability
    - Heartbeat for SSE keepalive
    """

    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        self._sequence_counters: dict[str, int] = {}

    @classmethod
    async def create(cls) -> "EventBus":
        """Factory method to create EventBus with connection."""
        client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD,
            db=REDIS_DB,
            decode_responses=True,
        )
        # Test connection
        await client.ping()
        logger.info("event_bus_connected", host=REDIS_HOST, port=REDIS_PORT)
        return cls(client)

    def _stream_key(self, run_id: str) -> str:
        """Get Redis Stream key for a run."""
        return f"{STREAM_PREFIX}{run_id}"

    def _get_next_sequence(self, run_id: str) -> int:
        """Get next sequence number for a run."""
        if run_id not in self._sequence_counters:
            self._sequence_counters[run_id] = 0
        self._sequence_counters[run_id] += 1
        return self._sequence_counters[run_id]

    async def publish(self, event: WorkflowEvent) -> str:
        """
        Publish an event to the run's event stream.

        Args:
            event: WorkflowEvent to publish

        Returns:
            Redis Stream message ID
        """
        # Set sequence if not already set
        if event.sequence == 0:
            event.sequence = self._get_next_sequence(event.run_id)

        stream_key = self._stream_key(event.run_id)

        # Serialize event
        event_data = {
            "data": event.model_dump_json(),
            "event_id": event.event_id,
            "kind": event.kind.value,
            "ts": event.ts.isoformat(),
        }

        # Add to stream with max length cap
        message_id = await self.redis.xadd(
            stream_key,
            event_data,
            maxlen=MAX_STREAM_LEN,
        )

        logger.debug(
            "event_published",
            run_id=event.run_id,
            kind=event.kind.value,
            message_id=message_id,
            sequence=event.sequence,
        )

        return message_id

    async def subscribe(
        self,
        run_id: str,
        last_event_id: Optional[str] = None,
        include_heartbeats: bool = True,
    ) -> AsyncGenerator[WorkflowEvent, None]:
        """
        Subscribe to events for a run using Redis Streams.

        Args:
            run_id: Run to subscribe to
            last_event_id: Resume from this event ID (for reconnection)
            include_heartbeats: Whether to yield heartbeat events

        Yields:
            WorkflowEvent objects
        """
        stream_key = self._stream_key(run_id)

        # Determine starting position
        # Use "0" to start from beginning, "$" for only new events
        # Or use last_event_id for resume
        start_id = last_event_id if last_event_id else "0"

        logger.info(
            "event_subscribe_started",
            run_id=run_id,
            stream_key=stream_key,
            start_id=start_id,
        )

        last_heartbeat = datetime.utcnow()
        heartbeat_sequence = 0

        while True:
            try:
                # Read from stream with blocking (5 second timeout)
                messages = await self.redis.xread(
                    {stream_key: start_id},
                    count=100,
                    block=5000,  # 5 second block
                )

                if messages:
                    for stream_name, stream_messages in messages:
                        for message_id, message_data in stream_messages:
                            # Update position for next read
                            start_id = message_id

                            # Parse event
                            try:
                                event_json = message_data.get("data", "{}")
                                event = WorkflowEvent.model_validate_json(event_json)
                                yield event

                                # Check for run completion
                                if event.kind in [EventKind.RUN_COMPLETED, EventKind.RUN_FAILED]:
                                    logger.info("run_completed", run_id=run_id)
                                    return

                            except Exception as e:
                                logger.error("event_parse_error", error=str(e), data=message_data)
                                continue

                # Send heartbeat if needed
                if include_heartbeats:
                    now = datetime.utcnow()
                    if (now - last_heartbeat).total_seconds() >= HEARTBEAT_INTERVAL:
                        heartbeat_sequence += 1
                        yield heartbeat_event(run_id, sequence=heartbeat_sequence)
                        last_heartbeat = now

            except asyncio.CancelledError:
                logger.info("subscription_cancelled", run_id=run_id)
                raise
            except Exception as e:
                logger.error("subscription_error", run_id=run_id, error=str(e))
                await asyncio.sleep(1)  # Brief backoff before retry

    async def get_events(
        self,
        run_id: str,
        start_id: str = "-",
        end_id: str = "+",
        count: int = 1000,
    ) -> list[WorkflowEvent]:
        """
        Get historical events from a run's stream.

        Args:
            run_id: Run ID
            start_id: Start position (- for beginning)
            end_id: End position (+ for end)
            count: Maximum events to return

        Returns:
            List of WorkflowEvent objects
        """
        stream_key = self._stream_key(run_id)
        messages = await self.redis.xrange(stream_key, start_id, end_id, count=count)

        events = []
        for message_id, message_data in messages:
            try:
                event_json = message_data.get("data", "{}")
                event = WorkflowEvent.model_validate_json(event_json)
                events.append(event)
            except Exception as e:
                logger.error("event_parse_error", error=str(e))
                continue

        return events

    async def get_event_count(self, run_id: str) -> int:
        """Get total event count for a run."""
        stream_key = self._stream_key(run_id)
        return await self.redis.xlen(stream_key)

    async def delete_run_events(self, run_id: str) -> bool:
        """Delete all events for a run."""
        stream_key = self._stream_key(run_id)
        result = await self.redis.delete(stream_key)
        return result > 0

    async def close(self):
        """Close Redis connection."""
        await self.redis.close()


# Singleton instance
_event_bus: Optional[EventBus] = None


async def get_event_bus() -> EventBus:
    """Get or create the singleton EventBus instance."""
    global _event_bus
    if _event_bus is None:
        _event_bus = await EventBus.create()
    return _event_bus


async def close_event_bus():
    """Close the singleton EventBus instance."""
    global _event_bus
    if _event_bus is not None:
        await _event_bus.close()
        _event_bus = None

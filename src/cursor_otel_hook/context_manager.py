"""
Context Manager for Cross-Process Span Relationships

Since each Cursor hook runs in a separate process, we need to persist
trace context (trace_id, span_id) to a file so child spans can reference
their parent spans correctly.
"""

import hashlib
import json
import logging
import sys
from pathlib import Path
from typing import Optional, Dict, Any
import tempfile
import time

logger = logging.getLogger(__name__)


def generate_session_trace_id(conversation_id: str) -> int:
    """
    Generate deterministic 128-bit trace_id from conversation_id.

    Uses SHA256 hash of conversation_id, taking first 16 bytes (128 bits)
    and converting to integer for OTEL SpanContext compatibility.

    Args:
        conversation_id: The conversation ID string

    Returns:
        128-bit integer trace_id (formats to 32 hex characters)
    """
    hash_bytes = hashlib.sha256(conversation_id.encode("utf-8")).digest()
    # Take first 16 bytes (128 bits) for OTEL trace_id
    trace_id = int.from_bytes(hash_bytes[:16], byteorder="big")
    return trace_id


# Platform-specific file locking (same as batching_processor)
if sys.platform == "win32":
    import msvcrt

    def lock_file(file_handle, exclusive=True):
        """Lock file on Windows using msvcrt."""
        try:
            msvcrt.locking(
                file_handle.fileno(), msvcrt.LK_LOCK if exclusive else msvcrt.LK_LOCK, 1
            )
        except IOError:
            pass

    def unlock_file(file_handle):
        """Unlock file on Windows using msvcrt."""
        try:
            msvcrt.locking(file_handle.fileno(), msvcrt.LK_UNLCK, 1)
        except IOError:
            pass
else:
    import fcntl

    def lock_file(file_handle, exclusive=True):
        """Lock file on Unix/Linux using fcntl."""
        lock_type = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        fcntl.flock(file_handle.fileno(), lock_type)

    def unlock_file(file_handle):
        """Unlock file on Unix/Linux using fcntl."""
        fcntl.flock(file_handle.fileno(), fcntl.LOCK_UN)


class GenerationContextManager:
    """
    Manages span context across process invocations for a generation.

    This allows proper parent-child relationships between spans even though
    each hook event runs in a separate process.
    """

    def __init__(self, storage_dir: Optional[Path] = None):
        """
        Initialize the context manager.

        Args:
            storage_dir: Directory for context storage (default: temp dir)
        """
        if storage_dir is None:
            base_temp = Path(tempfile.gettempdir())
            self.storage_dir = base_temp / "cursor_otel_context"
        else:
            self.storage_dir = storage_dir

        self.storage_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(
            f"GenerationContextManager initialized with storage: {self.storage_dir}"
        )

    def get_context_file(self, generation_id: str) -> Path:
        """Get the context file path for a generation."""
        return self.storage_dir / f"{generation_id}_context.json"

    def get_parent_context(
        self, generation_id: str, hook_event: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get the parent span context for this hook event.

        Returns:
            Dict with trace_id, span_id, or None if this should be a root span
        """
        context_file = self.get_context_file(generation_id)

        if not context_file.exists():
            logger.debug(
                f"No context file for generation {generation_id}, creating root span"
            )
            return None

        try:
            with open(context_file, "r", encoding="utf-8") as f:
                lock_file(f, exclusive=False)
                try:
                    context = json.load(f)
                finally:
                    unlock_file(f)

            # Determine parent based on hook event type and context state
            parent = self._determine_parent(context, hook_event)

            if parent:
                logger.debug(f"Using parent span {parent['span_id']} for {hook_event}")
            else:
                logger.debug(f"No parent for {hook_event}, will be root span")

            return parent

        except Exception as e:
            logger.error(f"Error reading context file: {e}", exc_info=True)
            return None

    def get_session_trace_id(self, generation_id: str) -> Optional[int]:
        """
        Get the session-level trace_id for a generation.

        Returns:
            The session trace_id as integer, or None if not found
        """
        context_file = self.get_context_file(generation_id)

        if not context_file.exists():
            return None

        try:
            with open(context_file, "r", encoding="utf-8") as f:
                lock_file(f, exclusive=False)
                try:
                    context = json.load(f)
                finally:
                    unlock_file(f)

            return context.get("session_trace_id")

        except Exception as e:
            logger.error(f"Error reading session trace_id: {e}", exc_info=True)
            return None

    def _determine_parent(
        self, context: Dict[str, Any], hook_event: str
    ) -> Optional[Dict[str, Any]]:
        """
        Determine the appropriate parent span based on event type and context.

        Span hierarchy:
        - Root: sessionStart, beforeSubmitPrompt
        - Child of session: subagentStart, tool events
        - Child of subagent: tool events during subagent
        - Child of tool: postToolUse, postToolUseFailure (follow preToolUse)
        """
        # Events that should be root spans (no parent)
        root_events = {"sessionStart"}
        if hook_event in root_events:
            return None

        # Get current context state
        current_session = context.get("current_session_span")
        current_subagent = context.get("current_subagent_span")
        current_tool = context.get("current_tool_span")

        # Tool completion events should be children of the tool start
        if hook_event in {
            "postToolUse",
            "postToolUseFailure",
            "afterShellExecution",
            "afterMCPExecution",
            "afterFileEdit",
        }:
            if current_tool:
                return {
                    "trace_id": current_tool["trace_id"],
                    "span_id": current_tool["span_id"],
                }

        # Subagent events should be children of the session
        if hook_event == "subagentStart":
            if current_session:
                return {
                    "trace_id": current_session["trace_id"],
                    "span_id": current_session["span_id"],
                }

        # Tool start events should be children of subagent if in subagent, else session
        if hook_event in {
            "preToolUse",
            "beforeShellExecution",
            "beforeMCPExecution",
            "beforeReadFile",
        }:
            if current_subagent:
                return {
                    "trace_id": current_subagent["trace_id"],
                    "span_id": current_subagent["span_id"],
                }
            elif current_session:
                return {
                    "trace_id": current_session["trace_id"],
                    "span_id": current_session["span_id"],
                }

        # Other events should be children of subagent if active, else session
        if current_subagent:
            return {
                "trace_id": current_subagent["trace_id"],
                "span_id": current_subagent["span_id"],
            }
        elif current_session:
            return {
                "trace_id": current_session["trace_id"],
                "span_id": current_session["span_id"],
            }

        return None

    def save_span_context(
        self,
        generation_id: str,
        hook_event: str,
        trace_id: int,
        span_id: int,
    ) -> None:
        """
        Save the current span context for future hook events to use as parent.

        Args:
            generation_id: The generation ID
            hook_event: The hook event name
            trace_id: The trace ID (as integer)
            span_id: The span ID (as integer)
        """
        context_file = self.get_context_file(generation_id)

        # Read existing context or create new
        context = {}
        if context_file.exists():
            try:
                with open(context_file, "r", encoding="utf-8") as f:
                    lock_file(f, exclusive=False)
                    try:
                        context = json.load(f)
                    finally:
                        unlock_file(f)
            except Exception as e:
                logger.warning(f"Error reading context: {e}")

        # Update context based on event type
        span_info = {
            "trace_id": trace_id,
            "span_id": span_id,
            "hook_event": hook_event,
            "timestamp": time.time(),
        }

        # Track different span types
        if hook_event == "sessionStart":
            context["current_session_span"] = span_info
            context["current_subagent_span"] = None
            context["current_tool_span"] = None
            context["session_trace_id"] = trace_id

        elif hook_event == "sessionEnd":
            # Clear all context on session end
            context = {}

        elif hook_event == "subagentStart":
            context["current_subagent_span"] = span_info
            context["current_tool_span"] = None

        elif hook_event == "subagentStop":
            context["current_subagent_span"] = None
            context["current_tool_span"] = None

        elif hook_event in {
            "preToolUse",
            "beforeShellExecution",
            "beforeMCPExecution",
            "beforeReadFile",
        }:
            context["current_tool_span"] = span_info

        elif hook_event in {
            "postToolUse",
            "postToolUseFailure",
            "afterShellExecution",
            "afterMCPExecution",
            "afterFileEdit",
        }:
            # Clear tool span after completion
            context["current_tool_span"] = None

        # Write updated context
        try:
            with open(context_file, "w", encoding="utf-8") as f:
                lock_file(f, exclusive=True)
                try:
                    json.dump(context, f, indent=2)
                    f.flush()
                finally:
                    unlock_file(f)

            logger.debug(
                f"Saved context for {hook_event}: span_id={format(span_id, '016x')}"
            )

        except Exception as e:
            logger.error(f"Error saving context: {e}", exc_info=True)

    def cleanup_context(self, generation_id: str) -> None:
        """Remove context file for a generation after stop event."""
        context_file = self.get_context_file(generation_id)
        try:
            if context_file.exists():
                context_file.unlink()
                logger.debug(f"Cleaned up context file for generation {generation_id}")
        except Exception as e:
            logger.warning(f"Error cleaning up context file: {e}")

    def cleanup_old_contexts(self, max_age_hours: int = 24) -> None:
        """Remove context files older than max_age_hours."""
        try:
            current_time = time.time()
            max_age_seconds = max_age_hours * 3600

            for context_file in self.storage_dir.glob("*_context.json"):
                file_age = current_time - context_file.stat().st_mtime
                if file_age > max_age_seconds:
                    logger.info(f"Removing old context file: {context_file}")
                    context_file.unlink()
        except Exception as e:
            logger.error(f"Error cleaning up old contexts: {e}", exc_info=True)

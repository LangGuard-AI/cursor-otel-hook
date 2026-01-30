#!/usr/bin/env python3
"""
Cursor Hook Receiver with OpenTelemetry Integration

Receives Cursor IDE hook events via stdin and exports traces to OTEL collectors.
"""

import json
import logging
import sys
import time
from typing import Any, Dict, Optional
import argparse
from pathlib import Path

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider, ReadableSpan
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.trace import Status, StatusCode
from typing import Sequence

from .config import OTELConfig
from .privacy import mask_sensitive_data
from .context_manager import generate_session_trace_id

# Configure logging
logger = logging.getLogger(__name__)


class LoggingSpanExporterWrapper(SpanExporter):
    """Wrapper that logs spans before exporting them."""

    def __init__(self, exporter: SpanExporter):
        self.exporter = exporter

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        """Log spans and then export them."""
        # Log complete span information
        logger.debug(f"Exporting {len(spans)} spans")
        for i, span in enumerate(spans):
            span_dict = self._span_to_dict(span)
            logger.debug(
                f"Span {i + 1}/{len(spans)}:\n{json.dumps(span_dict, indent=2, default=str)}"
            )

        # Export via wrapped exporter
        return self.exporter.export(spans)

    def _span_to_dict(self, span: ReadableSpan) -> Dict[str, Any]:
        """Convert a ReadableSpan to a dictionary for logging."""
        ctx = span.get_span_context()

        result = {
            "name": span.name,
            "context": {
                "trace_id": format(ctx.trace_id, "032x"),
                "span_id": format(ctx.span_id, "016x"),
                "trace_flags": ctx.trace_flags,
            },
            "parent": {"span_id": format(span.parent.span_id, "016x")}
            if span.parent
            else None,
            "start_time": span.start_time,
            "end_time": span.end_time,
            "attributes": dict(span.attributes) if span.attributes else {},
            "events": [
                {
                    "name": event.name,
                    "timestamp": event.timestamp,
                    "attributes": dict(event.attributes) if event.attributes else {},
                }
                for event in (span.events or [])
            ],
            "status": {
                "status_code": span.status.status_code.name if span.status else None,
                "description": span.status.description if span.status else None,
            },
            "kind": span.kind.name if span.kind else None,
        }

        return result

    def shutdown(self):
        """Shutdown the wrapped exporter."""
        return self.exporter.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """Force flush the wrapped exporter."""
        return self.exporter.force_flush(timeout_millis)

    def export_otlp_json(self, otlp_payload: Dict[str, Any]) -> SpanExportResult:
        """
        Export pre-formatted OTLP JSON payload (pass-through to wrapped exporter).

        This method is used by GenerationBatchingProcessor to send batched spans.
        """
        logger.debug(f"Exporting batched OTLP JSON payload")
        logger.debug(f"Payload keys: {list(otlp_payload.keys())}")

        # Count spans for logging
        span_count = sum(
            len(scope_span.get("spans", []))
            for rs in otlp_payload.get("resourceSpans", [])
            for scope_span in rs.get("scopeSpans", [])
        )
        logger.debug(f"Batched payload contains {span_count} spans")

        # Pass through to wrapped exporter
        if hasattr(self.exporter, "export_otlp_json"):
            return self.exporter.export_otlp_json(otlp_payload)
        else:
            logger.error("Wrapped exporter doesn't support export_otlp_json")
            return SpanExportResult.FAILURE


class CursorHookProcessor:
    """Processes Cursor hooks and creates OTEL traces"""

    def __init__(self, config: OTELConfig, debug: bool = False):
        self.config = config
        self.debug = debug
        logger.info(
            f"Initializing CursorHookProcessor with endpoint: {config.endpoint}"
        )
        logger.info(f"Protocol: {config.protocol}, Service: {config.service_name}")
        logger.info(f"Debug mode: {debug}")
        self.span_processor = None  # Will be set by _setup_tracer
        self.context_manager = None  # Will be set for batching mode
        self.tracer = self._setup_tracer()
        # Check endpoint connectivity (non-blocking warning only)
        self._check_endpoint_connectivity()

    def _setup_tracer(self) -> trace.Tracer:
        """Initialize OpenTelemetry tracer with OTLP exporter"""
        # Create resource with service name
        resource = Resource(attributes={SERVICE_NAME: self.config.service_name})

        # Create tracer provider
        provider = TracerProvider(resource=resource)

        # Configure OTLP exporter based on protocol
        exporter_kwargs: Dict[str, Any] = {
            "endpoint": self.config.endpoint,
        }

        # Add headers if provided
        if self.config.headers:
            exporter_kwargs["headers"] = tuple(
                (k, v) for k, v in self.config.headers.items()
            )

        # Choose exporter based on protocol
        if self.config.protocol == "http/json":
            # Use custom JSON HTTP exporter
            from .json_exporter import OTLPJSONSpanExporter
            from .batching_processor import GenerationBatchingProcessor
            from .context_manager import GenerationContextManager

            # Ensure endpoint has /v1/traces path for OTLP HTTP spec
            endpoint = self.config.endpoint
            if not endpoint.endswith("/v1/traces"):
                if endpoint.endswith("/"):
                    endpoint = endpoint + "v1/traces"
                else:
                    endpoint = endpoint + "/v1/traces"
                logger.warning(f"Appended '/v1/traces' to endpoint: {endpoint}")

            logger.info(f"Using HTTP/JSON OTLP exporter with endpoint: {endpoint}")

            # Log auth headers (keys only, not values)
            if self.config.headers:
                header_keys = list(self.config.headers.keys())
                logger.info(f"Auth headers configured: {header_keys}")
            else:
                logger.warning("No auth headers configured - requests may be rejected")

            otlp_exporter = OTLPJSONSpanExporter(
                endpoint=endpoint,
                headers=self.config.headers,
                timeout=self.config.timeout,
                service_name=self.config.service_name,
            )
            logger.info("Custom JSON exporter initialized successfully")

            # Wrap with logging exporter
            wrapped_exporter = LoggingSpanExporterWrapper(otlp_exporter)

            # Use GenerationBatchingProcessor instead of BatchSpanProcessor
            # Pass debug flag to preserve files in debug mode
            span_processor = GenerationBatchingProcessor(
                wrapped_exporter, debug=self.debug
            )
            self.span_processor = span_processor  # Store reference for flushing

            # Initialize context manager for cross-process parent-child relationships
            self.context_manager = GenerationContextManager()
            logger.info("Context manager initialized for span relationships")

            provider.add_span_processor(span_processor)
            trace.set_tracer_provider(provider)
            return trace.get_tracer(__name__)

        elif self.config.protocol == "http/protobuf":
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )

            logger.info("Using HTTP OTLP exporter (protobuf format)")
            # HTTP exporter uses protobuf by default
            # The endpoint should include /v1/traces for OTLP HTTP
            # Note: HTTP exporter doesn't use 'insecure' parameter
            # Instead, use http:// or https:// in the endpoint URL
        else:
            # Default to gRPC
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            logger.info(f"Using gRPC OTLP exporter (insecure={self.config.insecure})")
            # gRPC exporter supports insecure parameter
            exporter_kwargs["insecure"] = self.config.insecure

        try:
            otlp_exporter = OTLPSpanExporter(**exporter_kwargs)
            logger.info("OTLP exporter initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize OTLP exporter: {e}")
            raise

        # Wrap with logging exporter
        wrapped_exporter = LoggingSpanExporterWrapper(otlp_exporter)

        # Add span processor
        span_processor = BatchSpanProcessor(wrapped_exporter)
        provider.add_span_processor(span_processor)

        # Set as global tracer provider
        trace.set_tracer_provider(provider)

        return trace.get_tracer(__name__)

    def _check_endpoint_connectivity(self) -> bool:
        """
        Quick connectivity check to endpoint (non-blocking warning only).

        Performs a HEAD request to the endpoint with a 2-second timeout.
        Logs INFO if reachable, WARNING if unreachable. Does not fail startup.

        Returns:
            True if endpoint is reachable, False otherwise
        """
        try:
            import urllib.request

            req = urllib.request.Request(self.config.endpoint, method="HEAD")
            urllib.request.urlopen(req, timeout=2)
            logger.info(f"Endpoint reachable: {self.config.endpoint}")
            return True
        except Exception as e:
            logger.warning(f"Endpoint may be unreachable: {self.config.endpoint} ({e})")
            return False

    def process_hook(self, hook_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a hook event and create appropriate OTEL spans

        Returns the response to send back to Cursor
        """
        hook_event = hook_data.get("hook_event_name", "unknown")
        conversation_id = hook_data.get("conversation_id", "unknown")
        generation_id = hook_data.get("generation_id", "unknown")

        # Log processing start with event and generation_id
        gen_id_display = generation_id[:16] if generation_id != "unknown" else "unknown"
        logger.info(f"Processing: event={hook_event}, generation={gen_id_display}...")

        # Check if this is a 'stop' event - if so, flush the generation
        if hook_event == "stop" and generation_id != "unknown":
            logger.info(
                f"Stop event detected for generation {generation_id}, flushing spans"
            )
            if self.span_processor and hasattr(self.span_processor, "flush_generation"):
                self.span_processor.flush_generation(
                    generation_id, self.config.service_name
                )
            # Cleanup context after flushing
            if self.context_manager:
                self.context_manager.cleanup_context(generation_id)
            # Note: We still create a span for the stop event itself

        # Create span name based on hook event
        span_name = f"cursor.{hook_event}"

        # Start timing
        start_time = time.time()

        # Get parent context if context manager is enabled
        parent_context = None
        if self.context_manager and generation_id != "unknown":
            parent_context = self.context_manager.get_parent_context(
                generation_id, hook_event
            )

        # Create span with or without parent context
        span = self._create_span_with_context(
            span_name,
            parent_context,
            conversation_id=conversation_id,
            hook_event=hook_event,
            generation_id=generation_id,
        )

        # Log span creation with trace_id
        ctx = span.get_span_context()
        trace_id_prefix = format(ctx.trace_id, "032x")[:16]
        logger.info(
            f"Created span: {span_name} (generation: {gen_id_display}, trace: {trace_id_prefix}...)"
        )

        with span:
            try:
                # Add common attributes
                self._add_common_attributes(span, hook_data)

                # Add event-specific attributes
                self._add_event_specific_attributes(span, hook_event, hook_data)

                # Process based on hook type
                response = self._generate_response(hook_event, hook_data)

                # Add response attributes
                if "permission" in response:
                    span.set_attribute(
                        "langsmith.metadata.permission", response["permission"]
                    )

                # Set status as OK
                span.set_status(Status(StatusCode.OK))

                return response

            except Exception as e:
                # Record exception in span
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR, str(e)))

                # Re-raise to handle at higher level
                raise

            finally:
                # Record duration
                duration = time.time() - start_time
                span.set_attribute("langsmith.metadata.duration_ms", duration * 1000)

                # Log span completion with duration
                logger.info(
                    f"Span completed: {span_name} (duration: {duration * 1000:.1f}ms)"
                )

                if self.context_manager:
                    ctx = span.get_span_context()

                    if hook_event == "sessionStart" and conversation_id != "unknown":
                        self.context_manager.save_conversation_trace_id(
                            conversation_id=conversation_id,
                            trace_id=ctx.trace_id,
                        )

                    if generation_id != "unknown":
                        self.context_manager.save_span_context(
                            generation_id=generation_id,
                            hook_event=hook_event,
                            trace_id=ctx.trace_id,
                            span_id=ctx.span_id,
                        )

    def _create_span_with_context(
        self,
        span_name: str,
        parent_context: Optional[Dict[str, Any]] = None,
        conversation_id: Optional[str] = None,
        hook_event: Optional[str] = None,
        generation_id: Optional[str] = None,
    ) -> trace.Span:
        """
        Create a span with explicit parent context.

        If parent_context is provided, creates the span as a child of that context.
        Otherwise, creates a new root span.

        For sessionStart events, generates a deterministic trace_id from conversation_id.
        For other events, uses the stored session trace_id if available.
        """
        from opentelemetry.trace import SpanContext, TraceFlags
        from opentelemetry import context as otel_context
        import random

        if parent_context is None:
            # For sessionStart, generate deterministic trace_id from conversation_id
            if (
                hook_event == "sessionStart"
                and conversation_id
                and conversation_id != "unknown"
            ):
                session_trace_id = generate_session_trace_id(conversation_id)

                # Generate a new span_id
                span_id = random.getrandbits(64)

                # Create SpanContext with our deterministic trace_id
                span_context = SpanContext(
                    trace_id=session_trace_id,
                    span_id=span_id,
                    is_remote=False,
                    trace_flags=TraceFlags(0x01),
                )

                # Create context and start span
                ctx = trace.set_span_in_context(trace.NonRecordingSpan(span_context))
                return self.tracer.start_span(span_name, context=ctx)

            # For other root spans, try to use existing session trace_id
            if (
                conversation_id
                and conversation_id != "unknown"
                and self.context_manager
            ):
                session_trace_id = self.context_manager.get_conversation_trace_id(
                    conversation_id
                )
                if session_trace_id:
                    # Generate new span_id
                    span_id = random.getrandbits(64)

                    # Create SpanContext with session trace_id
                    span_context = SpanContext(
                        trace_id=session_trace_id,
                        span_id=span_id,
                        is_remote=False,
                        trace_flags=TraceFlags(0x01),
                    )

                    # Create context and start span
                    ctx = trace.set_span_in_context(
                        trace.NonRecordingSpan(span_context)
                    )
                    return self.tracer.start_span(span_name, context=ctx)

            # Fallback for spans with no conversation_id or no stored trace_id
            return self.tracer.start_span(span_name)

        if self.context_manager:
            session_trace_id = None

            if generation_id and generation_id != "unknown":
                session_trace_id = self.context_manager.get_session_trace_id(
                    generation_id
                )

            if (
                not session_trace_id
                and conversation_id
                and conversation_id != "unknown"
            ):
                session_trace_id = self.context_manager.get_conversation_trace_id(
                    conversation_id
                )

            if session_trace_id:
                parent_span_context = SpanContext(
                    trace_id=session_trace_id,
                    span_id=parent_context["span_id"],
                    is_remote=True,
                    trace_flags=TraceFlags(0x01),
                )

                ctx = trace.set_span_in_context(
                    trace.NonRecordingSpan(parent_span_context)
                )

                return self.tracer.start_span(span_name, context=ctx)

        # Fallback: use parent_context as-is
        parent_span_context = SpanContext(
            trace_id=parent_context["trace_id"],
            span_id=parent_context["span_id"],
            is_remote=True,
            trace_flags=TraceFlags(0x01),  # Sampled
        )

        # Create a context with this parent
        ctx = trace.set_span_in_context(trace.NonRecordingSpan(parent_span_context))

        # Start span with this parent context
        return self.tracer.start_span(span_name, context=ctx)

    def _add_common_attributes(
        self, span: trace.Span, hook_data: Dict[str, Any]
    ) -> None:
        """Add common attributes using LangSmith/GenAI conventions"""

        # Get span context to access OTEL IDs
        ctx = span.get_span_context()

        # Session and trace identifiers (LangSmith convention)
        # IMPORTANT: Use actual OTEL trace_id, not generation_id
        span.set_attribute("langsmith.trace.id", format(ctx.trace_id, "032x"))

        # Add span ID derived from OTEL context
        span.set_attribute("langsmith.span.id", format(ctx.span_id, "016x"))

        # Add parent span ID if it exists
        if span.parent:
            span.set_attribute(
                "langsmith.span.parent_id", format(span.parent.span_id, "016x")
            )

        # Session ID comes from Cursor's conversation_id
        if "conversation_id" in hook_data:
            span.set_attribute(
                "langsmith.trace.session_id", hook_data["conversation_id"]
            )

        # Preserve generation_id as metadata (not as trace ID)
        if "generation_id" in hook_data:
            span.set_attribute(
                "langsmith.metadata.generation_id", hook_data["generation_id"]
            )

        # Model information (GenAI convention)
        if "model" in hook_data:
            model = hook_data["model"]
            span.set_attribute("gen_ai.request.model", model)
            span.set_attribute("gen_ai.response.model", model)

            # Determine provider from model name
            if "claude" in model.lower():
                span.set_attribute("gen_ai.system", "anthropic")
            elif "gpt" in model.lower() or "o1" in model.lower():
                span.set_attribute("gen_ai.system", "openai")
            else:
                span.set_attribute("gen_ai.system", "cursor")

        # Additional metadata (LangSmith convention)
        if "cursor_version" in hook_data:
            span.set_attribute(
                "langsmith.metadata.cursor_version", hook_data["cursor_version"]
            )
        if "user_email" in hook_data:
            span.set_attribute("langsmith.metadata.user_email", hook_data["user_email"])
        if "transcript_path" in hook_data:
            span.set_attribute(
                "langsmith.metadata.transcript_path", hook_data["transcript_path"]
            )

        # Workspace context
        workspace_roots = hook_data.get("workspace_roots", [])
        if workspace_roots:
            span.set_attribute(
                "langsmith.metadata.workspace_roots", json.dumps(workspace_roots)
            )

        # Store hook event type
        if "hook_event_name" in hook_data:
            span.set_attribute(
                "langsmith.metadata.hook_event", hook_data["hook_event_name"]
            )

    def _add_event_specific_attributes(
        self, span: trace.Span, event: str, hook_data: Dict[str, Any]
    ) -> None:
        """Add event-specific attributes using LangSmith/GenAI conventions"""

        # Apply masking if enabled
        if self.config.mask_prompts:
            hook_data = mask_sensitive_data(hook_data)

        # Set operation name for GenAI convention
        span.set_attribute("gen_ai.operation.name", self._map_event_to_operation(event))

        # Set LangSmith span kind
        span.set_attribute("langsmith.span.kind", self._map_event_to_span_kind(event))

        # Session events
        if event in ["sessionStart", "sessionEnd"]:
            for attr in ["session_id", "is_background_agent", "composer_mode"]:
                if attr in hook_data:
                    span.set_attribute(
                        f"langsmith.metadata.{attr}", str(hook_data[attr])
                    )

        # Tool use events (GenAI convention)
        elif event in ["preToolUse", "postToolUse", "postToolUseFailure"]:
            if "tool_name" in hook_data:
                span.set_attribute("gen_ai.tool.name", hook_data["tool_name"])

            if "tool_input" in hook_data:
                tool_input = hook_data["tool_input"]
                # Store as invocation parameters
                span.set_attribute(
                    "langsmith.metadata.tool_input", json.dumps(tool_input)
                )
                # Also store arguments in standard format
                if isinstance(tool_input, dict):
                    span.set_attribute("gen_ai.tool.arguments", json.dumps(tool_input))

            if "tool_output" in hook_data:
                output = hook_data["tool_output"]
                # Truncate large outputs
                if isinstance(output, str) and len(output) > 10000:
                    output = output[:10000] + "... (truncated)"
                span.set_attribute("langsmith.metadata.tool_output", str(output))

        # Shell execution (treat as tool)
        elif event in ["beforeShellExecution", "afterShellExecution"]:
            span.set_attribute("gen_ai.tool.name", "bash")

            if "command" in hook_data:
                span.set_attribute(
                    "gen_ai.tool.arguments",
                    json.dumps({"command": hook_data["command"]}),
                )
                span.set_attribute(
                    "langsmith.metadata.shell_command", hook_data["command"]
                )
            if "cwd" in hook_data:
                span.set_attribute("langsmith.metadata.shell_cwd", hook_data["cwd"])
            if "timeout" in hook_data:
                span.set_attribute(
                    "langsmith.metadata.shell_timeout", hook_data["timeout"]
                )
            if "exit_code" in hook_data:
                span.set_attribute(
                    "langsmith.metadata.shell_exit_code", hook_data["exit_code"]
                )

        # MCP execution (treat as tool)
        elif event in ["beforeMCPExecution", "afterMCPExecution"]:
            if "mcp_tool" in hook_data:
                tool_name = hook_data["mcp_tool"]
                if "mcp_server" in hook_data:
                    tool_name = f"{hook_data['mcp_server']}.{tool_name}"
                span.set_attribute("gen_ai.tool.name", tool_name)

            if "mcp_input" in hook_data:
                span.set_attribute(
                    "gen_ai.tool.arguments", json.dumps(hook_data["mcp_input"])
                )

            if "mcp_server" in hook_data:
                span.set_attribute(
                    "langsmith.metadata.mcp_server", hook_data["mcp_server"]
                )

        # File operations (treat as tool)
        elif event in ["beforeReadFile", "afterFileEdit"]:
            tool_name = "read_file" if event == "beforeReadFile" else "edit_file"
            span.set_attribute("gen_ai.tool.name", tool_name)

            if "file_path" in hook_data:
                span.set_attribute(
                    "gen_ai.tool.arguments",
                    json.dumps({"file_path": hook_data["file_path"]}),
                )
                span.set_attribute(
                    "langsmith.metadata.file_path", hook_data["file_path"]
                )

            if "edits" in hook_data:
                span.set_attribute(
                    "langsmith.metadata.edit_count", len(hook_data["edits"])
                )

        # Prompt submission (GenAI convention)
        elif event == "beforeSubmitPrompt":
            if "prompt" in hook_data and not self.config.mask_prompts:
                prompt = hook_data["prompt"]
                # Truncate very long prompts
                if len(prompt) > 5000:
                    prompt = prompt[:5000] + "... (truncated)"

                # Store in GenAI format (as user message)
                span.set_attribute("gen_ai.prompt.0.role", "user")
                span.set_attribute("gen_ai.prompt.0.content", prompt)
            elif "prompt" in hook_data:
                span.set_attribute("gen_ai.prompt.0.role", "user")
                span.set_attribute("gen_ai.prompt.0.content", "[MASKED]")

        # Context compaction
        elif event == "preCompact":
            if "context_size" in hook_data:
                span.set_attribute(
                    "langsmith.metadata.context_size", hook_data["context_size"]
                )
            if "context_limit" in hook_data:
                span.set_attribute(
                    "langsmith.metadata.context_limit", hook_data["context_limit"]
                )

        # Stop/completion events
        elif event == "stop":
            if "status" in hook_data:
                span.set_attribute(
                    "langsmith.metadata.completion_status", hook_data["status"]
                )
            if "loop_count" in hook_data:
                span.set_attribute(
                    "langsmith.metadata.loop_count", hook_data["loop_count"]
                )

        # Subagent events (treat as chain)
        elif event in ["subagentStart", "subagentStop"]:
            if "subagent_type" in hook_data:
                span.set_attribute(
                    "langsmith.metadata.subagent_type", hook_data["subagent_type"]
                )
            if "subagent_task" in hook_data:
                span.set_attribute(
                    "langsmith.metadata.subagent_task", hook_data["subagent_task"]
                )

        # Add all remaining fields as JSON for debugging
        span.set_attribute("langsmith.metadata.raw_event", json.dumps(hook_data))

    def _map_event_to_operation(self, event: str) -> str:
        """Map Cursor hook event to GenAI operation name"""
        operation_map = {
            "beforeSubmitPrompt": "chat",
            "preToolUse": "tool",
            "postToolUse": "tool",
            "postToolUseFailure": "tool",
            "beforeShellExecution": "tool",
            "afterShellExecution": "tool",
            "beforeMCPExecution": "tool",
            "afterMCPExecution": "tool",
            "beforeReadFile": "tool",
            "afterFileEdit": "tool",
            "subagentStart": "chain",
            "subagentStop": "chain",
            "sessionStart": "session",
            "sessionEnd": "session",
        }
        return operation_map.get(event, "unknown")

    def _map_event_to_span_kind(self, event: str) -> str:
        """Map Cursor hook event to LangSmith span kind"""
        kind_map = {
            "beforeSubmitPrompt": "llm",
            "preToolUse": "tool",
            "postToolUse": "tool",
            "postToolUseFailure": "tool",
            "beforeShellExecution": "tool",
            "afterShellExecution": "tool",
            "beforeMCPExecution": "tool",
            "afterMCPExecution": "tool",
            "beforeReadFile": "tool",
            "afterFileEdit": "tool",
            "subagentStart": "chain",
            "subagentStop": "chain",
        }
        return kind_map.get(event, "chain")

    def _generate_response(
        self, event: str, hook_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate appropriate response for the hook event

        By default, allow all operations. Override this method for custom logic.
        """
        # For hooks that require permission responses
        if event in [
            "beforeShellExecution",
            "beforeMCPExecution",
            "beforeReadFile",
            "beforeSubmitPrompt",
        ]:
            return {"permission": "allow"}

        # For other hooks, return empty response (allows operation to proceed)
        return {}


def main() -> None:
    """Main entry point for the hook receiver"""
    parser = argparse.ArgumentParser(
        description="Cursor OpenTelemetry Hook Receiver",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment Variables:
  OTEL_EXPORTER_OTLP_ENDPOINT    OTLP endpoint (default: http://localhost:4317)
  OTEL_SERVICE_NAME              Service name (default: cursor-agent)
  OTEL_EXPORTER_OTLP_INSECURE    Use insecure connection (default: true)
  OTEL_EXPORTER_OTLP_HEADERS     Headers as key=value,key=value
  OTEL_EXPORTER_OTLP_TIMEOUT     Timeout in seconds (default: 30)
  CURSOR_OTEL_MASK_PROMPTS       Mask user prompts (default: false)

Examples:
  # Using environment variables
  export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317"
  cursor-otel-hook

  # Using config file
  cursor-otel-hook --config /path/to/config.json
        """,
    )
    parser.add_argument(
        "--config",
        "-c",
        help="Path to JSON configuration file",
        default=None,
    )
    parser.add_argument(
        "--debug",
        "-d",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--log-file",
        "-l",
        help="Path to log file (default: cursor_otel_hook.log in project dir)",
        default=None,
    )

    args = parser.parse_args()

    # Setup logging
    # Only show INFO and above when debug is off, DEBUG and above when on
    log_level = logging.DEBUG if args.debug else logging.INFO
    log_file = args.log_file

    # If no log file specified, use Cursor profile directory
    if log_file is None:
        # Default to ~/.cursor/hooks/ directory
        cursor_hooks_dir = Path.home() / ".cursor" / "hooks"
        cursor_hooks_dir.mkdir(parents=True, exist_ok=True)
        log_file = cursor_hooks_dir / "cursor_otel_hook.log"
    else:
        log_file = Path(log_file)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stderr) if args.debug else logging.NullHandler(),
        ],
    )

    logger.info("=" * 60)
    logger.info("Cursor OTEL Hook starting")
    logger.info(f"Log file: {log_file}")
    logger.info(f"Debug mode: {args.debug}")

    try:
        # Load configuration
        logger.info(
            f"Loading configuration from: {args.config or 'environment variables'}"
        )
        config = OTELConfig.load(args.config)
        logger.info(f"Configuration loaded successfully")
        logger.debug(f"Config details: {config}")

        # Create processor with debug flag
        processor = CursorHookProcessor(config, debug=args.debug)

        # Read hook data from stdin
        logger.debug("Reading hook data from stdin")
        hook_input = sys.stdin.read()
        logger.debug(f"Received {len(hook_input)} bytes of input")

        # Parse JSON
        logger.debug("Parsing JSON input")
        hook_data = json.loads(hook_input)
        hook_event = hook_data.get("hook_event_name", "unknown")
        logger.info(f"Processing hook event: {hook_event}")

        # Process hook and get response
        response = processor.process_hook(hook_data)
        logger.info(f"Hook processed successfully, response: {response}")

        # Output response as JSON
        print(json.dumps(response))

        logger.info("Hook execution completed successfully")
        logger.info("=" * 60)

        # Exit with success
        sys.exit(0)

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON input: {e}")
        logger.error(
            f"Input received: {hook_input if 'hook_input' in locals() else 'N/A'}"
        )
        print(f"Error: Invalid JSON input: {e}", file=sys.stderr)
        sys.exit(1)

    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        print(f"Error: {e}", file=sys.stderr)
        if args.debug:
            import traceback

            traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

"""
Batching Span Processor for Generation-based Coalescing

This processor stores spans in temporary files grouped by generation_id,
and only sends them to the OTEL receiver when a 'stop' event is received.

The spans are stored in OTLP JSON format directly, so they can be easily
sent to the collector without reconstruction.
"""

import json
import logging
import time
import sys
from pathlib import Path
from typing import Optional, Any, Dict
import tempfile

from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.context import Context
from opentelemetry.trace import SpanKind, StatusCode

logger = logging.getLogger(__name__)

# Platform-specific file locking
if sys.platform == "win32":
    import msvcrt

    def lock_file(file_handle, exclusive=True):
        """Lock file on Windows using msvcrt."""
        try:
            msvcrt.locking(
                file_handle.fileno(), msvcrt.LK_LOCK if exclusive else msvcrt.LK_LOCK, 1
            )
        except IOError:
            pass  # File may already be locked

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


class GenerationBatchingProcessor(SpanProcessor):
    """
    Span processor that batches spans by generation_id and only exports on 'stop' event.

    Each span is written to a temporary file named by generation_id. When a 'stop'
    event is received, all spans for that generation are read and exported together.
    """

    def __init__(
        self,
        exporter: SpanExporter,
        storage_dir: Optional[Path] = None,
        max_age_hours: int = 24,
        debug: bool = False,
    ):
        """
        Initialize the batching processor.

        Args:
            exporter: The SpanExporter to send batched spans to
            storage_dir: Directory for temporary span storage (default: temp dir)
            max_age_hours: Maximum age of temporary files before cleanup
            debug: If True, preserve temporary files after export for debugging
        """
        self.exporter = exporter
        self.max_age_hours = max_age_hours
        self.debug = debug

        # Setup storage directory
        if storage_dir is None:
            # Use system temp directory with a subdirectory for our spans
            base_temp = Path(tempfile.gettempdir())
            self.storage_dir = base_temp / "cursor_otel_spans"
        else:
            self.storage_dir = storage_dir

        self.storage_dir.mkdir(parents=True, exist_ok=True)
        logger.info(
            f"GenerationBatchingProcessor initialized with storage: {self.storage_dir}"
        )
        if self.debug:
            logger.info(f"Debug mode enabled - temporary files will be preserved")

        # Track if we're shutting down
        self._shutdown = False

    def on_start(
        self, span: ReadableSpan, parent_context: Optional[Context] = None
    ) -> None:
        """Called when a span starts - no action needed."""
        pass

    def on_end(self, span: ReadableSpan) -> None:
        """
        Called when a span ends. Store it in a temporary file by generation_id.
        """
        if self._shutdown:
            logger.warning("Processor is shutdown, ignoring span")
            return

        try:
            # Extract generation_id from span attributes
            generation_id = None
            if span.attributes:
                generation_id = span.attributes.get("langsmith.metadata.generation_id")

            if not generation_id:
                logger.warning(
                    "Span has no generation_id, cannot batch. Exporting immediately."
                )
                # If no generation_id, export immediately as fallback
                self.exporter.export([span])
                return

            # Store span in temporary file
            span_file = self.storage_dir / f"{generation_id}.jsonl"
            self._store_span(generation_id, span)
            logger.info(
                f"Span queued: {span.name} -> {span_file} (generation: {generation_id[:16]}...)"
            )

        except Exception as e:
            logger.error(f"Error storing span: {e}", exc_info=True)

    def _store_span(self, generation_id: str, span: ReadableSpan) -> None:
        """Store a span in the temporary file for this generation."""
        span_file = self.storage_dir / f"{generation_id}.jsonl"

        # Convert span to storable format
        span_data = self._span_to_dict(span)

        # Append to file with file locking (in case of concurrent access)
        try:
            with open(span_file, "a", encoding="utf-8") as f:
                # Acquire exclusive lock
                lock_file(f, exclusive=True)
                try:
                    f.write(json.dumps(span_data, default=str) + "\n")
                    f.flush()
                finally:
                    # Release lock
                    unlock_file(f)
        except Exception as e:
            logger.error(f"Failed to write span to {span_file}: {e}")
            raise

    def _span_to_dict(self, span: ReadableSpan) -> dict:
        """
        Convert a ReadableSpan to OTLP JSON format for storage.

        This matches the format expected by OTLP/JSON protocol.
        """
        ctx = span.get_span_context()

        # Format IDs as hex strings
        trace_id = format(ctx.trace_id, "032x")
        span_id = format(ctx.span_id, "016x")
        parent_span_id = format(span.parent.span_id, "016x") if span.parent else None

        # Build OTLP span structure
        otlp_span = {
            "traceId": trace_id,
            "spanId": span_id,
            "name": span.name,
            "kind": self._encode_span_kind(span.kind),
            "startTimeUnixNano": str(span.start_time),
            "endTimeUnixNano": str(span.end_time),
            "attributes": self._encode_attributes(span.attributes or {}),
            "status": self._encode_status(span.status),
        }

        if parent_span_id:
            otlp_span["parentSpanId"] = parent_span_id

        # Add events if present
        if span.events:
            otlp_span["events"] = [self._encode_event(event) for event in span.events]

        # Store resource attributes separately
        otlp_span["_resource"] = dict(span.resource.attributes) if span.resource else {}

        return otlp_span

    def _encode_span_kind(self, kind: SpanKind) -> int:
        """Convert SpanKind to OTLP integer."""
        kind_map = {
            SpanKind.INTERNAL: 1,
            SpanKind.SERVER: 2,
            SpanKind.CLIENT: 3,
            SpanKind.PRODUCER: 4,
            SpanKind.CONSUMER: 5,
        }
        return kind_map.get(kind, 0)  # 0 = UNSPECIFIED

    def _encode_attributes(self, attributes: Dict[str, Any]) -> list:
        """Convert attributes to OTLP JSON format."""
        otlp_attrs = []

        for key, value in attributes.items():
            attr = {"key": key}

            # Encode value based on type
            if isinstance(value, bool):
                attr["value"] = {"boolValue": value}
            elif isinstance(value, int):
                attr["value"] = {"intValue": str(value)}
            elif isinstance(value, float):
                attr["value"] = {"doubleValue": value}
            elif isinstance(value, str):
                attr["value"] = {"stringValue": value}
            elif isinstance(value, (list, tuple)):
                attr["value"] = {"stringValue": str(value)}
            else:
                attr["value"] = {"stringValue": str(value)}

            otlp_attrs.append(attr)

        return otlp_attrs

    def _encode_status(self, status) -> Dict[str, Any]:
        """Encode span status to OTLP JSON format."""
        if status is None:
            return {"code": 0}  # UNSET

        status_code_map = {
            StatusCode.UNSET: 0,
            StatusCode.OK: 1,
            StatusCode.ERROR: 2,
        }

        otlp_status = {"code": status_code_map.get(status.status_code, 0)}

        if status.description:
            otlp_status["message"] = status.description

        return otlp_status

    def _encode_event(self, event) -> Dict[str, Any]:
        """Encode a span event to OTLP JSON format."""
        otlp_event = {
            "timeUnixNano": str(event.timestamp),
            "name": event.name,
        }

        if event.attributes:
            otlp_event["attributes"] = self._encode_attributes(event.attributes)

        return otlp_event

    def flush_generation(
        self, generation_id: str, service_name: str = "cursor-agent"
    ) -> bool:
        """
        Flush all spans for a given generation_id to the exporter.

        Args:
            generation_id: The generation ID to flush
            service_name: Service name for the resource

        Returns:
            True if successful, False otherwise
        """
        span_file = self.storage_dir / f"{generation_id}.jsonl"

        if not span_file.exists():
            logger.info(f"No spans found for generation {generation_id}")
            return True

        try:
            logger.info(f"Flushing batch for generation: {generation_id[:16]}...")
            flush_start = time.time()

            # Read all spans from file
            spans_data = []
            resource_attrs = {}
            line_count = 0

            with open(span_file, "r", encoding="utf-8") as f:
                # Acquire shared lock for reading
                lock_file(f, exclusive=False)
                try:
                    for line in f:
                        if line.strip():
                            span_data = json.loads(line)
                            # Extract and merge resource attributes
                            if "_resource" in span_data:
                                resource_attrs.update(span_data.pop("_resource"))
                            spans_data.append(span_data)
                            line_count += 1
                finally:
                    unlock_file(f)

            if not spans_data:
                logger.warning(f"No valid spans found in {span_file}")
                span_file.unlink()
                return True

            # Log temp file statistics
            file_size = span_file.stat().st_size
            logger.info(
                f"Temp storage: {span_file} ({file_size} bytes, {line_count} spans)"
            )

            logger.info(f"Batch contains {len(spans_data)} spans from {span_file}")

            # Build complete OTLP JSON payload
            otlp_payload = self._build_otlp_payload(
                spans_data, service_name, resource_attrs
            )

            # Export via the exporter
            result = self._export_otlp_payload(otlp_payload)

            if result == SpanExportResult.SUCCESS:
                logger.info(f"Batch export successful: {len(spans_data)} spans")
                flush_duration_ms = (time.time() - flush_start) * 1000
                logger.info(
                    f"Flush complete: {len(spans_data)} spans exported in {flush_duration_ms:.0f}ms"
                )

                # Delete the temporary file unless debug mode is enabled
                if self.debug:
                    logger.info(f"Debug mode: Preserving temporary file {span_file}")
                else:
                    span_file.unlink()
                    logger.debug(f"Deleted temporary file {span_file}")

                return True
            else:
                logger.error(f"Failed to export spans for generation {generation_id}")
                return False

        except Exception as e:
            logger.error(
                f"Error flushing generation {generation_id}: {e}", exc_info=True
            )
            return False

    def _build_otlp_payload(
        self, spans: list, service_name: str, resource_attrs: dict
    ) -> dict:
        """Build a complete OTLP JSON payload from stored spans."""
        # Merge resource attributes with service name
        resource_attributes = [
            {"key": "service.name", "value": {"stringValue": service_name}}
        ]

        # Add any other resource attributes
        for key, value in resource_attrs.items():
            if key != "service.name":  # Don't duplicate
                attr = {"key": key}
                if isinstance(value, str):
                    attr["value"] = {"stringValue": value}
                elif isinstance(value, int):
                    attr["value"] = {"intValue": str(value)}
                elif isinstance(value, float):
                    attr["value"] = {"doubleValue": value}
                elif isinstance(value, bool):
                    attr["value"] = {"boolValue": value}
                else:
                    attr["value"] = {"stringValue": str(value)}
                resource_attributes.append(attr)

        return {
            "resourceSpans": [
                {
                    "resource": {"attributes": resource_attributes},
                    "scopeSpans": [
                        {"scope": {"name": "cursor_otel_hook"}, "spans": spans}
                    ],
                }
            ]
        }

    def _export_otlp_payload(self, otlp_payload: dict) -> SpanExportResult:
        """
        Export OTLP JSON payload directly to the exporter.

        This works with our custom JSON exporter that has export_otlp_json method.
        """
        # Check if exporter supports direct OTLP JSON export
        if hasattr(self.exporter, "export_otlp_json"):
            return self.exporter.export_otlp_json(otlp_payload)

        # Otherwise, log the payload for debugging
        logger.warning(
            "Exporter doesn't support export_otlp_json. Cannot export batched spans."
        )
        logger.debug(f"OTLP payload: {json.dumps(otlp_payload, indent=2)}")

        return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        """Shutdown the processor and cleanup."""
        if self._shutdown:
            return

        logger.info("Shutting down GenerationBatchingProcessor")
        self._shutdown = True

        # Cleanup old temporary files
        self._cleanup_old_files()

        # Shutdown exporter
        try:
            self.exporter.shutdown()
        except Exception as e:
            logger.error(f"Error shutting down exporter: {e}")

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """
        Force flush is not supported in batching mode.
        Spans are only flushed when 'stop' event is received.
        """
        logger.debug(
            "force_flush called but batching processor only flushes on 'stop' event"
        )
        return True

    def _cleanup_old_files(self) -> None:
        """Remove temporary files older than max_age_hours."""
        try:
            current_time = time.time()
            max_age_seconds = self.max_age_hours * 3600

            for span_file in self.storage_dir.glob("*.jsonl"):
                file_age = current_time - span_file.stat().st_mtime
                if file_age > max_age_seconds:
                    logger.info(f"Removing old temporary file: {span_file}")
                    span_file.unlink()
        except Exception as e:
            logger.error(f"Error cleaning up old files: {e}", exc_info=True)

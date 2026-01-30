"""
Custom OTLP JSON Exporter for HTTP/JSON protocol.

This exporter implements the OTLP/HTTP JSON specification for sending
traces to OTLP collectors that require JSON format.
"""

import json
import logging
import time
from typing import Any, Dict, Optional, Sequence

import requests
from requests.exceptions import ConnectionError

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace import SpanKind, StatusCode

logger = logging.getLogger(__name__)


class OTLPJSONSpanExporter(SpanExporter):
    """Custom OTLP Span Exporter that sends JSON over HTTP."""

    def __init__(
        self,
        endpoint: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 10.0,
        service_name: str = "cursor-agent",
    ):
        """
        Initialize the JSON exporter.

        Args:
            endpoint: The OTLP endpoint URL (should include /v1/traces)
            headers: Optional HTTP headers to include
            timeout: Request timeout in seconds
            service_name: Service name for the resource
        """
        self.endpoint = endpoint
        self.timeout = timeout
        self.service_name = service_name

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

        if headers:
            self.session.headers.update(headers)
            logger.info(f"Session headers updated with keys: {list(headers.keys())}")

        self._shutdown = False
        logger.info(f"Initialized OTLP JSON exporter for endpoint: {endpoint}")

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        """Export spans in OTLP JSON format."""
        if self._shutdown:
            logger.warning("Exporter already shutdown, ignoring batch")
            return SpanExportResult.FAILURE

        try:
            # Convert spans to OTLP JSON format
            otlp_json = self._encode_spans(spans)

            # Log the complete OTLP trace payload
            logger.info(f"Sending {len(spans)} spans to {self.endpoint}")
            logger.debug(
                f"Complete OTLP JSON trace payload:\n{json.dumps(otlp_json, indent=2)}"
            )

            try:
                resp = self.session.post(
                    url=self.endpoint,
                    json=otlp_json,
                    timeout=self.timeout,
                )
            except ConnectionError:
                # Retry once on connection error
                logger.warning("Connection error, retrying...")
                resp = self.session.post(
                    url=self.endpoint,
                    json=otlp_json,
                    timeout=self.timeout,
                )

            if resp.ok:
                logger.info(
                    f"Export successful: {len(spans)} spans (HTTP {resp.status_code})"
                )
                return SpanExportResult.SUCCESS
            else:
                logger.error(
                    f"Export failed: HTTP {resp.status_code} - {resp.text[:500]}"
                )
                return SpanExportResult.FAILURE

        except Exception as e:
            logger.error(f"Error exporting spans: {e}", exc_info=True)
            return SpanExportResult.FAILURE

    def _encode_spans(self, spans: Sequence[ReadableSpan]) -> Dict[str, Any]:
        """
        Encode spans to OTLP JSON format.

        See: https://github.com/open-telemetry/opentelemetry-proto/blob/main/opentelemetry/proto/trace/v1/trace.proto
        """
        resource_spans = []

        if not spans:
            return {"resourceSpans": resource_spans}

        # Group spans by resource (for now, assume all spans have same resource)
        scope_spans = []

        for span in spans:
            otlp_span = self._encode_span(span)
            scope_spans.append(otlp_span)

        # Create resource attributes
        resource_attributes = [
            {"key": "service.name", "value": {"stringValue": self.service_name}}
        ]

        resource_spans.append(
            {
                "resource": {"attributes": resource_attributes},
                "scopeSpans": [
                    {"scope": {"name": "cursor_otel_hook"}, "spans": scope_spans}
                ],
            }
        )

        return {"resourceSpans": resource_spans}

    def _encode_span(self, span: ReadableSpan) -> Dict[str, Any]:
        """Encode a single span to OTLP JSON format."""
        ctx = span.get_span_context()

        # Format trace_id and span_id as hex strings
        trace_id = format(ctx.trace_id, "032x")
        span_id = format(ctx.span_id, "016x")
        parent_span_id = format(span.parent.span_id, "016x") if span.parent else None

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
                # Array values - convert to string for simplicity
                attr["value"] = {"stringValue": str(value)}
            else:
                # Fallback to string representation
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

    def shutdown(self):
        """Shutdown the exporter."""
        if self._shutdown:
            logger.warning("Exporter already shutdown, ignoring call")
            return

        self._shutdown = True
        self.session.close()
        logger.info("OTLP JSON exporter shutdown complete")

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """Nothing is buffered in this exporter, so this method does nothing."""
        return True

    def export_otlp_json(self, otlp_payload: Dict[str, Any]) -> SpanExportResult:
        """
        Export a pre-formatted OTLP JSON payload.

        This method is used by the GenerationBatchingProcessor to send
        batched spans that are already in OTLP JSON format.

        Args:
            otlp_payload: Complete OTLP JSON payload with resourceSpans

        Returns:
            SpanExportResult indicating success or failure
        """
        if self._shutdown:
            logger.warning("Exporter already shutdown, ignoring batch")
            return SpanExportResult.FAILURE

        try:
            logger.info(f"Sending batched OTLP JSON payload to {self.endpoint}")
            logger.debug(f"Payload: {json.dumps(otlp_payload, indent=2)}")

            try:
                resp = self.session.post(
                    url=self.endpoint,
                    json=otlp_payload,
                    timeout=self.timeout,
                )
            except ConnectionError:
                # Retry once on connection error
                logger.warning("Connection error, retrying...")
                resp = self.session.post(
                    url=self.endpoint,
                    json=otlp_payload,
                    timeout=self.timeout,
                )

            if resp.ok:
                span_count = sum(
                    len(scope_span.get("spans", []))
                    for rs in otlp_payload.get("resourceSpans", [])
                    for scope_span in rs.get("scopeSpans", [])
                )
                logger.info(
                    f"Export successful: {span_count} spans (HTTP {resp.status_code})"
                )
                return SpanExportResult.SUCCESS
            else:
                logger.error(
                    f"Export failed: HTTP {resp.status_code} - {resp.text[:500]}"
                )
                return SpanExportResult.FAILURE

        except Exception as e:
            logger.error(f"Error exporting batched spans: {e}", exc_info=True)
            return SpanExportResult.FAILURE

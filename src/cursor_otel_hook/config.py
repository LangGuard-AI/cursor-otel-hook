"""Configuration management for Cursor OTEL Hook"""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class OTELConfig:
    """OpenTelemetry configuration"""

    endpoint: str
    service_name: str
    insecure: bool = False
    headers: Optional[dict] = None
    mask_prompts: bool = False
    timeout: int = 30
    protocol: str = "grpc"  # "grpc", "http/protobuf", or "http/json"

    @classmethod
    def from_env(cls) -> "OTELConfig":
        """Load configuration from environment variables"""
        protocol = os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc").lower()

        # Normalize protocol values - keep http/json and http/protobuf distinct
        if protocol == "http":
            protocol = "http/protobuf"  # Default HTTP to protobuf
        elif protocol not in ["grpc", "http/protobuf", "http/json"]:
            protocol = "grpc"  # Default to grpc for unknown values

        return cls(
            endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"),
            service_name=os.getenv("OTEL_SERVICE_NAME", "cursor-agent"),
            insecure=os.getenv("OTEL_EXPORTER_OTLP_INSECURE", "true").lower() == "true",
            headers=cls._parse_headers(os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "")),
            mask_prompts=os.getenv("CURSOR_OTEL_MASK_PROMPTS", "false").lower()
            == "true",
            timeout=int(os.getenv("OTEL_EXPORTER_OTLP_TIMEOUT", "30")),
            protocol=protocol,
        )

    @classmethod
    def from_file(cls, config_path: str) -> "OTELConfig":
        """Load configuration from JSON file using OTEL standard env var names"""
        import logging

        logger = logging.getLogger(__name__)

        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(path, "r") as f:
            data = json.load(f)

        logger.debug(f"Raw config file data: {data}")

        # Support standard OTEL environment variable names in JSON
        endpoint = data.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
        service_name = data.get("OTEL_SERVICE_NAME", "cursor-agent")
        protocol = data.get("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc").lower()
        insecure = (
            str(data.get("OTEL_EXPORTER_OTLP_INSECURE", "true")).lower() == "true"
        )
        headers = data.get("OTEL_EXPORTER_OTLP_HEADERS")
        mask_prompts = (
            str(data.get("CURSOR_OTEL_MASK_PROMPTS", "false")).lower() == "true"
        )
        timeout = int(data.get("OTEL_EXPORTER_OTLP_TIMEOUT", "30"))

        logger.debug(
            f"Parsed values - endpoint: {endpoint}, protocol: {protocol}, headers: {headers}"
        )

        # Parse headers if it's a string (same format as env var)
        if isinstance(headers, str):
            headers = cls._parse_headers(headers)

        # Normalize protocol values - keep http/json and http/protobuf distinct
        logger.debug(f"Protocol before normalization: '{protocol}'")
        if protocol == "http":
            protocol = "http/protobuf"  # Default HTTP to protobuf
            logger.debug("Normalized 'http' to 'http/protobuf'")
        elif protocol not in ["grpc", "http/protobuf", "http/json"]:
            logger.debug(f"Unknown protocol '{protocol}', defaulting to 'grpc'")
            protocol = "grpc"
        logger.debug(f"Protocol after normalization: '{protocol}'")

        return cls(
            endpoint=endpoint,
            service_name=service_name,
            insecure=insecure,
            headers=headers,
            mask_prompts=mask_prompts,
            timeout=timeout,
            protocol=protocol,
        )

    @classmethod
    def load(cls, config_file: Optional[str] = None) -> "OTELConfig":
        """
        Load configuration with precedence:
        1. Config file (if provided)
        2. Environment variables
        """
        if config_file:
            try:
                config = cls.from_file(config_file)
            except FileNotFoundError:
                logger.warning(
                    f"Config file not found: {config_file}, falling back to environment variables"
                )
                config = cls.from_env()
            except Exception as e:
                logger.error(f"Error loading config file: {e}")
                raise
        else:
            config = cls.from_env()

        if not cls._is_valid_endpoint(config.endpoint):
            logger.warning(f"Endpoint URL may be malformed: {config.endpoint}")

        logger.info(
            f"Configuration loaded: endpoint={config.endpoint}, "
            f"protocol={config.protocol}, service={config.service_name}"
        )
        logger.info(f"Auth headers configured: {bool(config.headers)}")

        return config

    @staticmethod
    def _is_valid_endpoint(endpoint: str) -> bool:
        """Check if endpoint URL is well-formed (starts with http:// or https://)"""
        return endpoint.startswith("http://") or endpoint.startswith("https://")

    @staticmethod
    def _parse_headers(headers_str: str) -> Optional[dict]:
        """Parse OTEL headers from string format: key1=value1,key2=value2"""
        if not headers_str:
            return None

        headers = {}
        for pair in headers_str.split(","):
            if "=" in pair:
                key, value = pair.split("=", 1)
                headers[key.strip()] = value.strip()

        return headers if headers else None

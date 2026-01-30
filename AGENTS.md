# AGENTS.md - Cursor OTEL Hook

## Project Overview

Python OpenTelemetry integration for Cursor IDE hooks. Captures agent activity and exports traces to OTEL-compliant receivers. Uses LangSmith/GenAI semantic conventions for observability platforms.

## Quick Reference

```bash
# Setup
./setup.sh                      # Unix/macOS setup
python -m venv venv && source venv/bin/activate
pip install -e ".[dev]"         # Install with dev dependencies

# Development
black src/                      # Format code
mypy src/                       # Type check
pytest tests/                   # Run tests
pytest tests/test_foo.py        # Single test file
pytest tests/test_foo.py::test_name  # Single test function

# Manual testing
echo '{"hook_event_name":"test"}' | python -m cursor_otel_hook --debug
```

## Project Structure

```
src/cursor_otel_hook/
├── __init__.py          # Package init, version
├── __main__.py          # Entry point for -m invocation
├── config.py            # OTELConfig dataclass, config loading
├── hook_receiver.py     # Main CursorHookProcessor, CLI
├── privacy.py           # Data masking utilities
├── batching_processor.py # Generation-based span batching
├── context_manager.py   # Cross-process span relationships
└── json_exporter.py     # Custom OTLP/JSON exporter
```

## Code Style Guidelines

### Python Version
- Target Python 3.8+ (oldest supported version)
- Use features available in 3.8 (walrus operator OK, but no 3.10+ match statements)

### Formatting (Black)
- **Line length**: 100 characters
- **Quotes**: Double quotes for strings (Black default)
- Run `black src/` before committing

### Type Hints (Required)
```python
from typing import Optional, Dict, Any, Sequence, List

def process_hook(self, hook_data: Dict[str, Any]) -> Dict[str, Any]:
    """Process a hook event and create OTEL spans."""
    ...

def mask_email(email: str) -> str:
    """Mask email while preserving domain."""
    ...
```

### Imports Order
1. Standard library (`import json`, `from typing import ...`)
2. Third-party (`from opentelemetry import trace`)
3. Local imports (`from .config import OTELConfig`)

```python
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

from .config import OTELConfig
from .privacy import mask_sensitive_data
```

### Docstrings
Use triple-quoted docstrings for all public functions and classes:

```python
def _encode_span(self, span: ReadableSpan) -> Dict[str, Any]:
    """
    Encode a single span to OTLP JSON format.
    
    Args:
        span: The OpenTelemetry span to encode
        
    Returns:
        Dictionary in OTLP JSON format
    """
```

### Dataclasses
Use `@dataclass` for configuration and data containers:

```python
from dataclasses import dataclass

@dataclass
class OTELConfig:
    """OpenTelemetry configuration"""
    endpoint: str
    service_name: str
    insecure: bool = False
    headers: Optional[dict] = None
```

### Logging
- Use module-level logger: `logger = logging.getLogger(__name__)`
- Log levels: DEBUG for verbose, INFO for operations, WARNING for recoverable issues, ERROR for failures

```python
logger = logging.getLogger(__name__)

logger.debug(f"Processing span: {span.name}")
logger.info(f"Exported {len(spans)} spans")
logger.warning(f"Config file not found, using defaults")
logger.error(f"Failed to export: {e}", exc_info=True)
```

### Error Handling
- Catch specific exceptions when possible
- Log errors with context before re-raising
- Use `exc_info=True` for stack traces in error logs

```python
try:
    config = OTELConfig.from_file(config_path)
except FileNotFoundError:
    logger.warning(f"Config not found: {config_path}, using env vars")
    config = OTELConfig.from_env()
except Exception as e:
    logger.error(f"Error loading config: {e}", exc_info=True)
    raise
```

### Naming Conventions
- **Classes**: PascalCase (`CursorHookProcessor`, `OTELConfig`)
- **Functions/Methods**: snake_case (`process_hook`, `_encode_span`)
- **Private methods**: Leading underscore (`_add_common_attributes`)
- **Constants**: SCREAMING_SNAKE_CASE at module level only
- **Variables**: snake_case (`span_data`, `hook_event`)

### Platform Compatibility
Handle Windows vs Unix differences explicitly:

```python
if sys.platform == 'win32':
    import msvcrt
    def lock_file(file_handle, exclusive=True):
        msvcrt.locking(...)
else:
    import fcntl
    def lock_file(file_handle, exclusive=True):
        fcntl.flock(...)
```

## Type Checking (mypy)

Configuration in `pyproject.toml`:
```toml
[tool.mypy]
python_version = "3.8"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
```

**Rules**:
- All function parameters and return types must be annotated
- Use `Optional[T]` for nullable types, not `T | None` (3.10+)
- Use `Dict`, `List`, `Tuple` from typing, not built-in generics (3.8 compat)

## Testing

Tests go in `tests/` directory. Use pytest:

```python
# tests/test_config.py
import pytest
from cursor_otel_hook.config import OTELConfig

def test_config_from_env(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://test:4317")
    config = OTELConfig.from_env()
    assert config.endpoint == "http://test:4317"

def test_config_defaults():
    config = OTELConfig(endpoint="http://localhost:4317", service_name="test")
    assert config.protocol == "grpc"
    assert config.insecure is False
```

## Key Concepts

### Hook Events
The processor handles these Cursor IDE events:
- `sessionStart/sessionEnd` - Agent session lifecycle
- `preToolUse/postToolUse/postToolUseFailure` - Tool execution
- `beforeShellExecution/afterShellExecution` - Shell commands
- `beforeMCPExecution/afterMCPExecution` - MCP protocol calls
- `beforeReadFile/afterFileEdit` - File operations
- `beforeSubmitPrompt` - User prompt submission
- `subagentStart/subagentStop` - Subagent activities
- `stop` - Agent completion (triggers batch flush)

### Span Attributes
Uses LangSmith/GenAI conventions:
- `langsmith.trace.session_id` - Conversation ID
- `langsmith.span.id/parent_id` - Span relationships
- `gen_ai.tool.name/arguments` - Tool information
- `gen_ai.prompt.0.content` - User prompts

### Batching (HTTP/JSON mode)
When `OTEL_EXPORTER_OTLP_PROTOCOL=http/json`:
- Spans stored in temp files by `generation_id`
- Batch exported on `stop` event
- Context manager tracks parent-child relationships across processes

## Dependencies

Core:
- `opentelemetry-api>=1.20.0`
- `opentelemetry-sdk>=1.20.0`
- `opentelemetry-exporter-otlp>=1.20.0`

Dev:
- `pytest>=7.0.0`
- `black>=23.0.0`
- `mypy>=1.0.0`

## Common Patterns

### Adding a New Hook Event
1. Add handler in `_add_event_specific_attributes()` in `hook_receiver.py`
2. Update `_map_event_to_operation()` and `_map_event_to_span_kind()`
3. If it affects parent-child relationships, update `context_manager.py`

### Adding Configuration Options
1. Add field to `OTELConfig` dataclass in `config.py`
2. Parse from env in `from_env()` classmethod
3. Parse from JSON in `from_file()` classmethod
4. Document the new env var in README.md

### Privacy/Masking
Add sensitive fields to `sensitive_fields` list in `privacy.py`:
```python
sensitive_fields = [
    "prompt", "user_message", "tool_input", ...
]
```

## Git Workflow

- No pre-commit hooks configured
- Run `black src/` and `mypy src/` before committing
- Test manually with debug flag: `--debug`

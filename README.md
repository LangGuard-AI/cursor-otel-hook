# Cursor OpenTelemetry Hook

An easy-to-deploy Python-based OpenTelemetry integration for Cursor IDE that captures agent activity and exports detailed traces to any OTEL-compliant receiver.

## Features

- **LangGuard/LangSmith/LangChain Compatible**: Uses official GenAI semantic conventions and LangSmith attribute mappings for seamless integration with:
  - **LangGuard** - LangGuard's AI Control Plane
  - **Langfuse** - Open-source LLM observability
  - Any OTLP backend

- **Comprehensive Tracing**: Captures all Cursor IDE hook events including:
  - Session lifecycle (start/end)
  - Tool usage (pre/post/failure)
  - Shell command execution
  - MCP (Model Context Protocol) calls
  - File operations (read/edit)
  - Prompt submissions
  - Context compaction events
  - Subagent activities

- **Generation-based Batching**: When using HTTP/JSON protocol, spans are automatically batched by generation_id and sent as a single payload when the 'stop' event is received. This provides better trace coherence and reduces network overhead.

- **Custom JSON Exporter**: Includes a custom OTLP/JSON exporter for platforms that require JSON format
- **Privacy Controls**: Built-in data masking to protect sensitive user information
- **Flexible Configuration**: Support for both environment variables and JSON config files
- **Easy Setup**: Automated installation scripts for Windows and macOS/Linux
- **Multiple Protocols**: Supports gRPC, HTTP/Protobuf, and HTTP/JSON

## Quick Start

### Prerequisites

- Python 3.8 or higher
- Cursor IDE
- An OpenTelemetry collector or compatible backend

### Installation

#### macOS/Linux

```bash
# Clone or download this repository
cd cursor_otel_hook

# Run the setup script
./setup.sh
```

#### Windows

```powershell
# Clone or download this repository
cd cursor_otel_hook

# Run the setup script
powershell -ExecutionPolicy Bypass -File setup.ps1
```

The setup script will:
1. Create a Python virtual environment
2. Install the package and dependencies
3. Create a wrapper script in `~/.cursor/hooks/`
4. Generate default configuration files
5. Configure Cursor hooks to use the OTEL exporter

### Configuration

#### JSON Configuration File (Recommended)

The setup script creates a configuration file at `otel_config.json` in the cursor hooks directory. This is the recommended way to configure the hook as it doesn't require setting environment variables in Cursor.

The config file uses standard OTEL environment variable names as JSON keys:

```json
{
  "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317",
  "OTEL_SERVICE_NAME": "cursor-agent",
  "OTEL_EXPORTER_OTLP_PROTOCOL": "grpc",
  "OTEL_EXPORTER_OTLP_INSECURE": "true",
  "OTEL_EXPORTER_OTLP_HEADERS": null,
  "CURSOR_OTEL_MASK_PROMPTS": "false",
  "OTEL_EXPORTER_OTLP_TIMEOUT": "30"
}
```

**With Authentication:**

```json
{
  "OTEL_EXPORTER_OTLP_ENDPOINT": "https://your-collector:4317",
  "OTEL_SERVICE_NAME": "cursor-agent",
  "OTEL_EXPORTER_OTLP_PROTOCOL": "grpc",
  "OTEL_EXPORTER_OTLP_INSECURE": "false",
  "OTEL_EXPORTER_OTLP_HEADERS": {
    "authorization": "Bearer YOUR_TOKEN"
  }
}
```

**HTTP Protocol Examples:**

```json
{
  "OTEL_EXPORTER_OTLP_ENDPOINT": "http://your-collector/v1/traces",
  "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf"
}
```

**HTTP with JSON (for LangSmith/Langfuse):**

```json
{
  "OTEL_EXPORTER_OTLP_ENDPOINT": "https://api.smith.langchain.com/v1/traces",
  "OTEL_EXPORTER_OTLP_PROTOCOL": "http/json",
  "OTEL_EXPORTER_OTLP_HEADERS": {
    "Authorization": "Bearer YOUR_API_KEY"
  }
}
```

**Headers as String (Alternative):**

You can also specify headers as a comma-separated string, just like the environment variable:

```json
{
  "OTEL_EXPORTER_OTLP_ENDPOINT": "https://your-collector:4317",
  "OTEL_EXPORTER_OTLP_HEADERS": "authorization=Bearer TOKEN,x-tenant-id=123"
}
```

The wrapper script automatically uses this config file, so no environment variables are needed in Cursor.

#### Environment Variables (Alternative)

You can also configure the hook using environment variables in your cursor session:

```bash
# Required: OTEL endpoint
export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317"

# Optional: Service name (default: cursor-agent)
export OTEL_SERVICE_NAME="my-cursor-agent"

# Optional: Use insecure connection (default: true)
export OTEL_EXPORTER_OTLP_INSECURE="true"

# Optional: Custom headers (comma-separated key=value pairs)
export OTEL_EXPORTER_OTLP_HEADERS="api-key=secret123,env=production"

# Optional: Timeout in seconds (default: 30)
export OTEL_EXPORTER_OTLP_TIMEOUT="30"

# Optional: Mask user prompts for privacy (default: false)
export CURSOR_OTEL_MASK_PROMPTS="true"

# Optional: Protocol - "grpc" or "http" (default: grpc)
export OTEL_EXPORTER_OTLP_PROTOCOL="grpc"
```

**Protocol Selection:**

- **gRPC** (default): Binary protocol, most efficient
- **http/protobuf**: HTTP with protobuf encoding
- **http/json**: HTTP with JSON encoding (recommended for LangSmith/Langfuse)

```bash
# Use gRPC (default)
export OTEL_EXPORTER_OTLP_PROTOCOL="grpc"
export OTEL_EXPORTER_OTLP_ENDPOINT="http://your-collector:4317"

# Use HTTP with Protobuf
export OTEL_EXPORTER_OTLP_PROTOCOL="http/protobuf"
export OTEL_EXPORTER_OTLP_ENDPOINT="http://your-collector:4318/v1/traces"

# Use HTTP with JSON (for LangSmith/Langfuse)
export OTEL_EXPORTER_OTLP_PROTOCOL="http/json"
export OTEL_EXPORTER_OTLP_ENDPOINT="https://api.smith.langchain.com/v1/traces"
```

**Note:**
- Endpoint format depends on your OTEL collector configuration. See the [OpenTelemetry Protocol Specification](https://opentelemetry.io/docs/specs/otlp/) for details.
- When using environment variables, you must set them in your shell/system, not in Cursor's settings.
- The JSON config file approach (recommended) avoids the need to set environment variables.

## Usage

Once installed and configured, the hooks will automatically run whenever you use Cursor. The traces will be sent to your configured OTEL endpoint.

### Span Attributes

This hook uses **LangSmith/LangChain OpenTelemetry conventions** for maximum compatibility with LLM observability platforms like LangSmith, Langfuse, and other OTLP-compatible systems.

#### Common Attributes (All Spans)

**Session & Trace IDs (LangSmith convention):**
- `langsmith.trace.session_id`: Conversation identifier (from Cursor's conversation_id)
- `langsmith.trace.id`: OpenTelemetry trace ID (derived from span context, not generation_id)
- `langsmith.span.id`: OpenTelemetry span ID (derived from span context)
- `langsmith.span.parent_id`: Parent span ID when applicable (derived from span context)

**Model Information (GenAI convention):**
- `gen_ai.system`: Provider name (anthropic, openai, cursor)
- `gen_ai.request.model`: AI model being used (e.g., "claude-sonnet-4-5")
- `gen_ai.response.model`: Model used in response

**Operation Type:**
- `gen_ai.operation.name`: Operation type (chat, tool, chain, session)
- `langsmith.span.kind`: Span classification (llm, tool, chain)

**Metadata:**
- `langsmith.metadata.hook_event`: Original Cursor hook event name
- `langsmith.metadata.generation_id`: Cursor's generation identifier (preserved as metadata)
- `langsmith.metadata.cursor_version`: Cursor IDE version
- `langsmith.metadata.user_email`: User email (can be masked)
- `langsmith.metadata.workspace_roots`: Project directories
- `langsmith.metadata.duration_ms`: Event duration in milliseconds

#### Event-Specific Attributes

**Prompts (GenAI convention):**
- `gen_ai.prompt.0.role`: Message role (typically "user")
- `gen_ai.prompt.0.content`: User prompt text (can be masked)

**Tool Usage (GenAI convention):**
- `gen_ai.tool.name`: Tool name (e.g., "Read", "bash", "edit_file")
- `gen_ai.tool.arguments`: Tool input parameters (JSON)
- `langsmith.metadata.tool_input`: Detailed tool input
- `langsmith.metadata.tool_output`: Tool output (truncated if large)

**Shell Execution (treated as tool):**
- `gen_ai.tool.name`: "bash"
- `gen_ai.tool.arguments`: Command in JSON format
- `langsmith.metadata.shell_command`: Command being executed
- `langsmith.metadata.shell_cwd`: Working directory
- `langsmith.metadata.shell_exit_code`: Command exit code

**MCP Calls (treated as tool):**
- `gen_ai.tool.name`: Format: "{server}.{tool}"
- `gen_ai.tool.arguments`: MCP call parameters (JSON)
- `langsmith.metadata.mcp_server`: MCP server name

**File Operations (treated as tool):**
- `gen_ai.tool.name`: "read_file" or "edit_file"
- `gen_ai.tool.arguments`: File path in JSON format
- `langsmith.metadata.file_path`: File being accessed
- `langsmith.metadata.edit_count`: Number of edits in operation

**Subagent Activities:**
- `langsmith.span.kind`: "chain"
- `langsmith.metadata.subagent_type`: Type of subagent
- `langsmith.metadata.subagent_task`: Task description

## Generation-based Span Batching

When using the `http/json` protocol, the hook automatically implements generation-based batching to improve trace coherence and reduce network overhead.

### How It Works

1. **Span Storage**: As each hook event is processed, spans are converted to OTLP JSON format and stored in temporary files, grouped by `generation_id`.

2. **Temporary Files**: Spans are stored in `{temp_dir}/cursor_otel_spans/{generation_id}.jsonl`, where each line is a JSON-formatted span.

3. **Batched Export**: When a 'stop' hook event is received for a generation_id, all stored spans for that generation are:
   - Read from the temporary file
   - Combined into a single OTLP JSON payload
   - Sent as one request to the OTEL receiver
   - The temporary file is deleted after successful export

4. **Automatic Cleanup**: Temporary files older than 24 hours are automatically removed to prevent disk accumulation.

### Parent-Child Span Relationships

The hook automatically maintains proper parent-child relationships between spans across process invocations:

**Span Hierarchy:**
- **Root Spans**: `sessionStart`, `beforeSubmitPrompt` (start new trace contexts)
- **Session Children**: `subagentStart`, tool events (when not in subagent)
- **Subagent Children**: Tool events during subagent execution
- **Tool Children**: `postToolUse`, `postToolUseFailure`, `afterShellExecution`, `afterMCPExecution`, `afterFileEdit` (children of their corresponding start events)

**Context Management:**
Context is persisted across process invocations using temporary files (`{temp_dir}/cursor_otel_context/{generation_id}_context.json`):
- Tracks current session span, subagent span, and tool span
- Each hook event looks up its appropriate parent span
- Proper parent span_id is set when creating child spans
- Context is cleaned up after the 'stop' event

**Example Trace Structure:**
```
sessionStart (root)
├── subagentStart (child of session)
│   ├── preToolUse: Read (child of subagent)
│   │   └── postToolUse: Read (child of tool)
│   ├── preToolUse: Edit (child of subagent)
│   │   └── postToolUse: Edit (child of tool)
│   └── subagentStop (child of subagent)
└── stop (child of session)
```

### Benefits

- **Better Trace Coherence**: All spans for a single generation are sent together, making it easier for trace backends to assemble complete traces
- **Proper Parent-Child Relationships**: Spans correctly reference their parent spans, even across separate process invocations
- **Reduced Network Overhead**: Instead of N individual requests (one per span), only one batched request is sent per generation
- **Improved Reliability**: If a span export fails, it doesn't affect the storage of other spans
- **Correct ID Derivation**: All spans maintain proper OpenTelemetry trace_id, span_id, and parent_span_id relationships

### Requirements

- Only available when using `OTEL_EXPORTER_OTLP_PROTOCOL="http/json"`
- For other protocols (gRPC, http/protobuf), spans are sent immediately using standard BatchSpanProcessor (without cross-process parent-child relationships)

## Privacy and Security

### Data Masking

When `CURSOR_OTEL_MASK_PROMPTS=true`, the following fields are masked:

- User prompts and messages
- Tool inputs and outputs
- File paths (username components)
- Email addresses (partially masked)
- Command line arguments

### What Gets Sent

By default, the hook sends:
- Timing information (durations, timestamps)
- Model and tool names
- Event types and status
- File paths and commands (unless masked)
- Conversation IDs, generation IDs (as metadata), and OpenTelemetry trace/span IDs

The hook **never** sends:
- API keys or authentication tokens (automatically filtered)
- File contents
- Raw code (only metadata)

## OpenTelemetry Backends

This hook works with any OpenTelemetry-compliant backend using either gRPC or HTTP protocols.

**For detailed OTLP protocol information, see:**
- [OpenTelemetry Protocol Specification](https://opentelemetry.io/docs/specs/otlp/)
- [OTLP Exporter Configuration](https://opentelemetry.io/docs/languages/sdk-configuration/otlp-exporter/)

### Local Development with Jaeger

```bash
# Run Jaeger all-in-one (supports both gRPC and HTTP)
docker run -d --name jaeger \
  -p 4317:4317 \
  -p 4318:4318 \
  -p 16686:16686 \
  jaegertracing/all-in-one:latest

# Configure the hook (gRPC default)
export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317"

# Or use HTTP protocol
export OTEL_EXPORTER_OTLP_PROTOCOL="http"
export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4318/v1/traces"

# View traces at http://localhost:16686
```

**Note:** Check your backend's documentation for the correct endpoint URL and required headers. Each provider may have different requirements.

## Hook Events Reference

| Event | When Triggered | Attributes |
|-------|---------------|------------|
| `sessionStart` | Agent session begins | session_id, composer_mode |
| `sessionEnd` | Agent session ends | session_id |
| `preToolUse` | Before tool execution | tool_name, tool_input |
| `postToolUse` | After tool execution | tool_name, tool_output |
| `postToolUseFailure` | Tool execution fails | tool_name, error |
| `beforeShellExecution` | Before shell command | command, cwd |
| `afterShellExecution` | After shell command | command, exit_code |
| `beforeMCPExecution` | Before MCP call | mcp_server, mcp_tool |
| `afterMCPExecution` | After MCP call | mcp_server, mcp_tool |
| `beforeReadFile` | Before file read | file_path |
| `afterFileEdit` | After file edit | file_path, edits |
| `beforeSubmitPrompt` | Before prompt submission | prompt |
| `stop` | Agent stops | status, loop_count |
| `subagentStart` | Subagent starts | subagent_type |
| `subagentStop` | Subagent stops | subagent_type |

## Logging and Troubleshooting

### Log Files

The hook automatically logs to `~/.cursor/hooks/cursor_otel_hook.log`.

**View logs:**
```bash
# View recent entries
tail -f ~/.cursor/hooks/cursor_otel_hook.log

# Search for errors
grep ERROR ~/.cursor/hooks/cursor_otel_hook.log

# View all logs
cat ~/.cursor/hooks/cursor_otel_hook.log
```

**Enable debug logging:**

Edit the wrapper script (`~/.cursor/hooks/otel_hook.sh`) to add `--debug`:
```bash
exec cursor-otel-hook --config "/path/to/otel_config.json" --debug "$@"
```

**Debug mode features:**
- Logs detailed DEBUG-level information to the log file
- Outputs logs to stderr (visible in Cursor)
- Preserves temporary OTLP JSON files for inspection (when using http/json protocol)
  - Span files: `{temp_dir}/cursor_otel_spans/{generation_id}.jsonl`
  - Context files: `{temp_dir}/cursor_otel_context/{generation_id}_context.json`

**Without debug mode:**
- Only WARNING and ERROR messages are logged
- No stderr output
- Temporary files are automatically cleaned up after export

### Common Issues

**No traces appearing:**
1. Check log file for errors
2. Verify OTEL endpoint is reachable: `curl http://localhost:4317`
3. Ensure collector is running: `docker ps | grep jaeger`
4. Test manually: `echo '{"hook_event_name":"test"}' | cursor-otel-hook --config otel_config.json --debug`

**Hooks not firing:**
1. Check if log file is being created
2. Verify `~/.cursor/hooks.json` exists
3. Restart Cursor IDE
4. Test wrapper script: `echo '{"hook_event_name":"test"}' | ~/.cursor/hooks/otel_hook.sh`

**Connection errors:**
- For gRPC: Ensure port 4317 is accessible
- For HTTP: Ensure endpoint URL is correct
- Try switching protocols (gRPC ↔ HTTP)

**For detailed troubleshooting, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md)**

## Customization

### Custom Hook Logic

To add custom logic (e.g., blocking certain operations), extend the `CursorHookProcessor` class:

```python
from cursor_otel_hook.hook_receiver import CursorHookProcessor

class CustomProcessor(CursorHookProcessor):
    def _generate_response(self, event, hook_data):
        # Block git commands
        if event == "beforeShellExecution":
            command = hook_data.get("command", "")
            if "git" in command:
                return {
                    "permission": "deny",
                    "user_message": "Git commands are blocked"
                }

        return super()._generate_response(event, hook_data)
```

### Selective Hook Registration

Edit `~/.cursor/hooks.json` to register hooks for only specific events:

```json
{
  "version": 1,
  "hooks": {
    "sessionStart": [{"command": "~/.cursor/hooks/otel_hook.sh", "timeout": 5}],
    "sessionEnd": [{"command": "~/.cursor/hooks/otel_hook.sh", "timeout": 5}],
    "preToolUse": [{"command": "~/.cursor/hooks/otel_hook.sh", "timeout": 5}],
    "postToolUse": [{"command": "~/.cursor/hooks/otel_hook.sh", "timeout": 5}]
  }
}
```

## Troubleshooting

### Hooks Not Running

1. Check if hooks are enabled in Cursor settings
2. Verify the wrapper script is executable: `chmod +x ~/.cursor/hooks/otel_hook.sh`
3. Check Cursor logs for hook errors
4. Test manually: `echo '{"hook_event_name":"test"}' | ~/.cursor/hooks/otel_hook.sh`

### No Traces Appearing

1. Verify OTEL endpoint is reachable: `curl http://localhost:4317`
2. Check if the collector is running
3. Enable debug mode: `cursor-otel-hook --debug`
4. Verify network connectivity and firewall rules

### Performance Issues

1. Reduce hook registrations (only essential events)
2. Increase timeout values in `hooks.json`
3. Use a local OTEL collector instead of remote endpoint
4. Enable prompt masking to reduce payload size

## Development

### Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/

# Format code
black src/

# Type checking
mypy src/
```

### Project Structure

```
cursor_otel_hook/
├── src/
│   └── cursor_otel_hook/
│       ├── __init__.py
│       ├── config.py          # Configuration management
│       ├── hook_receiver.py   # Main hook processor
│       └── privacy.py         # Data masking utilities
├── setup.sh                   # Unix/macOS setup script
├── setup.ps1                  # Windows setup script
├── pyproject.toml            # Project metadata
├── requirements.txt          # Dependencies
└── README.md                 # This file
```

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## License

MIT License - see LICENSE file for details

## Related Projects

- [LangGuard](https://langguard.ai) - AI Control Plane
- [Cursor IDE](https://cursor.com) - AI-powered code editor
- [OpenTelemetry](https://opentelemetry.io) - Observability framework

## Support

For issues and questions:
- GitHub Issues: [Create an issue]
- Cursor Docs: https://cursor.com/docs
- OpenTelemetry Docs: https://opentelemetry.io/docs

# Quick Start Guide

Get Cursor OpenTelemetry hooks up and running in 5 minutes!

## Step 1: Install (Choose Your Platform)

### macOS/Linux

```bash
cd cursor_otel_hook
./setup.sh
```

### Windows

```powershell
cd cursor_otel_hook
powershell -ExecutionPolicy Bypass -File setup.ps1
```

## Step 2: Start a Local OTEL Backend

The easiest way is using Docker with Jaeger:

```bash
# Start Jaeger (supports both gRPC and HTTP OTLP)
docker run -d --name jaeger \
  -p 4317:4317 \
  -p 4318:4318 \
  -p 16686:16686 \
  jaegertracing/all-in-one:latest
```

Or use the included docker-compose:

```bash
cd examples
docker-compose up -d
```

## Step 3: Configure the Hook

The setup script creates a configuration file at `otel_config.json` in the project directory.

Edit this file to configure your OTEL endpoint:

```bash
# macOS/Linux
nano otel_config.json

# Windows
notepad otel_config.json
```

**Default configuration (works with local Jaeger):**
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

The keys match standard OTEL environment variable names!

**For production use, update the endpoint and add authentication:**
```json
{
  "OTEL_EXPORTER_OTLP_ENDPOINT": "https://your-collector:4317",
  "OTEL_SERVICE_NAME": "cursor-agent",
  "OTEL_EXPORTER_OTLP_PROTOCOL": "grpc",
  "OTEL_EXPORTER_OTLP_INSECURE": "false",
  "OTEL_EXPORTER_OTLP_HEADERS": {
    "authorization": "Bearer YOUR_TOKEN"
  },
  "CURSOR_OTEL_MASK_PROMPTS": "false"
}
```

## Step 4: Use with Cursor

1. **Restart Cursor IDE** to activate the hooks
2. Start coding with Claude in Cursor
3. Watch traces appear in Jaeger UI in real-time!

## Common Patterns

### Enable Privacy Mode

Edit `otel_config.json` and set `CURSOR_OTEL_MASK_PROMPTS` to `"true"`:

```json
{
  "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317",
  "CURSOR_OTEL_MASK_PROMPTS": "true"
}
```

### Use Remote OTEL Collector with Authentication

Edit `otel_config.json`:

```json
{
  "OTEL_EXPORTER_OTLP_ENDPOINT": "https://otel.yourcompany.com:4317",
  "OTEL_SERVICE_NAME": "cursor-agent",
  "OTEL_EXPORTER_OTLP_PROTOCOL": "grpc",
  "OTEL_EXPORTER_OTLP_INSECURE": "false",
  "OTEL_EXPORTER_OTLP_HEADERS": {
    "authorization": "Bearer YOUR_TOKEN",
    "x-tenant-id": "your-tenant"
  }
}
```

### Use HTTP Protocol Instead of gRPC

Edit `otel_config.json`:

```json
{
  "OTEL_EXPORTER_OTLP_ENDPOINT": "http://your-collector/v1/traces",
  "OTEL_EXPORTER_OTLP_PROTOCOL": "http",
  "OTEL_EXPORTER_OTLP_HEADERS": {
    "Content-Type": "application/json"
  }
}
```

### Track Only Specific Events

Edit `~/.cursor/hooks.json` and keep only the events you want:

```json
{
  "version": 1,
  "hooks": {
    "sessionStart": [{"command": "~/.cursor/hooks/otel_hook.sh", "timeout": 5}],
    "sessionEnd": [{"command": "~/.cursor/hooks/otel_hook.sh", "timeout": 5}],
    "postToolUse": [{"command": "~/.cursor/hooks/otel_hook.sh", "timeout": 5}]
  }
}
```

## Troubleshooting

### Hooks not firing?

```bash
# Check the log file
tail ~/.cursor/hooks/cursor_otel_hook.log

# Test manually
echo '{"hook_event_name":"test","model":"claude"}' | ~/.cursor/hooks/otel_hook.sh
```

### No traces in Jaeger?

1. Check if Jaeger is running: `docker ps`
2. Verify endpoint: `curl http://localhost:4317`
3. Enable debug mode: `cursor-otel-hook --debug`

### Permission errors?

```bash
# Make scripts executable
chmod +x ~/.cursor/hooks/otel_hook.sh
chmod +x setup.sh
```

## What's Next?

- Read the full [README.md](README.md) for advanced configuration
- Check [examples/](examples/) for more configurations
- Customize hook behavior by extending the Python code
- Integrate with your existing observability stack

## Need Help?

- Check the full README: [README.md](README.md)
- Review Cursor hook docs: https://cursor.com/docs/agent/hooks
- OpenTelemetry docs: https://opentelemetry.io/docs

Happy tracing! 🔍

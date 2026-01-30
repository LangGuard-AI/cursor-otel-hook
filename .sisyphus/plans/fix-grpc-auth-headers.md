# Fix gRPC Auth Headers Not Being Sent

## TL;DR

> **Quick Summary**: gRPC auth headers aren't reaching the OTEL backend due to incorrect endpoint format and missing diagnostic logging. The endpoint should be `host:port` not `https://host`.
> 
> **Deliverables**: 
> - Fix endpoint format handling for gRPC
> - Add header debugging logging
> - Validate configuration on startup
> 
> **Estimated Effort**: Quick
> **Parallel Execution**: NO - sequential
> **Critical Path**: Diagnose → Fix endpoint → Add logging

---

## Context

### Original Request
User's OTEL traces aren't being sent. Config uses gRPC with Bearer auth:
```json
{
  "OTEL_EXPORTER_OTLP_ENDPOINT": "https://dev.app.langguard.ai",
  "OTEL_EXPORTER_OTLP_PROTOCOL": "grpc",
  "OTEL_EXPORTER_OTLP_INSECURE": "false",
  "OTEL_EXPORTER_OTLP_HEADERS": {
    "authorization": "Bearer lgr_hyJlhKTuohKNqL-..."
  }
}
```

### Root Causes Identified

**Issue 1: ENDPOINT FORMAT WRONG FOR gRPC**

The gRPC exporter expects `host:port` format, NOT URL format:
- **Current**: `https://dev.app.langguard.ai` ❌
- **Should be**: `dev.app.langguard.ai:443` ✅

The OpenTelemetry gRPC exporter doesn't parse URL schemes. When you pass `https://dev.app.langguard.ai`, it tries to connect to a host literally named `https://dev.app.langguard.ai` which fails.

**Issue 2: NO DIAGNOSTIC LOGGING**

When the export fails, there's no logging showing:
- What endpoint is being used
- What headers are being passed (masked)
- What the actual gRPC error is

**Issue 3: POTENTIAL HEADER CASE SENSITIVITY**

Some backends expect `Authorization` (capital A), not `authorization`. While gRPC metadata is typically case-insensitive, some middleware may be strict.

---

## Work Objectives

### Core Objective
Fix gRPC auth header delivery and add diagnostic logging to identify export failures.

### Concrete Deliverables
- Endpoint format auto-correction or validation warning
- Header presence logging (without exposing secrets)
- gRPC error logging with details

### Definition of Done
- [ ] Traces successfully reach `dev.app.langguard.ai`
- [ ] Logs show headers are being passed
- [ ] gRPC errors are clearly logged

### Must Have
- Fix/warn about gRPC endpoint format
- Log header keys (not values) being sent
- Log gRPC connection errors with details

### Must NOT Have (Guardrails)
- Do NOT log auth header values (security)
- Do NOT break HTTP protocol support
- Do NOT auto-modify user's config file

---

## Verification Strategy

### Manual Verification

**Test command:**
```bash
echo '{"hook_event_name":"test","generation_id":"test-1"}' | python -m cursor_otel_hook --debug --config ~/.cursor/hooks/otel_config.json
```

**Check logs:**
```bash
tail -100 ~/.cursor/hooks/cursor_otel_hook.log | grep -E "(header|Header|endpoint|Endpoint|gRPC|error|Error)"
```

---

## TODOs

- [ ] 1. Add gRPC endpoint format validation and auto-fix

  **What to do**:
  - In `hook_receiver.py` `_setup_tracer()`, for gRPC protocol, validate/fix endpoint:
  
  ```python
  # For gRPC protocol, ensure endpoint is in host:port format (not URL)
  if self.config.protocol == "grpc":
      endpoint = self.config.endpoint
      # Strip https:// or http:// if present - gRPC doesn't use URL schemes
      if endpoint.startswith("https://"):
          endpoint = endpoint[8:]  # Remove "https://"
          logger.warning(f"gRPC endpoint had 'https://' prefix - stripped to: {endpoint}")
          # Add default HTTPS port if no port specified
          if ":" not in endpoint:
              endpoint = f"{endpoint}:443"
              logger.info(f"Added default gRPC/TLS port: {endpoint}")
      elif endpoint.startswith("http://"):
          endpoint = endpoint[7:]  # Remove "http://"
          logger.warning(f"gRPC endpoint had 'http://' prefix - stripped to: {endpoint}")
          if ":" not in endpoint:
              endpoint = f"{endpoint}:4317"
              logger.info(f"Added default gRPC port: {endpoint}")
      
      exporter_kwargs["endpoint"] = endpoint
  ```

  **Location**: `src/cursor_otel_hook/hook_receiver.py` around line 190, in the gRPC section

  **Must NOT do**:
  - Don't modify HTTP/JSON endpoint handling (those use full URLs)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Blocks**: Task 2, 3
  - **Blocked By**: None

  **References**:
  - `src/cursor_otel_hook/hook_receiver.py:189-196` - gRPC exporter setup
  - OpenTelemetry gRPC exporter expects `host:port` format

  **Acceptance Criteria**:
  ```bash
  # With https:// endpoint, should see warning in logs
  echo '{"hook_event_name":"test"}' | python -m cursor_otel_hook --debug
  grep "stripped" ~/.cursor/hooks/cursor_otel_hook.log
  # Should show: "gRPC endpoint had 'https://' prefix - stripped to: dev.app.langguard.ai:443"
  ```

  **Commit**: YES
  - Message: `fix(grpc): auto-correct endpoint format for gRPC protocol`
  - Files: `src/cursor_otel_hook/hook_receiver.py`

---

- [ ] 2. Add auth header diagnostic logging

  **What to do**:
  - After setting up headers in `exporter_kwargs`, log what's being passed (keys only, not values):
  
  ```python
  # Log headers being used (keys only for security)
  if self.config.headers:
      header_keys = list(self.config.headers.keys())
      logger.info(f"Auth headers configured: {header_keys}")
      exporter_kwargs["headers"] = tuple(
          (k, v) for k, v in self.config.headers.items()
      )
      logger.debug(f"Headers tuple format: {[(k, '***') for k, v in self.config.headers.items()]}")
  else:
      logger.warning("No auth headers configured - requests may fail if endpoint requires authentication")
  ```

  **Location**: `src/cursor_otel_hook/hook_receiver.py` around line 141-145

  **Must NOT do**:
  - Do NOT log header values (contains Bearer token)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Blocks**: Task 3
  - **Blocked By**: Task 1

  **References**:
  - `src/cursor_otel_hook/hook_receiver.py:141-145` - Header setup

  **Acceptance Criteria**:
  ```bash
  echo '{"hook_event_name":"test"}' | python -m cursor_otel_hook --debug
  grep "Auth headers" ~/.cursor/hooks/cursor_otel_hook.log
  # Should show: "Auth headers configured: ['authorization']"
  ```

  **Commit**: YES (group with task 1)
  - Message: `fix(logging): add auth header diagnostic logging`
  - Files: `src/cursor_otel_hook/hook_receiver.py`

---

- [ ] 3. Add gRPC export error logging with details

  **What to do**:
  - Wrap the gRPC exporter in a custom wrapper that catches and logs errors:
  
  ```python
  class GRPCLoggingExporterWrapper(SpanExporter):
      """Wrapper that logs gRPC-specific errors."""
      
      def __init__(self, exporter: SpanExporter, endpoint: str):
          self.exporter = exporter
          self.endpoint = endpoint
      
      def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
          try:
              logger.info(f"Exporting {len(spans)} spans via gRPC to {self.endpoint}")
              result = self.exporter.export(spans)
              if result == SpanExportResult.SUCCESS:
                  logger.info(f"gRPC export successful: {len(spans)} spans")
              else:
                  logger.error(f"gRPC export returned non-success: {result}")
              return result
          except Exception as e:
              logger.error(f"gRPC export failed: {type(e).__name__}: {e}")
              # Log common gRPC errors with helpful messages
              error_str = str(e).lower()
              if "unavailable" in error_str:
                  logger.error(f"  -> Endpoint {self.endpoint} may be unreachable")
              if "unauthenticated" in error_str:
                  logger.error(f"  -> Auth headers may be missing or invalid")
              if "permission denied" in error_str:
                  logger.error(f"  -> Auth token may be expired or lack permissions")
              raise
      
      def shutdown(self):
          return self.exporter.shutdown()
      
      def force_flush(self, timeout_millis: int = 30000) -> bool:
          return self.exporter.force_flush(timeout_millis)
  ```

  **Location**: Add class near top of `src/cursor_otel_hook/hook_receiver.py` (after LoggingSpanExporterWrapper), and use it to wrap the gRPC exporter

  **Must NOT do**:
  - Don't suppress errors - just log and re-raise

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Blocks**: None
  - **Blocked By**: Tasks 1, 2

  **References**:
  - `src/cursor_otel_hook/hook_receiver.py:31-112` - Existing LoggingSpanExporterWrapper pattern
  - `src/cursor_otel_hook/hook_receiver.py:198-209` - Where gRPC exporter is created

  **Acceptance Criteria**:
  ```bash
  # With a bad endpoint, should see detailed error
  echo '{"hook_event_name":"stop","generation_id":"x"}' | OTEL_EXPORTER_OTLP_ENDPOINT="bad.endpoint:443" python -m cursor_otel_hook --debug
  grep -E "(gRPC export|unreachable)" ~/.cursor/hooks/cursor_otel_hook.log
  # Should show gRPC error with helpful message
  ```

  **Commit**: YES (group with tasks 1-2)
  - Message: `fix(grpc): add detailed gRPC export error logging`
  - Files: `src/cursor_otel_hook/hook_receiver.py`

---

- [ ] 4. Change default log level to INFO

  **What to do**:
  - In `hook_receiver.py` main(), change default log level from WARNING to INFO:
  
  ```python
  # Change from:
  log_level = logging.DEBUG if args.debug else logging.WARNING
  # To:
  log_level = logging.DEBUG if args.debug else logging.INFO
  ```

  **Location**: `src/cursor_otel_hook/hook_receiver.py` line 606

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - `src/cursor_otel_hook/hook_receiver.py:604-606` - Logging setup

  **Acceptance Criteria**:
  ```bash
  # Without --debug flag, should still see INFO logs
  echo '{"hook_event_name":"test"}' | python -m cursor_otel_hook
  grep "INFO" ~/.cursor/hooks/cursor_otel_hook.log | tail -5
  # Should show recent INFO entries
  ```

  **Commit**: YES (group with tasks 1-3)
  - Message: `fix(logging): change default log level to INFO`
  - Files: `src/cursor_otel_hook/hook_receiver.py`

---

## Commit Strategy

| After Tasks | Message | Files |
|-------------|---------|-------|
| 1-4 | `fix(grpc): fix auth header delivery and add diagnostic logging` | hook_receiver.py |

---

## Immediate Workaround

**While waiting for the fix, update your config to use correct gRPC endpoint format:**

```json
{
  "OTEL_EXPORTER_OTLP_ENDPOINT": "dev.app.langguard.ai:443",
  "OTEL_SERVICE_NAME": "cursor-agent",
  "OTEL_EXPORTER_OTLP_PROTOCOL": "grpc",
  "OTEL_EXPORTER_OTLP_INSECURE": "false",
  "OTEL_EXPORTER_OTLP_HEADERS": {
    "authorization": "Bearer lgr_hyJlhKTuohKNqL-s6OocUi3b25I6jGMVy6Ro0xOGHIk"
  }
}
```

**Key change**: Remove `https://` from endpoint, add port `:443`

---

## Success Criteria

### Verification Commands
```bash
# Test with corrected config
echo '{"hook_event_name":"sessionStart","generation_id":"test"}' | python -m cursor_otel_hook --debug

# Check logs for successful export
grep -E "(gRPC export|Auth headers|stripped)" ~/.cursor/hooks/cursor_otel_hook.log | tail -10
```

### Expected Log Output After Fix
```
INFO - Auth headers configured: ['authorization']
INFO - gRPC endpoint had 'https://' prefix - stripped to: dev.app.langguard.ai
INFO - Added default gRPC/TLS port: dev.app.langguard.ai:443
INFO - Using gRPC OTLP exporter (insecure=False)
INFO - OTLP exporter initialized successfully
INFO - Exporting 1 spans via gRPC to dev.app.langguard.ai:443
INFO - gRPC export successful: 1 spans
```

### Final Checklist
- [ ] Endpoint auto-corrected from `https://host` to `host:443`
- [ ] Logs show auth header keys being passed
- [ ] gRPC errors show helpful diagnostic messages
- [ ] Default log level is INFO (not WARNING)
- [ ] Traces successfully reach LangGuard backend

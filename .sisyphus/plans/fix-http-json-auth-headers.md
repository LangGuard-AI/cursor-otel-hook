# Fix HTTP/JSON Auth Headers Not Being Sent

## TL;DR

> **Quick Summary**: HTTP/JSON exports may be failing due to missing `/v1/traces` endpoint path, silent batching behavior, and DEBUG-level logging hiding failures.
> 
> **Deliverables**: 
> - Auto-append `/v1/traces` to endpoint if missing
> - Add INFO-level logging for export attempts/results
> - Log auth header presence on startup
> - Ensure batching behavior is visible
> 
> **Estimated Effort**: Quick
> **Parallel Execution**: NO - sequential
> **Critical Path**: Logging → Endpoint fix → Test

---

## Context

### Original Request
User's OTEL traces aren't being sent. Updated config to use http/json:
```json
{
  "OTEL_EXPORTER_OTLP_ENDPOINT": "https://dev.app.langguard.ai",
  "OTEL_EXPORTER_OTLP_PROTOCOL": "http/json",
  "OTEL_EXPORTER_OTLP_INSECURE": "false",
  "OTEL_EXPORTER_OTLP_HEADERS": {
    "authorization": "Bearer lgr_hyJlhKTuohKNqL-..."
  }
}
```

### Root Causes Identified

**Issue 1: ENDPOINT MISSING `/v1/traces` PATH**

OTLP HTTP spec requires the traces endpoint path. The code comment even says:
> "endpoint: The OTLP endpoint URL (should include /v1/traces)"

- **Current**: `https://dev.app.langguard.ai` ❌
- **Should be**: `https://dev.app.langguard.ai/v1/traces` ✅

**Issue 2: BATCHING MODE SILENTLY HOLDS SPANS**

With `http/json` protocol, spans are NOT sent immediately. They're stored in temp files:
```
/tmp/cursor_otel_spans/{generation_id}.jsonl
```

Spans are only exported when a `stop` event is received! If your agent session doesn't end cleanly, spans accumulate but never send.

**Issue 3: LOGGING AT WRONG LEVEL**

- Default log level: `WARNING`
- Export success logged at: `DEBUG` (line 88)
- Export failure logged at: `ERROR` (line 91-92)

So you only see failures, never successes - and only if log level allows.

**Issue 4: NO HEADER CONFIRMATION LOGGING**

There's no log showing that auth headers were configured and will be sent.

---

## Work Objectives

### Core Objective
Ensure HTTP/JSON exports work correctly with auth headers and provide visibility into export status.

### Concrete Deliverables
- Auto-append `/v1/traces` to endpoint if missing
- INFO-level logging for all export attempts
- Log configured headers (keys only) on startup
- Log temp file location when batching

### Definition of Done
- [x] Traces successfully reach `dev.app.langguard.ai/v1/traces`
- [x] Logs show headers are configured
- [x] Logs show export attempts and results at INFO level
- [x] Logs show where spans are being stored (batching)

### Must Have
- Endpoint path auto-correction for http/json
- INFO-level export logging
- Header presence logging (keys only)

### Must NOT Have (Guardrails)
- Do NOT log auth header values
- Do NOT break other protocols (grpc, http/protobuf)
- Do NOT change batching behavior

---

## Verification Strategy

### Manual Verification

**Test with debug to see everything:**
```bash
echo '{"hook_event_name":"sessionStart","generation_id":"test-1"}' | python -m cursor_otel_hook --debug --config ~/.cursor/hooks/otel_config.json
echo '{"hook_event_name":"stop","generation_id":"test-1"}' | python -m cursor_otel_hook --debug --config ~/.cursor/hooks/otel_config.json
```

**Check logs:**
```bash
tail -50 ~/.cursor/hooks/cursor_otel_hook.log
```

**Check temp files (batching):**
```bash
ls -la /tmp/cursor_otel_spans/
```

---

## TODOs

- [x] 1. Change default log level from WARNING to INFO

  **What to do**:
  - In `hook_receiver.py` line 606, change:
  ```python
  # From:
  log_level = logging.DEBUG if args.debug else logging.WARNING
  # To:
  log_level = logging.DEBUG if args.debug else logging.INFO
  ```

  **Location**: `src/cursor_otel_hook/hook_receiver.py:606`

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Blocks**: All other tasks (need logging visible first)
  - **Blocked By**: None

  **References**:
  - `src/cursor_otel_hook/hook_receiver.py:604-606`

  **Acceptance Criteria**:
  ```bash
  echo '{"hook_event_name":"test"}' | python -m cursor_otel_hook
  grep "INFO" ~/.cursor/hooks/cursor_otel_hook.log | tail -3
  # Should show INFO entries without --debug flag
  ```

  **Commit**: YES
  - Message: `fix(logging): change default log level to INFO for visibility`
  - Files: `src/cursor_otel_hook/hook_receiver.py`

---

- [x] 2. Add endpoint path validation for http/json

  **What to do**:
  - In `hook_receiver.py`, in the `http/json` section (around line 148-161), add endpoint validation:
  
  ```python
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

      otlp_exporter = OTLPJSONSpanExporter(
          endpoint=endpoint,  # Use corrected endpoint
          headers=self.config.headers,
          timeout=self.config.timeout,
          service_name=self.config.service_name,
      )
  ```

  **Location**: `src/cursor_otel_hook/hook_receiver.py:148-161`

  **Must NOT do**:
  - Don't modify gRPC or http/protobuf paths
  - Don't auto-modify if endpoint already has a path

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Blocks**: Task 4
  - **Blocked By**: Task 1

  **References**:
  - `src/cursor_otel_hook/hook_receiver.py:148-161` - http/json setup
  - `src/cursor_otel_hook/json_exporter.py:37` - Comment says "should include /v1/traces"

  **Acceptance Criteria**:
  ```bash
  echo '{"hook_event_name":"test"}' | python -m cursor_otel_hook --debug
  grep "v1/traces" ~/.cursor/hooks/cursor_otel_hook.log
  # Should show endpoint with /v1/traces appended
  ```

  **Commit**: YES (group with task 1)
  - Message: `fix(http): auto-append /v1/traces to OTLP HTTP endpoint`
  - Files: `src/cursor_otel_hook/hook_receiver.py`

---

- [x] 3. Add auth header diagnostic logging

  **What to do**:
  - In `hook_receiver.py`, before creating the exporter, log headers info:
  
  ```python
  # Log auth headers (keys only, not values)
  if self.config.headers:
      header_keys = list(self.config.headers.keys())
      logger.info(f"Auth headers configured: {header_keys}")
  else:
      logger.warning("No auth headers configured - requests may be rejected")
  ```

  - In `json_exporter.py`, in `__init__`, log what's being added to session:
  
  ```python
  if headers:
      self.session.headers.update(headers)
      logger.info(f"Session headers updated with keys: {list(headers.keys())}")
  ```

  **Locations**: 
  - `src/cursor_otel_hook/hook_receiver.py:141-145`
  - `src/cursor_otel_hook/json_exporter.py:52-53`

  **Must NOT do**:
  - Do NOT log header values (contains Bearer token)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Blocks**: Task 4
  - **Blocked By**: Task 1

  **References**:
  - `src/cursor_otel_hook/hook_receiver.py:141-145`
  - `src/cursor_otel_hook/json_exporter.py:52-53`

  **Acceptance Criteria**:
  ```bash
  echo '{"hook_event_name":"test"}' | python -m cursor_otel_hook --debug
  grep -i "header" ~/.cursor/hooks/cursor_otel_hook.log
  # Should show: "Auth headers configured: ['authorization']"
  ```

  **Commit**: YES (group with tasks 1-2)
  - Message: `fix(logging): add auth header diagnostic logging`
  - Files: `src/cursor_otel_hook/hook_receiver.py`, `src/cursor_otel_hook/json_exporter.py`

---

- [x] 4. Upgrade export logging to INFO level

  **What to do**:
  - In `json_exporter.py`, change export logging from DEBUG to INFO:
  
  ```python
  def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
      # ... existing code ...
      
      logger.info(f"Sending {len(spans)} spans to {self.endpoint}")  # Changed from debug
      
      # ... make request ...
      
      if resp.ok:
          logger.info(f"Export successful: {len(spans)} spans (HTTP {resp.status_code})")  # Changed from debug
          return SpanExportResult.SUCCESS
      else:
          logger.error(f"Export failed: HTTP {resp.status_code} - {resp.text[:500]}")  # Truncate long responses
          return SpanExportResult.FAILURE
  ```

  - Same for `export_otlp_json` method (batched export)

  **Location**: `src/cursor_otel_hook/json_exporter.py:58-98` and `:253-305`

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Blocks**: None
  - **Blocked By**: Tasks 1-3

  **References**:
  - `src/cursor_otel_hook/json_exporter.py:68-94` - export() method
  - `src/cursor_otel_hook/json_exporter.py:269-301` - export_otlp_json() method

  **Acceptance Criteria**:
  ```bash
  # Trigger a flush (stop event)
  echo '{"hook_event_name":"sessionStart","generation_id":"test-x"}' | python -m cursor_otel_hook
  echo '{"hook_event_name":"stop","generation_id":"test-x"}' | python -m cursor_otel_hook
  grep -E "(Sending|Export)" ~/.cursor/hooks/cursor_otel_hook.log | tail -5
  # Should show "Sending X spans" and "Export successful/failed"
  ```

  **Commit**: YES (group with tasks 1-3)
  - Message: `fix(logging): upgrade export logging to INFO level`
  - Files: `src/cursor_otel_hook/json_exporter.py`

---

- [x] 5. Add batching visibility logging

  **What to do**:
  - In `batching_processor.py`, add INFO logging for span storage:
  
  ```python
  def on_end(self, span: ReadableSpan) -> None:
      # ... existing code ...
      
      # After storing span:
      logger.info(f"Span queued for batch: {span.name} (generation: {generation_id[:16]}...)")
  ```

  - In `flush_generation`, add timing and count:
  
  ```python
  def flush_generation(self, generation_id: str, service_name: str = "cursor-agent") -> bool:
      logger.info(f"Flushing batch for generation: {generation_id}")
      
      # ... existing code to read spans ...
      
      logger.info(f"Batch contains {len(spans_data)} spans from {span_file}")
      
      # ... export ...
      
      if result == SpanExportResult.SUCCESS:
          logger.info(f"Batch export successful: {len(spans_data)} spans")
      else:
          logger.error(f"Batch export FAILED for generation {generation_id}")
  ```

  **Location**: `src/cursor_otel_hook/batching_processor.py:106-131` and `:260-328`

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Blocks**: None
  - **Blocked By**: Tasks 1-4

  **References**:
  - `src/cursor_otel_hook/batching_processor.py:106-131` - on_end()
  - `src/cursor_otel_hook/batching_processor.py:260-328` - flush_generation()

  **Acceptance Criteria**:
  ```bash
  echo '{"hook_event_name":"preToolUse","generation_id":"batch-test","tool_name":"test"}' | python -m cursor_otel_hook
  grep "queued" ~/.cursor/hooks/cursor_otel_hook.log | tail -1
  # Should show: "Span queued for batch: cursor.preToolUse (generation: batch-test...)"
  ```

  **Commit**: YES (group with all tasks)
  - Message: `fix(logging): add batching visibility logging`
  - Files: `src/cursor_otel_hook/batching_processor.py`

---

## Commit Strategy

| After Tasks | Message | Files |
|-------------|---------|-------|
| 1-5 | `fix: improve HTTP/JSON auth and logging visibility` | hook_receiver.py, json_exporter.py, batching_processor.py |

---

## Immediate Workaround

**Update your config now to include the full endpoint path:**

```json
{
  "OTEL_EXPORTER_OTLP_ENDPOINT": "https://dev.app.langguard.ai/v1/traces",
  "OTEL_SERVICE_NAME": "cursor-agent",
  "OTEL_EXPORTER_OTLP_PROTOCOL": "http/json",
  "OTEL_EXPORTER_OTLP_INSECURE": "false",
  "OTEL_EXPORTER_OTLP_HEADERS": {
    "authorization": "Bearer lgr_hyJlhKTuohKNqL-s6OocUi3b25I6jGMVy6Ro0xOGHIk"
  }
}
```

**Key change**: Add `/v1/traces` to endpoint

**Test manually with debug:**
```bash
echo '{"hook_event_name":"sessionStart","generation_id":"manual-test"}' | python -m cursor_otel_hook --debug --config ~/.cursor/hooks/otel_config.json
echo '{"hook_event_name":"stop","generation_id":"manual-test"}' | python -m cursor_otel_hook --debug --config ~/.cursor/hooks/otel_config.json
tail -30 ~/.cursor/hooks/cursor_otel_hook.log
```

---

## Understanding Batching (Important!)

With `http/json` protocol, spans are **NOT sent immediately**. Here's what happens:

```
1. sessionStart event → Span created → Stored in /tmp/cursor_otel_spans/gen-123.jsonl
2. preToolUse event   → Span created → Appended to /tmp/cursor_otel_spans/gen-123.jsonl
3. postToolUse event  → Span created → Appended to /tmp/cursor_otel_spans/gen-123.jsonl
4. stop event         → Triggers FLUSH → All spans read from file → HTTP POST to endpoint → File deleted
```

**If you never see a `stop` event**, spans accumulate in temp files but never get sent!

Check for orphaned spans:
```bash
ls -la /tmp/cursor_otel_spans/
# If you see .jsonl files here, they haven't been flushed
```

---

## Success Criteria

### Verification Commands
```bash
# Full lifecycle test
echo '{"hook_event_name":"sessionStart","generation_id":"final-test"}' | python -m cursor_otel_hook --config ~/.cursor/hooks/otel_config.json
echo '{"hook_event_name":"stop","generation_id":"final-test"}' | python -m cursor_otel_hook --config ~/.cursor/hooks/otel_config.json

# Check logs
grep "final-test" ~/.cursor/hooks/cursor_otel_hook.log
```

### Expected Log Output After Fix
```
INFO - Auth headers configured: ['authorization']
INFO - Appended '/v1/traces' to endpoint: https://dev.app.langguard.ai/v1/traces
INFO - Using HTTP/JSON OTLP exporter with endpoint: https://dev.app.langguard.ai/v1/traces
INFO - Session headers updated with keys: ['authorization']
INFO - Processing hook event: sessionStart
INFO - Span queued for batch: cursor.sessionStart (generation: final-test...)
INFO - Processing hook event: stop
INFO - Flushing batch for generation: final-test
INFO - Batch contains 2 spans from /tmp/cursor_otel_spans/final-test.jsonl
INFO - Sending 2 spans to https://dev.app.langguard.ai/v1/traces
INFO - Export successful: 2 spans (HTTP 200)
INFO - Batch export successful: 2 spans
```

### Final Checklist
- [x] Default log level is INFO
- [x] Endpoint has `/v1/traces` appended automatically
- [x] Auth header keys logged on startup
- [x] Export attempts logged with endpoint URL
- [x] Export results logged with HTTP status
- [x] Batching operations visible in logs
- [x] Traces successfully reach LangGuard

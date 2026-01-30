# Add OTEL Debug Logging

## TL;DR

> **Quick Summary**: Add comprehensive logging to diagnose why OTEL traces aren't being sent. The current logging is too sparse and defaults to WARNING level, hiding critical operational info.
> 
> **Deliverables**: 
> - Enhanced logging at all critical points in the trace pipeline
> - Default log level changed from WARNING to INFO
> - Endpoint connectivity validation on startup
> - Export result tracking with timing
> 
> **Estimated Effort**: Quick
> **Parallel Execution**: NO - sequential changes to related files
> **Critical Path**: hook_receiver.py → json_exporter.py → batching_processor.py

---

## Context

### Original Request
User's OTEL logs are not being sent by the hook. Need to add additional logging to diagnose the issue.

### Analysis Findings

**Root Cause Candidates Identified:**

1. **Log Level Too Restrictive**: Default log level is `WARNING` (line 606 in hook_receiver.py), so INFO-level operational logs (initialization, export success) are never visible without `--debug` flag.

2. **Missing Critical Logging Points**:
   - No log when span is created/queued
   - No log confirming span was written to temp file (batching mode)
   - No log showing export HTTP response details
   - No config validation logging (is endpoint reachable?)
   - No log showing what protocol is actually being used

3. **Batching Mode Silent Failures**: In `http/json` mode, spans are stored to temp files and only exported on `stop` event. If `stop` never fires, spans accumulate silently.

4. **No Connectivity Check**: Endpoint is never validated on startup - failures only appear on first export attempt.

### Key Files
- `src/cursor_otel_hook/hook_receiver.py` - Main entry, logging setup, span creation
- `src/cursor_otel_hook/json_exporter.py` - HTTP export with response handling
- `src/cursor_otel_hook/batching_processor.py` - Temp file storage, batch flush
- `src/cursor_otel_hook/config.py` - Config loading and validation

---

## Work Objectives

### Core Objective
Add comprehensive logging to trace the complete lifecycle of spans from creation to export, making it easy to diagnose where traces are getting lost.

### Concrete Deliverables
- Modified `hook_receiver.py` with enhanced logging
- Modified `json_exporter.py` with HTTP request/response logging
- Modified `batching_processor.py` with file operation logging
- Modified `config.py` with validation logging

### Definition of Done
- [x] Running `echo '{"hook_event_name":"test"}' | python -m cursor_otel_hook` shows INFO-level logs
- [x] Logs clearly show: config loaded → exporter initialized → span created → span queued → export attempted → export result
- [x] Failed exports show HTTP status code and response body
- [x] Temp file operations are logged (write/read/delete)

### Must Have
- Default log level changed to INFO (not WARNING)
- Log entry when span is created with span name and generation_id
- Log entry when span is written to temp file (batching mode)
- Log entry showing HTTP request URL and response status
- Log entry on export success/failure with span count

### Must NOT Have (Guardrails)
- Do NOT log sensitive data (prompts, tool outputs) at INFO level
- Do NOT log full OTLP payload at INFO level (too verbose) - keep at DEBUG
- Do NOT add logging that significantly impacts performance
- Do NOT change the functional behavior - only add observability

---

## Verification Strategy

### Test Decision
- **Infrastructure exists**: NO (tests/ directory is empty)
- **User wants tests**: Manual verification
- **QA approach**: Manual verification with test commands

### Manual Verification Procedures

**For each change, run:**
```bash
# Test with a simple hook event
echo '{"hook_event_name":"test","generation_id":"test-123"}' | python -m cursor_otel_hook --config ~/.cursor/hooks/otel_config.json

# Check the log file
tail -50 ~/.cursor/hooks/cursor_otel_hook.log
```

**Expected log output should show:**
```
INFO - Cursor OTEL Hook starting
INFO - Loading configuration from: ...
INFO - Configuration loaded: endpoint=http://..., protocol=...
INFO - Initializing CursorHookProcessor...
INFO - Using [protocol] OTLP exporter
INFO - Processing hook event: test
INFO - Created span: cursor.test (generation: test-123)
INFO - Span queued for export (or) Span written to temp file: ...
INFO - Hook processed successfully
```

---

## TODOs

- [x] 1. Change default log level from WARNING to INFO

  **What to do**:
  - In `hook_receiver.py` line 606, change `logging.WARNING` to `logging.INFO`
  - This ensures operational logs are always visible without `--debug`

  **Must NOT do**:
  - Do not change DEBUG level behavior
  - Do not add stderr output without --debug flag

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`
    - Simple one-line change

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Blocks**: Tasks 2-5 (they depend on logging being visible)
  - **Blocked By**: None

  **References**:
  - `src/cursor_otel_hook/hook_receiver.py:604-606` - Current logging setup

  **Acceptance Criteria**:
  ```bash
  # After change, this should show INFO logs (not just errors)
  echo '{"hook_event_name":"test"}' | python -m cursor_otel_hook 2>/dev/null
  grep "INFO" ~/.cursor/hooks/cursor_otel_hook.log | tail -5
  # Should see recent INFO entries
  ```

  **Commit**: YES
  - Message: `fix(logging): change default log level from WARNING to INFO`
  - Files: `src/cursor_otel_hook/hook_receiver.py`

---

- [x] 2. Add config validation logging

  **What to do**:
  - In `config.py`, after loading config, log a summary at INFO level:
    ```python
    logger.info(f"Configuration loaded: endpoint={self.endpoint}, protocol={self.protocol}, service={self.service_name}")
    ```
  - Add validation: check if endpoint URL is well-formed
  - Log headers presence (not values): `logger.info(f"Auth headers configured: {bool(self.headers)}")`

  **Must NOT do**:
  - Do NOT log header values (may contain secrets)
  - Do NOT log full config object with sensitive fields

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES (with tasks 3, 4, 5)
  - **Blocks**: None
  - **Blocked By**: Task 1

  **References**:
  - `src/cursor_otel_hook/config.py:94-114` - `OTELConfig.load()` method
  - `src/cursor_otel_hook/config.py:22-41` - `from_env()` method
  - `src/cursor_otel_hook/config.py:43-91` - `from_file()` method

  **Acceptance Criteria**:
  ```bash
  echo '{"hook_event_name":"test"}' | python -m cursor_otel_hook --config ~/.cursor/hooks/otel_config.json
  grep "Configuration loaded" ~/.cursor/hooks/cursor_otel_hook.log | tail -1
  # Should show: Configuration loaded: endpoint=..., protocol=..., service=...
  ```

  **Commit**: YES (group with task 1)
  - Message: `fix(logging): add config validation and summary logging`
  - Files: `src/cursor_otel_hook/config.py`

---

- [x] 3. Add span lifecycle logging in hook_receiver.py

  **What to do**:
  - After creating span (line ~249), add:
    ```python
    logger.info(f"Created span: {span_name} (generation: {generation_id}, trace: {format(span.get_span_context().trace_id, '032x')[:16]}...)")
    ```
  - After span ends (in finally block, after line ~292), add:
    ```python
    logger.info(f"Span completed: {span_name} (duration: {duration*1000:.1f}ms)")
    ```
  - In `process_hook`, log the generation_id and conversation_id at start:
    ```python
    logger.info(f"Processing: event={hook_event}, generation={generation_id[:16] if generation_id != 'unknown' else 'unknown'}...")
    ```

  **Must NOT do**:
  - Do NOT log full hook_data at INFO level
  - Do NOT log span attributes (may contain sensitive data)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES (with tasks 2, 4, 5)
  - **Blocks**: None
  - **Blocked By**: Task 1

  **References**:
  - `src/cursor_otel_hook/hook_receiver.py:217-292` - `process_hook()` method
  - `src/cursor_otel_hook/hook_receiver.py:249` - Span creation
  - `src/cursor_otel_hook/hook_receiver.py:279-292` - Finally block

  **Acceptance Criteria**:
  ```bash
  echo '{"hook_event_name":"sessionStart","generation_id":"abc123"}' | python -m cursor_otel_hook
  grep -E "(Created span|Span completed)" ~/.cursor/hooks/cursor_otel_hook.log | tail -2
  # Should show both "Created span" and "Span completed" entries
  ```

  **Commit**: YES (group with tasks 1-2)
  - Message: `fix(logging): add span lifecycle logging`
  - Files: `src/cursor_otel_hook/hook_receiver.py`

---

- [x] 4. Add HTTP export logging in json_exporter.py

  **What to do**:
  - Before HTTP request (line ~73), add:
    ```python
    logger.info(f"Exporting {len(spans)} spans to {self.endpoint}")
    ```
  - After successful response, add:
    ```python
    logger.info(f"Export successful: {len(spans)} spans, HTTP {resp.status_code}, {resp.elapsed.total_seconds()*1000:.0f}ms")
    ```
  - On failure, enhance error logging:
    ```python
    logger.error(f"Export failed: HTTP {resp.status_code}, response: {resp.text[:500]}")
    ```
  - Same for `export_otlp_json` method (batched export)

  **Must NOT do**:
  - Do NOT log request body at INFO level
  - Do NOT log auth headers

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES (with tasks 2, 3, 5)
  - **Blocks**: None
  - **Blocked By**: Task 1

  **References**:
  - `src/cursor_otel_hook/json_exporter.py:58-98` - `export()` method
  - `src/cursor_otel_hook/json_exporter.py:253-305` - `export_otlp_json()` method

  **Acceptance Criteria**:
  ```bash
  # With a valid endpoint configured
  echo '{"hook_event_name":"stop","generation_id":"test123"}' | python -m cursor_otel_hook
  grep -E "(Exporting|Export successful|Export failed)" ~/.cursor/hooks/cursor_otel_hook.log | tail -3
  # Should show export attempt and result
  ```

  **Commit**: YES (group with tasks 1-3)
  - Message: `fix(logging): add HTTP export request/response logging`
  - Files: `src/cursor_otel_hook/json_exporter.py`

---

- [x] 5. Add batching processor logging

  **What to do**:
  - In `on_end` (line ~106), after storing span:
    ```python
    logger.info(f"Span queued: {span.name} -> {span_file} (generation: {generation_id[:16]}...)")
    ```
  - In `flush_generation` (line ~260), add timing:
    ```python
    flush_start = time.time()
    # ... existing code ...
    logger.info(f"Flush complete: {len(spans_data)} spans exported in {(time.time()-flush_start)*1000:.0f}ms")
    ```
  - Log temp file stats:
    ```python
    logger.info(f"Temp storage: {span_file} ({span_file.stat().st_size} bytes, {line_count} spans)")
    ```

  **Must NOT do**:
  - Do NOT log span content
  - Do NOT change file cleanup behavior

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: YES (with tasks 2, 3, 4)
  - **Blocks**: None
  - **Blocked By**: Task 1

  **References**:
  - `src/cursor_otel_hook/batching_processor.py:106-131` - `on_end()` method
  - `src/cursor_otel_hook/batching_processor.py:260-328` - `flush_generation()` method
  - `src/cursor_otel_hook/batching_processor.py:133-153` - `_store_span()` method

  **Acceptance Criteria**:
  ```bash
  # Create a span, then flush it
  echo '{"hook_event_name":"sessionStart","generation_id":"test456"}' | python -m cursor_otel_hook
  echo '{"hook_event_name":"stop","generation_id":"test456"}' | python -m cursor_otel_hook
  grep -E "(Span queued|Flush complete)" ~/.cursor/hooks/cursor_otel_hook.log | tail -2
  # Should show queuing and flush
  ```

  **Commit**: YES (group with tasks 1-4)
  - Message: `fix(logging): add batching processor operation logging`
  - Files: `src/cursor_otel_hook/batching_processor.py`

---

- [x] 6. Add startup connectivity check (optional enhancement)

  **What to do**:
  - In `CursorHookProcessor.__init__` or `_setup_tracer`, add optional connectivity check:
    ```python
    def _check_endpoint_connectivity(self) -> bool:
        """Quick connectivity check to endpoint (non-blocking warning only)."""
        try:
            import urllib.request
            req = urllib.request.Request(self.config.endpoint, method='HEAD')
            urllib.request.urlopen(req, timeout=2)
            logger.info(f"Endpoint reachable: {self.config.endpoint}")
            return True
        except Exception as e:
            logger.warning(f"Endpoint may be unreachable: {self.config.endpoint} ({e})")
            return False
    ```
  - Call this after exporter initialization
  - This is non-blocking - just a warning if unreachable

  **Must NOT do**:
  - Do NOT make this block startup
  - Do NOT fail if endpoint is unreachable (it might come up later)

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: `[]`

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Blocks**: None
  - **Blocked By**: Tasks 1-5

  **References**:
  - `src/cursor_otel_hook/hook_receiver.py:118-126` - `CursorHookProcessor.__init__`
  - `src/cursor_otel_hook/hook_receiver.py:128-215` - `_setup_tracer()`

  **Acceptance Criteria**:
  ```bash
  # With unreachable endpoint
  echo '{"hook_event_name":"test"}' | OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:9999" python -m cursor_otel_hook
  grep "Endpoint" ~/.cursor/hooks/cursor_otel_hook.log | tail -1
  # Should show warning about unreachable endpoint
  ```

  **Commit**: YES
  - Message: `feat(logging): add optional endpoint connectivity check on startup`
  - Files: `src/cursor_otel_hook/hook_receiver.py`

---

## Commit Strategy

| After Task | Message | Files |
|------------|---------|-------|
| 1-5 (grouped) | `fix(logging): add comprehensive OTEL debug logging` | hook_receiver.py, config.py, json_exporter.py, batching_processor.py |
| 6 | `feat(logging): add endpoint connectivity check` | hook_receiver.py |

---

## Success Criteria

### Verification Commands
```bash
# Full test: should see complete lifecycle
echo '{"hook_event_name":"sessionStart","generation_id":"test-gen-1"}' | python -m cursor_otel_hook
echo '{"hook_event_name":"preToolUse","generation_id":"test-gen-1","tool_name":"bash"}' | python -m cursor_otel_hook  
echo '{"hook_event_name":"stop","generation_id":"test-gen-1"}' | python -m cursor_otel_hook

# Check logs show complete flow
grep "test-gen-1" ~/.cursor/hooks/cursor_otel_hook.log
```

### Expected Log Flow
```
INFO - Configuration loaded: endpoint=http://..., protocol=http/json, service=cursor-agent
INFO - Endpoint reachable: http://...
INFO - Using custom HTTP OTLP exporter (JSON format) with generation batching
INFO - Processing: event=sessionStart, generation=test-gen-1...
INFO - Created span: cursor.sessionStart (generation: test-gen-1, trace: abc123...)
INFO - Span queued: cursor.sessionStart -> /tmp/cursor_otel_spans/test-gen-1.jsonl
INFO - Span completed: cursor.sessionStart (duration: 5.2ms)
...
INFO - Processing: event=stop, generation=test-gen-1...
INFO - Flushing spans for generation test-gen-1
INFO - Exporting 3 spans to http://...
INFO - Export successful: 3 spans, HTTP 200, 45ms
INFO - Flush complete: 3 spans exported in 52ms
```

### Final Checklist
- [x] Default log level is INFO (not WARNING)
- [x] Config summary logged on startup
- [x] Each span creation/completion logged
- [x] Export attempts logged with URL
- [x] Export results logged with status code and timing
- [x] Temp file operations logged (batching mode)
- [x] No sensitive data in INFO logs

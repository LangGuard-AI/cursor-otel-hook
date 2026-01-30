# Known Issues & Gotchas

## [2026-01-30] HTTP/JSON Export Visibility

### Issue: Export Success/Failure Hidden at DEBUG Level
- **Problem**: json_exporter.py logs export results at DEBUG level (lines 68-94, 269-301)
- **Impact**: Users can't see if traces are being sent successfully
- **Solution**: Upgrade to INFO level in Task 4

### Issue: Batching Behavior Silent
- **Problem**: batching_processor.py doesn't log span queuing or batch flushing
- **Impact**: Users don't know spans are being stored vs sent immediately
- **Solution**: Add INFO logging in Task 5

### Gotcha: Batching Only on 'stop' Event
- **Important**: With http/json protocol, spans accumulate in temp files
- **Location**: /tmp/cursor_otel_spans/{generation_id}.jsonl
- **Trigger**: Only flushed when 'stop' event received
- **Risk**: If session doesn't end cleanly, spans never send

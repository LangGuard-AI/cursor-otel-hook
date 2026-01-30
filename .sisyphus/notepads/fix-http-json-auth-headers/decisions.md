# Architectural Decisions

## [2026-01-30] Logging Strategy

### Decision: Change Default Log Level to INFO
- **Rationale**: Users need to see export success/failure without --debug flag
- **Impact**: More verbose logs by default, but essential for troubleshooting
- **Location**: hook_receiver.py line 680

### Decision: Auto-append /v1/traces to Endpoint
- **Rationale**: OTLP HTTP spec requires this path, common user mistake
- **Impact**: Automatic correction with warning log
- **Location**: hook_receiver.py lines 162-171

### Decision: Log Header Keys Only
- **Rationale**: Security - never expose Bearer tokens in logs
- **Impact**: Users can verify headers are configured without exposing secrets
- **Locations**: hook_receiver.py lines 167-171, json_exporter.py line 56

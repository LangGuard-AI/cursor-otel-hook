#!/bin/bash
# Per-user setup script for Cursor OTEL Hook
# Runs as the logged-in user via LaunchAgent at login
# Also called by postinstall for immediate setup

INSTALL_DIR="/Library/Application Support/CursorOtelHook"
USER_CURSOR_DIR="$HOME/.cursor"
USER_HOOKS_DIR="$USER_CURSOR_DIR/hooks"
LOG_FILE="/tmp/cursor-otel-hook-setup-$USER.log"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
    echo "$1"
}

log "Starting Cursor OTEL Hook user setup for: $USER"

# Check if system installation exists
if [ ! -d "$INSTALL_DIR" ]; then
    log "ERROR: System installation not found at $INSTALL_DIR"
    exit 1
fi

# Create user directories
if [ ! -d "$USER_HOOKS_DIR" ]; then
    mkdir -p "$USER_HOOKS_DIR"
    log "Created hooks directory: $USER_HOOKS_DIR"
fi

# Copy executable if newer or missing
HOOK_EXECUTABLE="$USER_HOOKS_DIR/cursor-otel-hook"
SOURCE_EXECUTABLE="$INSTALL_DIR/cursor-otel-hook"

if [ ! -f "$HOOK_EXECUTABLE" ] || [ "$SOURCE_EXECUTABLE" -nt "$HOOK_EXECUTABLE" ]; then
    cp "$SOURCE_EXECUTABLE" "$HOOK_EXECUTABLE"
    chmod 755 "$HOOK_EXECUTABLE"
    log "Installed executable to: $HOOK_EXECUTABLE"
else
    log "Executable is up to date"
fi

# Copy configuration if newer or missing
CONFIG_FILE="$USER_HOOKS_DIR/otel_config.json"
SOURCE_CONFIG="$INSTALL_DIR/otel_config.json"

if [ -f "$SOURCE_CONFIG" ]; then
    if [ ! -f "$CONFIG_FILE" ] || [ "$SOURCE_CONFIG" -nt "$CONFIG_FILE" ]; then
        cp "$SOURCE_CONFIG" "$CONFIG_FILE"
        chmod 644 "$CONFIG_FILE"
        log "Installed configuration to: $CONFIG_FILE"
    else
        log "Configuration is up to date"
    fi
else
    log "WARNING: No system configuration found, user will need to configure manually"
fi

# Create or merge hooks.json
HOOKS_JSON="$USER_CURSOR_DIR/hooks.json"
HOOKS_TEMPLATE="$INSTALL_DIR/hooks.template.json"
HOOK_COMMAND="$HOOK_EXECUTABLE --config $CONFIG_FILE"
HOOK_TIMEOUT="5"
HOOK_EVENTS="sessionStart sessionEnd postToolUse afterShellExecution afterMCPExecution beforeReadFile afterFileEdit beforeSubmitPrompt subagentStart subagentStop stop"

if [ -f "$HOOKS_JSON" ]; then
    # Merge otel hooks into existing hooks.json
    log "hooks.json already exists at $HOOKS_JSON - merging otel hooks"
    if command -v python3 &> /dev/null; then
        if python3 - "$HOOKS_JSON" "$HOOK_COMMAND" $HOOK_EVENTS << 'PYEOF'
import json, sys

hooks_file = sys.argv[1]
hook_command = sys.argv[2]
events = sys.argv[3:]

with open(hooks_file, 'r') as f:
    data = json.load(f)

data.setdefault('version', 1)
data.setdefault('hooks', {})

changed = False
for event in events:
    entry = {'command': hook_command, 'timeout': 5}
    if event not in data['hooks']:
        data['hooks'][event] = [entry]
        changed = True
    else:
        cmds = [h.get('command', '') for h in data['hooks'][event]]
        if hook_command not in cmds:
            data['hooks'][event].append(entry)
            changed = True

if changed:
    with open(hooks_file, 'w') as f:
        json.dump(data, f, indent=2)
        f.write('\n')
PYEOF
        then
            log "Merged otel hooks into $HOOKS_JSON"
        else
            log "WARNING: Failed to merge hooks.json - manual merge may be needed"
        fi
    else
        log "WARNING: python3 not found, cannot auto-merge hooks.json"
        log "Manual merge may be needed to add otel hook entries"
    fi
elif [ -f "$HOOKS_TEMPLATE" ]; then
    # Create hooks.json from template
    HOOKS_CONTENT=$(cat "$HOOKS_TEMPLATE")
    HOOKS_CONTENT=$(echo "$HOOKS_CONTENT" | sed "s|{{HOOK_COMMAND}}|$HOOK_COMMAND|g")
    HOOKS_CONTENT=$(echo "$HOOKS_CONTENT" | sed "s|{{HOOK_TIMEOUT}}|$HOOK_TIMEOUT|g")

    echo "$HOOKS_CONTENT" > "$HOOKS_JSON"
    chmod 644 "$HOOKS_JSON"
    log "Created hooks.json at: $HOOKS_JSON"
else
    log "ERROR: hooks.template.json not found"
fi

log "User setup complete"
log "Restart Cursor IDE for changes to take effect"
exit 0

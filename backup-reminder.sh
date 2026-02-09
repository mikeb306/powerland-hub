#!/bin/bash
# backup-reminder.sh — Check if Hub localStorage backup is stale (>48 hours)
# If stale, sends a Telegram alert via Magic/OpenClaw

BACKUP_FILE="$HOME/.openclaw/workspace/data/hub-localStorage-backup.json"
MAX_AGE_HOURS=48

if [ ! -f "$BACKUP_FILE" ]; then
    # No backup exists at all
    bash "$HOME/.openclaw/workspace/tools/hub-note.sh" \
        "Hub localStorage has NEVER been backed up. Open the Hub in a browser to create a backup." \
        "" "flag"
    exit 0
fi

# Get file age in hours
FILE_AGE_SEC=$(( $(date +%s) - $(stat -f %m "$BACKUP_FILE") ))
FILE_AGE_HOURS=$(( FILE_AGE_SEC / 3600 ))

if [ "$FILE_AGE_HOURS" -ge "$MAX_AGE_HOURS" ]; then
    LAST_DATE=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M" "$BACKUP_FILE")
    bash "$HOME/.openclaw/workspace/tools/hub-note.sh" \
        "Hub localStorage backup is stale (last: $LAST_DATE, ${FILE_AGE_HOURS}h ago). Open the Hub to trigger a fresh backup." \
        "" "flag"
fi

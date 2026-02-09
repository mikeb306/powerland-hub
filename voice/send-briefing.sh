#!/bin/bash
# send-briefing.sh — Generate morning pipeline briefing and send via Telegram
# Runs daily on weekdays at 7:00 AM CST via LaunchAgent

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG="$SCRIPT_DIR/voice-config.json"
LOG="/tmp/powerland-briefing.log"

echo "$(date): Starting morning briefing..." >> "$LOG"

# Skip weekends
DOW=$(date +%u)
if [ "$DOW" -gt 5 ]; then
    echo "$(date): Weekend — skipping." >> "$LOG"
    exit 0
fi

# Read Telegram config
BOT_TOKEN=$(python3 -c "import json; print(json.load(open('$CONFIG'))['TELEGRAM_BOT_TOKEN'])")
CHAT_ID=$(python3 -c "import json; print(json.load(open('$CONFIG'))['TELEGRAM_CHAT_ID'])")

if [ "$BOT_TOKEN" = "YOUR_TELEGRAM_BOT_TOKEN_HERE" ] || [ "$CHAT_ID" = "YOUR_TELEGRAM_CHAT_ID_HERE" ]; then
    echo "$(date): ERROR — Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in voice-config.json" >> "$LOG"
    exit 1
fi

# Generate the briefing (text + MP3)
BRIEFING_TEXT=$(python3 "$SCRIPT_DIR/morning-briefing.py" 2>>"$LOG")
TODAY=$(date +%Y-%m-%d)
MP3_PATH="$SCRIPT_DIR/briefings/briefing-$TODAY.mp3"

if [ ! -f "$MP3_PATH" ]; then
    echo "$(date): ERROR — MP3 not generated at $MP3_PATH" >> "$LOG"
    exit 1
fi

# Extract just the script text (between the === lines)
SCRIPT_TEXT=$(echo "$BRIEFING_TEXT" | sed -n '/^MORNING BRIEFING SCRIPT$/,/^===/{/^===/d;/^MORNING BRIEFING SCRIPT$/d;p;}')

# Send audio to Telegram
echo "$(date): Sending audio to Telegram..." >> "$LOG"
AUDIO_RESP=$(curl -s -X POST \
    "https://api.telegram.org/bot${BOT_TOKEN}/sendAudio" \
    -F "chat_id=${CHAT_ID}" \
    -F "audio=@${MP3_PATH}" \
    -F "title=Pipeline Briefing ${TODAY}" \
    -F "performer=SK Command Center")

AUDIO_OK=$(echo "$AUDIO_RESP" | python3 -c "import json,sys; print(json.load(sys.stdin).get('ok', False))" 2>/dev/null || echo "False")

if [ "$AUDIO_OK" = "True" ]; then
    echo "$(date): Audio sent successfully." >> "$LOG"
else
    echo "$(date): WARNING — Audio send failed: $AUDIO_RESP" >> "$LOG"
fi

# Send text summary as follow-up message
echo "$(date): Sending text summary..." >> "$LOG"
curl -s -X POST \
    "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
    -d "chat_id=${CHAT_ID}" \
    -d "parse_mode=Markdown" \
    --data-urlencode "text=*Pipeline Briefing — ${TODAY}*

${SCRIPT_TEXT}" >> "$LOG" 2>&1

echo "" >> "$LOG"
echo "$(date): Briefing complete." >> "$LOG"

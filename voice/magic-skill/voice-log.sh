#!/bin/bash
# voice-log.sh — Parse voice transcription into structured CRM activity log
# Usage: voice-log.sh "<transcription text>"
#
# Examples:
#   voice-log.sh "Had a call with Jane Smith at Gov of SK about the M365 migration"
#   voice-log.sh "Met with the team at SaskTel to demo managed print"
#   voice-log.sh "Emailed Mark at Cameco about the print fleet renewal quote"

TEXT="${1:?Usage: voice-log.sh \"<transcription text>\"}"

python3 /Users/mikesmac/clawd/powerland-hub/voice/voice-to-crm.py --text "$TEXT"

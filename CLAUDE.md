# Powerland Hub

Single-file CRM application for Xerox IT Solutions pipeline management.

## Architecture
- **`index.html`** (~5400 lines) — entire app in one HTML file (HTML + CSS + JS)
- No build step, no framework — vanilla JS with localStorage persistence
- External lib: SortableJS for Kanban drag-and-drop

## Conventions
- **JS validation before commits**: `node -e "new Function(allJs)"` — extract all JS, parse it
- **localStorage key prefix**: `xits_acct_` for all account/deal data
- **No secrets in git** — `voice-config.json` is gitignored (contains API keys)

## Voice System (`voice/`)
- Scripts import from `eleven_tts.py` for ElevenLabs TTS
- Config: `voice/voice-config.json` (API keys, Telegram tokens — gitignored)
- Voice: Lily — Velvety Actress (`pFZP5JQG7iQjIQuC4Bku`)
- Automation: morning briefing, deal alerts, weekly wrap (via LaunchAgents)

## Features Implemented
- Kanban board with drag-and-drop stage transitions
- MEDDPICC scoring with gate enforcement on stage moves
- FAB (Floating Action Button) for quick activity logging
- KPI cards, health scoring, deal aging alerts
- Multi-contact management, competitive intel, whitespace heatmap
- Territory map, account tiering, win/loss analytics
- Mobile responsive, offline sync, data import/export

## Git
- Remote: `https://github.com/mikeb306/powerland-hub.git` (branch: main)

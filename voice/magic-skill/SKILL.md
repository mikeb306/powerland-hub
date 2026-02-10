---
name: voice-log
description: Parse voice messages and natural language transcriptions into structured CRM activity logs. Fuzzy-matches account names, detects activity type, extracts contact names, and posts to the Powerland Hub.
triggers:
  - voice log
  - log a call
  - log a meeting
  - log an email
  - log activity
  - had a call
  - met with
  - spoke with
  - talked to
  - emailed
  - just called
  - voice message
  - voice note
---

# Voice-to-CRM Activity Logger

## What This Does
Parses natural language messages (voice transcriptions or typed activity logs) into structured CRM activity entries. Automatically detects the activity type, fuzzy-matches the account name against known Saskatchewan accounts, extracts contact names, and posts the structured log to the Powerland Hub via cal-proxy.

## Tool
`bash /Users/mikesmac/.openclaw/workspace/tools/voice-log.sh "<transcription text>"`

## When to Use
Use this skill when Mike:
1. Sends a voice message describing a sales activity (call, meeting, email, note)
2. Types something like "log a call with Jane at SaskTel about the print proposal"
3. Says "had a meeting with..." or "just called..." or "emailed..." or "spoke with..."
4. Sends any message that sounds like an activity log for a specific account

## How It Works
1. **Activity Type Detection** — Infers call, email, meeting, or note from keywords
2. **Account Matching** — Fuzzy-matches against all known Powerland Hub accounts (supports abbreviations like "SGI", partial names like "Cameco", and full names)
3. **Contact Extraction** — Finds "FirstName LastName" patterns after prepositions
4. **Posts to Hub** — Sends structured JSON to cal-proxy `/notes` endpoint with `[VOICE LOG]` prefix

## Examples

**Voice message:** "Had a call with Jane Smith at Government of Saskatchewan about the M365 migration timeline, they're moving forward with the proposal next month"
```bash
voice-log.sh "Had a call with Jane Smith at Government of Saskatchewan about the M365 migration timeline, they're moving forward with the proposal next month"
```
→ Logged call with Jane Smith at Government of Saskatchewan

**Quick typed log:** "Met with the team at SaskTel to demo managed print"
```bash
voice-log.sh "Met with the team at SaskTel to demo managed print"
```
→ Logged meeting at SaskTel

**Email follow-up:** "Emailed Mark at Cameco about the print fleet renewal quote"
```bash
voice-log.sh "Emailed Mark at Cameco about the print fleet renewal quote"
```
→ Logged email at Cameco Corporation

## When Account Can't Be Matched
If the tool cannot match an account name, it will output an error message. In this case:
1. Tell Mike the account could not be matched
2. Ask Mike to clarify the account name
3. Re-run the tool with the corrected transcription, or use `hub-note.sh` directly with the correct account name

## Rules
- Always run the voice-log tool first — don't try to manually parse the message
- Always confirm to Mike what was logged: activity type, contact (if found), account, and summary
- If the tool output says "Could not match an account", ask Mike to clarify
- Don't modify the transcription before passing it to the tool — pass it verbatim
- This tool handles the cal-proxy posting; do NOT also post via hub-note.sh (that would duplicate the entry)

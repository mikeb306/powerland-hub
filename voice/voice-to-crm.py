#!/usr/bin/env python3
"""Voice-to-CRM — parse natural language transcriptions into structured activity logs."""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from difflib import get_close_matches

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CAL_PROXY = "http://127.0.0.1:18790"


# --- Activity type detection ---

ACTIVITY_PATTERNS = {
    "call": [
        r"\bcall(?:ed|ing)?\b", r"\bphon(?:e|ed|ing)\b", r"\brang\b",
        r"\bspoke (?:to|with)\b", r"\btalked (?:to|with)\b", r"\bdialed\b",
        r"\blog a call\b", r"\bcold call\b", r"\bphone call\b",
    ],
    "email": [
        r"\bemail(?:ed|ing)?\b", r"\be-?mail\b", r"\bsent (?:a |an )?(?:email|message|note)\b",
        r"\binbox\b", r"\bwrote to\b", r"\bfollowed up via email\b",
    ],
    "meeting": [
        r"\bm(?:et|eeting)\b", r"\bsat down with\b", r"\bvisit(?:ed|ing)?\b",
        r"\bsite visit\b", r"\bdemo(?:nstrat(?:ed|ion))?\b", r"\bpresent(?:ed|ation)\b",
        r"\blunch(?:ed)?\b", r"\bcoffee with\b", r"\bteams call\b", r"\bzoom\b",
        r"\bwebex\b", r"\bin-person\b", r"\bface to face\b",
    ],
    "note": [
        r"\bnote\b", r"\bupdate\b", r"\bfyi\b", r"\bheads up\b",
        r"\bjust (?:a )?(?:quick )?note\b", r"\breminder\b",
    ],
}


def detect_activity_type(text):
    text_lower = text.lower()
    scores = {t: 0 for t in ACTIVITY_PATTERNS}
    for activity_type, patterns in ACTIVITY_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                scores[activity_type] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "note"


# --- Contact name extraction ---

CONTACT_PREFIXES = [
    r"(?:with|to|from|and|met|called|emailed|spoke to|talked to|talked with|spoke with)\s+",
]
NAME_PATTERN = r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})"


def extract_contact_name(text, account_name=""):
    # Remove account name from text to avoid false matches
    cleaned = text
    if account_name:
        cleaned = cleaned.replace(account_name, "")

    # Try "with/to/from FirstName LastName" patterns
    for prefix in CONTACT_PREFIXES:
        match = re.search(prefix + NAME_PATTERN, cleaned)
        if match:
            name = match.group(1).strip()
            # Filter out common false positives
            skip_words = {
                "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                "Saturday", "Sunday", "January", "February", "March",
                "April", "May", "June", "July", "August", "September",
                "October", "November", "December", "Today", "Tomorrow",
                "The", "This", "That", "They", "Their", "About",
                "Called", "Emailed", "Meeting", "Note", "Update",
            }
            words = name.split()
            if words[0] not in skip_words and len(words) >= 2:
                return name

    return ""


# --- Account name matching ---

def fetch_known_accounts():
    """Fetch known account names from cal-proxy pipeline, backup, and fallback list."""
    accounts = {}  # lowercase key -> proper-cased name

    # From pipeline (highest quality names)
    try:
        r = requests.get(f"{CAL_PROXY}/pipeline", timeout=5)
        data = r.json()
        for deal in data.get("deals", []):
            if deal.get("account"):
                accounts[deal["account"].lower()] = deal["account"]
    except Exception:
        pass

    # From backup (all account keys — lower quality, don't overwrite pipeline names)
    try:
        r = requests.get(f"{CAL_PROXY}/backup", timeout=5)
        data = r.json()
        for key in data.get("keys", {}):
            if key.startswith("xits_acct_"):
                name = key.replace("xits_acct_", "").replace("_", " ").strip()
                if name.lower() not in accounts:
                    accounts[name.lower()] = name
    except Exception:
        pass

    # Hardcoded major accounts as fallback — these have proper casing, always override backup
    fallback = [
        "Government of Saskatchewan", "Nutrien Ltd", "SaskTel",
        "Federated Co-operatives", "SGI Canada", "The Mosaic Company",
        "SIGA", "Brandt Group", "SaskEnergy", "Cameco Corporation",
        "Conexus Credit Union", "Affinity Credit Union", "Viterra",
        "Saskatchewan WCB", "City of Saskatoon", "City of Regina",
        "Saskatchewan Health Authority", "eHealth Saskatchewan",
        "SaskPower", "Bunge Canada", "K+S Potash Canada",
        "Regina General Hospital", "St Paul's Hospital",
        "Saskatchewan Gaming Corporation", "Farm Credit Canada",
        "Vecima Networks", "Bourgault Industries", "CGI",
        "Prince Albert Grand Council", "Potash Corp of SK",
        "GSCS", "SLGA", "Pharma Choice Canada",
        "Maple Leaf Consumer Foods", "Trans Gas Ltd",
        "Sun Country Regional Health", "Five Hills Health Region",
        "Kelsey Trail Health Region", "Ranch Ehrlo Society",
        "Northern Lights Casino", "Gold Eagle Casino",
        "Painted Hand Casino", "Canadian Pacific Railway",
    ]
    for name in fallback:
        accounts[name.lower()] = name  # Fallback has proper casing, always wins

    return list(accounts.values())


def build_match_candidates(accounts):
    """Build a mapping of normalized names and abbreviations to original names."""
    candidates = {}
    for name in accounts:
        # Full name
        candidates[name.lower()] = name
        # Without parenthetical
        base = re.sub(r"\s*\([^)]*\)\s*", " ", name).strip()
        if base.lower() != name.lower():
            candidates[base.lower()] = name
        # Abbreviation from capitals (e.g., "SGI", "WCB", "FCL")
        abbr = "".join(c for c in name if c.isupper())
        if len(abbr) >= 2:
            candidates[abbr.lower()] = name
        # First word if distinctive enough
        first = name.split()[0] if name.split() else ""
        if len(first) > 3:
            candidates[first.lower()] = name
    return candidates


def match_account(text, known_accounts):
    """Fuzzy match an account name from transcription text."""
    text_lower = text.lower()
    candidates = build_match_candidates(known_accounts)

    # 1. Exact substring match (longest first for specificity)
    sorted_names = sorted(candidates.keys(), key=len, reverse=True)
    for cand in sorted_names:
        if len(cand) >= 4 and cand in text_lower:
            return candidates[cand]

    # 2. Try "at [Account]" or "for [Account]" or "about [Account]" patterns
    prep_match = re.search(r"(?:at|for|about|with|from|regarding)\s+(.+?)(?:\s+about|\s+regarding|\s*[,.]|\s+and\b|\s+they|\s+we|\s+I\b|$)", text, re.IGNORECASE)
    if prep_match:
        fragment = prep_match.group(1).strip()
        # Try fuzzy match on the fragment
        matches = get_close_matches(fragment.lower(), list(candidates.keys()), n=1, cutoff=0.6)
        if matches:
            return candidates[matches[0]]

    # 3. Fuzzy match each 2-4 word window against known accounts
    words = text.split()
    for window_size in (4, 3, 2):
        for i in range(len(words) - window_size + 1):
            fragment = " ".join(words[i:i + window_size])
            matches = get_close_matches(fragment.lower(), list(candidates.keys()), n=1, cutoff=0.65)
            if matches:
                return candidates[matches[0]]

    return ""


def build_summary(text, account, contact, activity_type):
    """Extract the core summary — strip out the account/contact/type preamble."""
    summary = text.strip()
    # Remove common preambles
    preambles = [
        r"^(?:I |just |hey |log a \w+ |note |update )",
        r"^(?:called|emailed|met with|had a meeting with|spoke (?:to|with)|talked (?:to|with))\s+",
    ]
    for p in preambles:
        summary = re.sub(p, "", summary, flags=re.IGNORECASE).strip()

    # If summary is very similar to original, just use it as-is
    if len(summary) < 10:
        summary = text.strip()

    # Capitalize first letter
    if summary:
        summary = summary[0].upper() + summary[1:]

    return summary


def post_to_calproxy(account, contact, activity_type, summary):
    """Post the structured activity to cal-proxy notes endpoint."""
    payload = {
        "text": f"[VOICE LOG] {summary}",
        "account": account,
        "type": activity_type,
        "contact": contact,
        "source": "voice",
        "timestamp": datetime.now().isoformat(),
    }
    try:
        r = requests.post(
            f"{CAL_PROXY}/notes",
            json=payload,
            timeout=5,
        )
        return r.status_code == 200
    except Exception as e:
        print(f"Warning: Could not post to cal-proxy: {e}", file=sys.stderr)
        return False


def process_transcription(text):
    """Main entry point — parse transcription and log activity."""
    known_accounts = fetch_known_accounts()

    activity_type = detect_activity_type(text)
    account = match_account(text, known_accounts)
    contact = extract_contact_name(text, account)
    summary = build_summary(text, account, contact, activity_type)

    result = {
        "account": account,
        "contact": contact,
        "activity_type": activity_type,
        "summary": summary,
        "matched": bool(account),
        "timestamp": datetime.now().isoformat(),
    }

    if not account:
        msg = f"Could not match an account from: \"{text}\"\nDetected type: {activity_type}"
        if contact:
            msg += f"\nContact found: {contact}"
        msg += "\nPlease specify the account name."
        print(msg)
        result["error"] = "account_not_matched"
        return result

    # Post to cal-proxy
    posted = post_to_calproxy(account, contact, activity_type, summary)
    result["posted"] = posted

    # Build confirmation message
    confirm = f"Logged {activity_type}"
    if contact:
        confirm += f" with {contact}"
    confirm += f" at {account}: {summary}"
    if not posted:
        confirm += " (note: cal-proxy sync pending)"

    print(confirm)
    result["confirmation"] = confirm
    return result


def main():
    parser = argparse.ArgumentParser(description="Voice-to-CRM — parse transcriptions into activity logs")
    parser.add_argument("--text", required=True, help="Voice transcription text to parse")
    parser.add_argument("--json", action="store_true", help="Output structured JSON instead of text")
    args = parser.parse_args()

    result = process_transcription(args.text)

    if args.json:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Morning Pipeline Briefing — generates a spoken daily summary and converts to MP3."""

import json
import os
import sys
from datetime import datetime, date

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CAL_PROXY = "http://127.0.0.1:18790"
TARGET = 3_000_000

STAGE_CONFIG = {
    "Prospecting":     {"prob": 5,   "maxDays": 42},
    "Discovery":       {"prob": 20,  "maxDays": 70},
    "Solution Design": {"prob": 35,  "maxDays": 98},
    "Proposal":        {"prob": 50,  "maxDays": 70},
    "Negotiation":     {"prob": 75,  "maxDays": 98},
    "Verbal Commit":   {"prob": 90,  "maxDays": 42},
    "Closed Won":      {"prob": 100, "maxDays": 0},
}


def fetch_json(endpoint):
    try:
        r = requests.get(f"{CAL_PROXY}{endpoint}", timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"Warning: Could not reach {endpoint}: {e}", file=sys.stderr)
        return None


def fetch_full_accounts():
    """Fetch full account data from backup endpoint for richer briefing."""
    backup = fetch_json("/backup")
    if not backup or "keys" not in backup:
        return {}
    accounts = {}
    for key, val in backup.get("keys", {}).items():
        if key.startswith("xits_acct_"):
            name = key.replace("xits_acct_", "").replace("_", " ").strip()
            try:
                accounts[name] = json.loads(val) if isinstance(val, str) else val
            except (json.JSONDecodeError, TypeError):
                pass
    return accounts


def days_since(date_str):
    if not date_str:
        return 0
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        return (date.today() - d).days
    except (ValueError, TypeError):
        return 0


def fmt_money(val):
    if val >= 1_000_000:
        return f"${val / 1_000_000:.1f} million"
    if val >= 1_000:
        return f"${val / 1_000:.0f} thousand"
    return f"${val:.0f}"


def generate_briefing():
    today = date.today()
    day_name = today.strftime("%A")
    month_day = today.strftime("%B %d")

    # Fetch pipeline deals
    pipeline_data = fetch_json("/pipeline")
    deals = pipeline_data.get("deals", []) if pipeline_data else []

    # Fetch full account data for health, meddpicc, competitors
    full_accounts = fetch_full_accounts()

    # Fetch recent notes
    notes_data = fetch_json("/notes")
    notes = notes_data if isinstance(notes_data, list) else []

    # --- Classify deals ---
    active_deals = [d for d in deals if d.get("stage") not in ("Closed Won", "Closed Lost", "Fresh", "", None)]
    closed_won = [d for d in deals if d.get("stage") == "Closed Won"]
    closed_lost = [d for d in deals if d.get("stage") == "Closed Lost"]

    total_pipeline = sum(d.get("value", 0) for d in active_deals)
    weighted_pipeline = sum(
        d.get("value", 0) * STAGE_CONFIG.get(d.get("stage", ""), {}).get("prob", 0) / 100
        for d in active_deals
    )
    closed_won_value = sum(d.get("value", 0) for d in closed_won)

    # Top deals by value
    top_deals = sorted(active_deals, key=lambda d: d.get("value", 0), reverse=True)[:3]

    # Enrich deals with full account data
    for deal in deals:
        acct_name = deal.get("account", "")
        # Try matching by lowercase key
        for key, data in full_accounts.items():
            if key.lower().replace(" ", "_") in acct_name.lower().replace(" ", "_") or \
               acct_name.lower().replace(" ", "_") in key.lower().replace(" ", "_"):
                deal["_full"] = data
                break

    # At-risk: stale or low health
    at_risk = []
    for d in active_deals:
        full = d.get("_full", {})
        stage_entered = full.get("stageEnteredDate", "")
        days_in = days_since(stage_entered)
        max_days = STAGE_CONFIG.get(d.get("stage", ""), {}).get("maxDays", 999)
        health = full.get("healthScore", 100)  # default high if missing

        stale = days_in > max_days and max_days > 0
        low_health = isinstance(health, (int, float)) and health < 40

        if stale or low_health:
            reason = []
            if stale:
                reason.append(f"{days_in} days in {d['stage']}")
            if low_health:
                reason.append(f"health score {health}")
            at_risk.append({"deal": d, "reasons": reason})

    # Competitive threats
    high_threats = []
    for d in active_deals:
        full = d.get("_full", {})
        comp = full.get("competitors", {})
        if isinstance(comp, dict) and comp.get("threatLevel") == "High":
            high_threats.append(d)

    # Today's follow-ups
    today_str = today.isoformat()
    follow_ups = [d for d in active_deals if d.get("followUp", "").startswith(today_str)]

    # Deals closing this month
    this_month = today.strftime("%Y-%m")
    closing_soon = [d for d in active_deals if d.get("closeQ", "").startswith(this_month) or
                    (d.get("stage") in ("Negotiation", "Verbal Commit"))]

    # Recent notes (last 24h)
    recent_notes = []
    for n in notes:
        if n.get("dt", "").startswith(today_str):
            recent_notes.append(n)

    # --- Build the script ---
    lines = []

    # Greeting
    lines.append(f"Good morning Mike. It's {day_name}, {month_day}. Here's your pipeline briefing.")
    lines.append("")

    # Quota attainment
    if closed_won_value > 0:
        pct = closed_won_value / TARGET * 100
        lines.append(f"Quota check. You've closed {fmt_money(closed_won_value)} against your {fmt_money(TARGET)} target. That's {pct:.0f}% attainment.")
    else:
        lines.append(f"You're working toward your {fmt_money(TARGET)} target. No closed won deals yet, but let's build that pipeline.")

    # Pipeline overview
    if active_deals:
        lines.append(f"You have {len(active_deals)} active deals worth {fmt_money(total_pipeline)} total. Weighted pipeline sits at {fmt_money(weighted_pipeline)}.")
    else:
        lines.append("Your pipeline is empty right now. Time to get some deals in motion.")

    # Top 3 deals
    if top_deals:
        lines.append("")
        lines.append("Your top deals.")
        for i, d in enumerate(top_deals, 1):
            full = d.get("_full", {})
            stage_entered = full.get("stageEnteredDate", "")
            days_in = days_since(stage_entered)
            val = fmt_money(d.get("value", 0))
            days_str = f", {days_in} days in stage" if days_in > 0 else ""
            lines.append(f"Number {i}. {d['account']}. {val} in {d['stage']}{days_str}.")

    # At-risk deals
    if at_risk:
        lines.append("")
        lines.append(f"Watch out. {'One deal needs' if len(at_risk) == 1 else str(len(at_risk)) + ' deals need'} attention.")
        for item in at_risk[:3]:
            d = item["deal"]
            reasons = " and ".join(item["reasons"])
            lines.append(f"{d['account']} — {reasons}.")

    # Competitive alerts
    if high_threats:
        lines.append("")
        count = len(high_threats)
        lines.append(f"Competitive alert. {'One deal has' if count == 1 else str(count) + ' deals have'} high threat levels.")
        for d in high_threats[:2]:
            full = d.get("_full", {})
            comp = full.get("competitors", {})
            competitor = comp.get("primary", "a competitor")
            lines.append(f"{d['account']} is up against {competitor}.")

    # Follow-ups
    if follow_ups:
        lines.append("")
        lines.append(f"You have {len(follow_ups)} follow-up{'s' if len(follow_ups) != 1 else ''} due today.")
        for d in follow_ups[:3]:
            lines.append(f"{d['account']} — {d.get('stage', 'active')}.")

    # Closing this month
    if closing_soon:
        total_closing = sum(d.get("value", 0) for d in closing_soon)
        lines.append("")
        lines.append(f"{len(closing_soon)} deal{'s' if len(closing_soon) != 1 else ''} in late stage, worth {fmt_money(total_closing)}. Keep pushing those across the line.")

    # Motivational closer
    lines.append("")
    closers = [
        "Let's make it a great day. Every conversation moves the needle.",
        "Stay sharp out there. Saskatchewan is your territory. Own it.",
        "You've got this Mike. One deal at a time. Go get it.",
        "Focus on the next best action for each deal. Momentum wins.",
        "Remember, every call is a chance to move something forward. Have a great day.",
        "Pipeline is built one conversation at a time. Make today count.",
        "Fortune favors the bold. Go open some doors today.",
    ]
    closer_idx = today.toordinal() % len(closers)
    lines.append(closers[closer_idx])

    return "\n".join(lines)


def main():
    script = generate_briefing()
    print("=" * 60)
    print("MORNING BRIEFING SCRIPT")
    print("=" * 60)
    print(script)
    print("=" * 60)

    # Generate audio
    today_str = date.today().isoformat()
    output_path = os.path.join(SCRIPT_DIR, "briefings", f"briefing-{today_str}.mp3")

    sys.path.insert(0, SCRIPT_DIR)
    from eleven_tts import text_to_speech

    print(f"\nGenerating audio...")
    text_to_speech(script, output_path)
    print(f"Briefing saved to {output_path}")

    return script, output_path


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Weekly Wrap-Up Briefing — Friday audio summary with pipeline movement, wins, and next week preview."""

import json
import os
import sys
from datetime import datetime, date, timedelta

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CAL_PROXY = "http://127.0.0.1:18790"
TARGET = 3_000_000

STAGE_CONFIG = {
    "Prospecting":     {"prob": 5,   "order": 0},
    "Discovery":       {"prob": 20,  "order": 1},
    "Solution Design": {"prob": 35,  "order": 2},
    "Proposal":        {"prob": 50,  "order": 3},
    "Negotiation":     {"prob": 75,  "order": 4},
    "Verbal Commit":   {"prob": 90,  "order": 5},
    "Closed Won":      {"prob": 100, "order": 6},
}


def fetch_json(endpoint):
    try:
        r = requests.get(f"{CAL_PROXY}{endpoint}", timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"Warning: Could not reach {endpoint}: {e}", file=sys.stderr)
        return None


def fmt_money(val):
    if val >= 1_000_000:
        return f"${val / 1_000_000:.1f} million"
    if val >= 1_000:
        return f"${val / 1_000:.0f} thousand"
    return f"${val:.0f}"


def days_since(date_str):
    if not date_str:
        return 0
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        return (date.today() - d).days
    except (ValueError, TypeError):
        return 0


def is_this_week(date_str):
    """Check if a date string falls within the current Mon-Fri work week."""
    if not date_str:
        return False
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        return monday <= d <= today
    except (ValueError, TypeError):
        return False


def is_next_week(date_str):
    """Check if a date string falls within next Mon-Fri."""
    if not date_str:
        return False
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        today = date.today()
        next_monday = today + timedelta(days=(7 - today.weekday()))
        next_friday = next_monday + timedelta(days=4)
        return next_monday <= d <= next_friday
    except (ValueError, TypeError):
        return False


def generate_weekly_wrap():
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    week_range = f"{monday.strftime('%B %d')} to {today.strftime('%B %d')}"

    # Fetch data
    pipeline_data = fetch_json("/pipeline")
    deals = pipeline_data.get("deals", []) if pipeline_data else []

    notes_data = fetch_json("/notes")
    notes = notes_data if isinstance(notes_data, list) else []

    backup = fetch_json("/backup")
    full_accounts = {}
    if backup and "keys" in backup:
        for key, val in backup.get("keys", {}).items():
            if key.startswith("xits_acct_"):
                try:
                    data = json.loads(val) if isinstance(val, str) else val
                    name = key.replace("xits_acct_", "").replace("_", " ").strip()
                    full_accounts[name] = data
                except (json.JSONDecodeError, TypeError):
                    pass

    def get_full(account_name):
        for name, data in full_accounts.items():
            if name.lower() == account_name.lower().replace(" ", " "):
                return data
            acct_words = account_name.lower().split()
            if all(w in name.lower() for w in acct_words if len(w) > 2):
                return data
        return {}

    # --- Classify ---
    active_deals = [d for d in deals if d.get("stage") not in ("Closed Won", "Closed Lost", "Fresh", "", None)]
    closed_won = [d for d in deals if d.get("stage") == "Closed Won"]
    closed_lost = [d for d in deals if d.get("stage") == "Closed Lost"]

    # This week's wins (closed won this week based on stageEnteredDate)
    week_wins = []
    for d in closed_won:
        full = get_full(d.get("account", ""))
        if is_this_week(full.get("stageEnteredDate", "")):
            week_wins.append(d)

    # This week's losses
    week_losses = []
    for d in closed_lost:
        full = get_full(d.get("account", ""))
        if is_this_week(full.get("stageEnteredDate", "")):
            week_losses.append(d)

    # Stage advances this week
    stage_advances = []
    for d in active_deals:
        full = get_full(d.get("account", ""))
        if is_this_week(full.get("stageEnteredDate", "")):
            stage_advances.append(d)

    # Pipeline totals
    total_pipeline = sum(d.get("value", 0) for d in active_deals)
    weighted_pipeline = sum(
        d.get("value", 0) * STAGE_CONFIG.get(d.get("stage", ""), {}).get("prob", 0) / 100
        for d in active_deals
    )
    closed_won_value = sum(d.get("value", 0) for d in closed_won)

    # Activity stats from notes this week
    week_notes = [n for n in notes if is_this_week(n.get("dt", ""))]
    activity_counts = {"call": 0, "email": 0, "meeting": 0, "note": 0}
    for n in week_notes:
        ntype = n.get("type", "note")
        text = n.get("text", "").lower()
        if ntype in activity_counts:
            activity_counts[ntype] += 1
        elif "call" in text:
            activity_counts["call"] += 1
        elif "email" in text:
            activity_counts["email"] += 1
        elif "meeting" in text or "met with" in text:
            activity_counts["meeting"] += 1
        else:
            activity_counts["note"] += 1
    total_activities = sum(activity_counts.values())

    # Deals closing next week (Negotiation/Verbal Commit or closeQ matches)
    next_week_deals = []
    for d in active_deals:
        full = get_full(d.get("account", ""))
        close_q = d.get("closeQ", "") or full.get("closeQ", "")
        if d.get("stage") in ("Negotiation", "Verbal Commit"):
            next_week_deals.append(d)
        elif is_next_week(close_q):
            next_week_deals.append(d)

    # Overdue follow-ups
    overdue = []
    for d in active_deals:
        follow_up = d.get("followUp", "")
        if follow_up and follow_up < today.isoformat() and days_since(follow_up) <= 14:
            overdue.append(d)

    # --- Build Script ---
    lines = []

    # Opening
    lines.append(f"Hey Mike, it's Friday. Here's your weekly wrap-up for {week_range}.")
    lines.append("")

    # Section 1: Wins
    if week_wins:
        win_val = sum(d.get("value", 0) for d in week_wins)
        lines.append(f"This week's wins. You closed {len(week_wins)} deal{'s' if len(week_wins) != 1 else ''} worth {fmt_money(win_val)}.")
        for d in week_wins:
            lines.append(f"{d['account']} for {fmt_money(d.get('value', 0))}.")
    else:
        lines.append("No new wins this week, but let's keep the momentum building.")

    if week_losses:
        loss_val = sum(d.get("value", 0) for d in week_losses)
        lines.append(f"On the flip side, {len(week_losses)} deal{'s' if len(week_losses) != 1 else ''} went to closed lost, totaling {fmt_money(loss_val)}.")

    # Section 2: Pipeline movement
    lines.append("")
    if stage_advances:
        lines.append(f"Pipeline movement. {len(stage_advances)} deal{'s' if len(stage_advances) != 1 else ''} advanced this week.")
        for d in stage_advances[:5]:
            lines.append(f"{d['account']} moved to {d.get('stage', 'active')}.")
    else:
        lines.append("No stage advances this week. Let's push some deals forward next week.")

    lines.append(f"Your active pipeline sits at {fmt_money(total_pipeline)} across {len(active_deals)} deals. Weighted pipeline is {fmt_money(weighted_pipeline)}.")

    # Quota check
    if closed_won_value > 0:
        pct = closed_won_value / TARGET * 100
        remaining = TARGET - closed_won_value
        lines.append(f"You're at {pct:.0f}% of your {fmt_money(TARGET)} target with {fmt_money(remaining)} to go.")
    else:
        lines.append(f"Working toward your {fmt_money(TARGET)} target. Pipeline is building.")

    # Section 3: Activity stats
    lines.append("")
    if total_activities > 0:
        parts = []
        if activity_counts["call"] > 0:
            parts.append(f"{activity_counts['call']} call{'s' if activity_counts['call'] != 1 else ''}")
        if activity_counts["email"] > 0:
            parts.append(f"{activity_counts['email']} email{'s' if activity_counts['email'] != 1 else ''}")
        if activity_counts["meeting"] > 0:
            parts.append(f"{activity_counts['meeting']} meeting{'s' if activity_counts['meeting'] != 1 else ''}")
        if activity_counts["note"] > 0:
            parts.append(f"{activity_counts['note']} note{'s' if activity_counts['note'] != 1 else ''}")
        lines.append(f"Activity this week. {total_activities} total touchpoints: {', '.join(parts)}.")
    else:
        lines.append("No activities logged this week. Try using the voice logger to capture calls and meetings next week.")

    # Section 4: Next week preview
    lines.append("")
    if next_week_deals or overdue:
        lines.append("Looking ahead to next week.")
        if next_week_deals:
            nw_val = sum(d.get("value", 0) for d in next_week_deals)
            lines.append(f"{len(next_week_deals)} deal{'s' if len(next_week_deals) != 1 else ''} in late stage worth {fmt_money(nw_val)}.")
            for d in next_week_deals[:3]:
                lines.append(f"{d['account']} in {d.get('stage', 'pipeline')}.")
        if overdue:
            lines.append(f"You also have {len(overdue)} overdue follow-up{'s' if len(overdue) != 1 else ''}. Don't let those slip.")
            for d in overdue[:3]:
                lines.append(f"{d['account']}.")
    else:
        lines.append("No late-stage deals or overdue follow-ups on the radar for next week. Good time to prospect and fill the top of funnel.")

    # Closer
    lines.append("")
    closers = [
        "Have a great weekend Mike. Rest up and come back Monday ready to close.",
        "Good week of work. Enjoy the weekend and we'll hit it hard on Monday.",
        "That's a wrap. Recharge this weekend, Saskatchewan is yours to win.",
        "Nice work this week. Every call and meeting counts. See you Monday.",
    ]
    closer_idx = today.isocalendar()[1] % len(closers)
    lines.append(closers[closer_idx])

    return "\n".join(lines)


def send_telegram(text, audio_path=None):
    config_path = os.path.join(SCRIPT_DIR, "voice-config.json")
    try:
        with open(config_path) as f:
            config = json.load(f)
    except Exception:
        return False

    token = config.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = config.get("TELEGRAM_CHAT_ID", "")
    if "YOUR_" in token or "YOUR_" in chat_id:
        print("Telegram not configured — skipping send", file=sys.stderr)
        return False

    if audio_path and os.path.exists(audio_path):
        try:
            with open(audio_path, "rb") as f:
                requests.post(
                    f"https://api.telegram.org/bot{token}/sendAudio",
                    data={"chat_id": chat_id, "title": f"Weekly Wrap {date.today().isoformat()}", "performer": "SK Command Center"},
                    files={"audio": f},
                    timeout=30,
                )
        except Exception as e:
            print(f"Warning: Telegram audio failed: {e}", file=sys.stderr)

    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
    except Exception as e:
        print(f"Warning: Telegram text failed: {e}", file=sys.stderr)

    return True


def main():
    script = generate_weekly_wrap()

    print("=" * 60)
    print("WEEKLY WRAP-UP")
    print("=" * 60)
    print(script)
    print("=" * 60)

    # Save text version
    today_str = date.today().isoformat()
    md_path = os.path.join(SCRIPT_DIR, "weekly", f"wrap-{today_str}.md")
    os.makedirs(os.path.dirname(md_path), exist_ok=True)
    with open(md_path, "w") as f:
        f.write(f"# Weekly Wrap-Up — {today_str}\n\n")
        f.write(script)
    print(f"\nText saved to {md_path}")

    # Generate audio
    mp3_path = os.path.join(SCRIPT_DIR, "weekly", f"wrap-{today_str}.mp3")
    sys.path.insert(0, SCRIPT_DIR)
    from eleven_tts import text_to_speech

    print("Generating audio...")
    text_to_speech(script, mp3_path)

    # Send via Telegram
    telegram_text = f"*Weekly Wrap-Up — {today_str}*\n\n{script}"
    send_telegram(telegram_text, mp3_path)

    print("Weekly wrap complete.")


if __name__ == "__main__":
    main()

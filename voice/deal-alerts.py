#!/usr/bin/env python3
"""Deal Alert Audio Notifications — spoken alerts for critical pipeline changes."""

import json
import hashlib
import os
import sys
from datetime import datetime, date

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CAL_PROXY = "http://127.0.0.1:18790"
STATE_FILE = os.path.join(SCRIPT_DIR, "alert-state.json")
ALERT_MP3 = os.path.join(SCRIPT_DIR, "briefings", f"alerts-{date.today().isoformat()}.mp3")

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


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"sent": {}, "last_run": None}


def save_state(state):
    state["last_run"] = datetime.now().isoformat()
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def alert_key(alert_type, account):
    """Generate a unique key for deduplication. Resets daily."""
    raw = f"{date.today().isoformat()}|{alert_type}|{account}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


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
        return f"${val / 1_000:.0f}k"
    return f"${val:.0f}"


def check_alerts():
    """Check all alert conditions and return list of new alerts."""
    pipeline_data = fetch_json("/pipeline")
    deals = pipeline_data.get("deals", []) if pipeline_data else []

    # Fetch full account data for health, meddpicc, competitors
    backup = fetch_json("/backup")
    full_accounts = {}
    if backup and "keys" in backup:
        for key, val in backup.get("keys", {}).items():
            if key.startswith("xits_acct_"):
                try:
                    full_accounts[key] = json.loads(val) if isinstance(val, str) else val
                except (json.JSONDecodeError, TypeError):
                    pass

    def get_full(account_name):
        """Match a deal's account name to its full localStorage data."""
        for key, data in full_accounts.items():
            name_from_key = key.replace("xits_acct_", "").replace("_", " ").strip()
            if name_from_key.lower() == account_name.lower().replace(" ", " "):
                return data
            # Fuzzy: check if account name words appear in key
            acct_words = account_name.lower().split()
            if all(w in key.lower() for w in acct_words if len(w) > 2):
                return data
        return {}

    state = load_state()
    alerts = []

    for deal in deals:
        account = deal.get("account", "")
        stage = deal.get("stage", "")
        value = deal.get("value", 0) or 0
        full = get_full(account)

        # 1. Closed Won — celebrate
        if stage == "Closed Won":
            key = alert_key("closed_won", account)
            if key not in state["sent"]:
                alerts.append({
                    "key": key,
                    "type": "closed_won",
                    "account": account,
                    "message": f"Great news! {account} just closed won for {fmt_money(value)}. Congratulations Mike, that's a big win.",
                })

        # 2. Stale deal — 7+ days past critical threshold
        if stage in STAGE_CONFIG and stage not in ("Closed Won", "Closed Lost"):
            stage_entered = full.get("stageEnteredDate", "")
            days_in = days_since(stage_entered)
            max_days = STAGE_CONFIG[stage]["maxDays"]
            if max_days > 0 and days_in > max_days + 7:
                key = alert_key("stale", account)
                if key not in state["sent"]:
                    alerts.append({
                        "key": key,
                        "type": "stale",
                        "account": account,
                        "message": f"Alert. {account} has been stuck in {stage} for {days_in} days. That's {days_in - max_days} days past the critical threshold. Time to re-engage or reassess.",
                    })

        # 3. Health score below 20 on deal worth $50K+
        if stage not in ("Closed Won", "Closed Lost", "Fresh", "", None) and value >= 50000:
            health = full.get("healthScore")
            if health is None:
                # Try computing from activities/contacts if healthScore not stored directly
                pass
            if isinstance(health, (int, float)) and health < 20:
                key = alert_key("low_health", account)
                if key not in state["sent"]:
                    alerts.append({
                        "key": key,
                        "type": "low_health",
                        "account": account,
                        "message": f"Warning. {account} has a health score of just {health} on a {fmt_money(value)} deal. This relationship needs immediate attention.",
                    })

        # 4. Competitor threat level changed to High
        competitors = full.get("competitors", {})
        if isinstance(competitors, dict) and competitors.get("threatLevel") == "High":
            if stage not in ("Closed Won", "Closed Lost", "Fresh", "", None):
                primary = competitors.get("primary", "a competitor")
                key = alert_key("high_threat", account)
                if key not in state["sent"]:
                    alerts.append({
                        "key": key,
                        "type": "high_threat",
                        "account": account,
                        "message": f"Competitive alert. {account} has a high threat level from {primary}. Review your differentiators and champion engagement.",
                    })

        # 5. Deal closing within 7 days with MEDDPICC < 60%
        if stage in ("Negotiation", "Verbal Commit"):
            meddpicc = full.get("meddpicc", {})
            if isinstance(meddpicc, dict) and meddpicc:
                scores = [int(v) for v in meddpicc.values() if isinstance(v, (int, float, str)) and str(v).isdigit()]
                if scores:
                    meddpicc_pct = round(sum(scores) / (len(scores) * 10) * 100)
                    if meddpicc_pct < 60:
                        key = alert_key("meddpicc_gap", account)
                        if key not in state["sent"]:
                            alerts.append({
                                "key": key,
                                "type": "meddpicc_gap",
                                "account": account,
                                "message": f"Qualification gap. {account} is in {stage} but MEDDPICC is only {meddpicc_pct}%. Shore up your qualification before pushing for close.",
                            })

    return alerts, state


def send_telegram(text, audio_path=None):
    """Send text and optional audio to Telegram."""
    config_path = os.path.join(SCRIPT_DIR, "voice-config.json")
    try:
        with open(config_path) as f:
            config = json.load(f)
    except Exception:
        print("Warning: Could not read voice-config.json", file=sys.stderr)
        return False

    token = config.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = config.get("TELEGRAM_CHAT_ID", "")
    if "YOUR_" in token or "YOUR_" in chat_id:
        print("Telegram not configured — skipping send", file=sys.stderr)
        return False

    success = True

    # Send audio if available
    if audio_path and os.path.exists(audio_path):
        try:
            with open(audio_path, "rb") as f:
                resp = requests.post(
                    f"https://api.telegram.org/bot{token}/sendAudio",
                    data={"chat_id": chat_id, "title": f"Deal Alert {date.today().isoformat()}"},
                    files={"audio": f},
                    timeout=30,
                )
            if not resp.json().get("ok"):
                success = False
        except Exception as e:
            print(f"Warning: Telegram audio send failed: {e}", file=sys.stderr)
            success = False

    # Send text
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
    except Exception as e:
        print(f"Warning: Telegram text send failed: {e}", file=sys.stderr)
        success = False

    return success


def main():
    alerts, state = check_alerts()

    if not alerts:
        print("No new alerts.")
        return

    # Build combined script
    lines = [f"You have {len(alerts)} pipeline {'alert' if len(alerts) == 1 else 'alerts'}."]
    for a in alerts:
        lines.append(a["message"])
    script = " ".join(lines)

    print("=" * 50)
    print("DEAL ALERTS")
    print("=" * 50)
    for a in alerts:
        icon = {"closed_won": "🎉", "stale": "⏰", "low_health": "🔴", "high_threat": "⚔️", "meddpicc_gap": "📋"}.get(a["type"], "⚠️")
        print(f"  {icon} [{a['type']}] {a['account']}: {a['message']}")
    print("=" * 50)

    # Generate audio
    sys.path.insert(0, SCRIPT_DIR)
    from eleven_tts import text_to_speech

    print("\nGenerating audio...")
    text_to_speech(script, ALERT_MP3)

    # Send via Telegram
    telegram_text = f"*Deal Alerts — {date.today().isoformat()}*\n\n"
    for a in alerts:
        icon = {"closed_won": "🎉", "stale": "⏰", "low_health": "🔴", "high_threat": "⚔️", "meddpicc_gap": "📋"}.get(a["type"], "⚠️")
        telegram_text += f"{icon} *{a['account']}*: {a['message']}\n\n"

    send_telegram(telegram_text, ALERT_MP3)

    # Mark alerts as sent
    for a in alerts:
        state["sent"][a["key"]] = {
            "type": a["type"],
            "account": a["account"],
            "sent_at": datetime.now().isoformat(),
        }

    # Prune old sent keys (older than 7 days)
    cutoff = date.today().isoformat()[:8]  # YYYY-MM-
    to_remove = []
    for key, info in state["sent"].items():
        sent_date = info.get("sent_at", "")[:10]
        if sent_date and days_since(sent_date) > 7:
            to_remove.append(key)
    for key in to_remove:
        del state["sent"][key]

    save_state(state)
    print(f"\n{len(alerts)} alert(s) sent and recorded.")


if __name__ == "__main__":
    main()

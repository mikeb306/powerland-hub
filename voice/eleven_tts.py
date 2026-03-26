#!/usr/bin/env python3
"""TTS script — converts text to speech using OpenAI TTS API and saves as MP3.

Originally used ElevenLabs; swapped to OpenAI TTS (2026-03-18) because ElevenLabs
credits were exhausted. The function signature is unchanged so all importers
(morning-briefing.py, weekly-wrap.py, deal-alerts.py) continue to work.
"""

import argparse
import json
import os
import sys

import requests

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voice-config.json")
OPENCLAW_CONFIG = os.path.expanduser("~/.openclaw/openclaw.json")


def load_config():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def _get_openai_key():
    """Load OpenAI API key from openclaw.json (under env.OPENAI_API_KEY)."""
    try:
        with open(OPENCLAW_CONFIG, "r") as f:
            data = json.load(f)
        key = data.get("env", {}).get("OPENAI_API_KEY", "") or data.get("OPENAI_API_KEY", "")
        if key:
            return key
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass

    # Fallback: environment variable
    key = os.environ.get("OPENAI_API_KEY", "")
    if key:
        return key

    print("ERROR: No OPENAI_API_KEY found in ~/.openclaw/openclaw.json or environment", file=sys.stderr)
    sys.exit(1)


def text_to_speech(text, output_path, config=None):
    if config is None:
        config = load_config()

    model = config.get("OPENAI_TTS_MODEL", "tts-1")
    voice = config.get("OPENAI_TTS_VOICE", "nova")
    api_key = _get_openai_key()

    url = "https://api.openai.com/v1/audio/speech"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "input": text,
        "voice": voice,
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=120)

    if resp.status_code != 200:
        print(f"ERROR: OpenAI TTS API returned {resp.status_code}", file=sys.stderr)
        print(resp.text[:500], file=sys.stderr)
        sys.exit(1)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(resp.content)

    size_kb = len(resp.content) / 1024
    print(f"Saved {output_path} ({size_kb:.1f} KB, {len(text)} chars)")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="OpenAI Text-to-Speech")
    parser.add_argument("--text", required=True, help="Text to convert to speech")
    parser.add_argument(
        "--output",
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "test.mp3"),
        help="Output MP3 file path",
    )
    args = parser.parse_args()
    text_to_speech(args.text, args.output)


if __name__ == "__main__":
    main()

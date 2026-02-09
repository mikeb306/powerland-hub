#!/usr/bin/env python3
"""ElevenLabs TTS script — converts text to speech and saves as MP3."""

import argparse
import json
import os
import sys

import requests

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voice-config.json")


def load_config():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def text_to_speech(text, output_path, config=None):
    if config is None:
        config = load_config()

    api_key = config["ELEVEN_API_KEY"]
    voice_id = config["VOICE_ID"]
    model_id = config.get("MODEL_ID", "eleven_multilingual_v2")

    if api_key == "YOUR_ELEVENLABS_API_KEY_HERE":
        print("ERROR: Set your ELEVEN_API_KEY in voice-config.json", file=sys.stderr)
        sys.exit(1)
    if voice_id == "YOUR_VOICE_ID_HERE":
        print("ERROR: Set your VOICE_ID in voice-config.json", file=sys.stderr)
        sys.exit(1)

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": api_key,
    }
    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.3,
            "use_speaker_boost": True,
        },
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=60)

    if resp.status_code != 200:
        print(f"ERROR: ElevenLabs API returned {resp.status_code}", file=sys.stderr)
        print(resp.text[:500], file=sys.stderr)
        sys.exit(1)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(resp.content)

    size_kb = len(resp.content) / 1024
    print(f"Saved {output_path} ({size_kb:.1f} KB, {len(text)} chars)")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="ElevenLabs Text-to-Speech")
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

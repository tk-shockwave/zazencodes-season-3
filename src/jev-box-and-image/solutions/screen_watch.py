"""Watch your screen with Jev.

Every second: take a screenshot, ask Jev what you're doing and how focused it
looks, log the answer and what it cost, and send a macOS notification when you
drift.

    uv run solutions/screen_watch.py
    uv run solutions/screen_watch.py --interval 5
"""

import argparse
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image as PILImage
from typesafe_sdk import Choice, Image, Noul, Score, TypeSafeClient

SCREENSHOT = Path("screen.png")
LOG = Path("screen_log.jsonl")
MAX_SIDE = 1568  # Jev rejects images with a side over 1568 px
USD_PER_INPUT_TOKEN = 0.042 / 1_000_000  # output tokens are free

QUESTIONS = {
    "activity": Choice(
        instructions="What is the person at this computer doing?",
        criteria={
            "coding": "An editor, terminal, or IDE with code",
            "writing": "Docs, notes, or email being written",
            "meeting": "A video call",
            "browsing": "Web pages, news, social media, or video",
        },
    ),
    "focus": Score(
        instructions="How focused on deep work does this screen look?",
        criteria=["Distracted", "Drifting", "Working", "Deep work"],
    ),
    "distracted": Noul(
        instructions="Is the person distracted by social media, videos, shopping, or news?",
    ),
}


def screenshot() -> Image:
    subprocess.run(["screencapture", "-x", "-C", str(SCREENSHOT)], check=True)
    img = PILImage.open(SCREENSHOT).convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    return Image.from_pil(img)


def notify(message: str) -> None:
    subprocess.run(["osascript", "-e", f'display notification "{message}" with title "Jev"'], check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=float, default=1, help="Seconds between screenshots")
    parser.add_argument("--threshold", type=float, default=0.8, help="Distracted probability that triggers a notification")
    args = parser.parse_args()

    load_dotenv()
    client = TypeSafeClient(headers={"TypeSafe-Danger-Zone-Images": "true"})
    total_cost = 0.0

    while True:
        start = time.perf_counter()
        response = client.system_one(state=screenshot(), questions=QUESTIONS)
        ms = (time.perf_counter() - start) * 1000

        activity = response.choices["activity"]
        focus = response.scores["focus"]
        distracted = response.nouls["distracted"].noul
        cost = response.usage.input_tokens * USD_PER_INPUT_TOKEN
        total_cost += cost

        entry = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "activity": activity.choice,
            "activity_confidence": round(activity.confidence, 3),
            "focus": round(focus.score, 2),
            "distracted": round(distracted, 3),
            "ms": round(ms),
            "cost_usd": round(cost, 8),
            "total_cost_usd": round(total_cost, 8),
        }
        with LOG.open("a") as f:
            f.write(json.dumps(entry) + "\n")
        print(
            f"{entry['time']}  {activity.choice:<9} focus {focus.score:.2f}/3  distracted {distracted:.0%}"
            f"  {ms:.0f} ms  ${cost:.6f}  total ${total_cost:.4f}"
        )

        if distracted >= args.threshold:
            notify(f"Looks like {activity.choice}. Back to it?")

        time.sleep(max(0, args.interval - (time.perf_counter() - start)))


if __name__ == "__main__":
    main()

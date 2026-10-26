"""Send a test alert to the phone on every configured channel: python scripts/admin/send_alert.py "text" [--urgent] [--url URL]"""
import argparse
import os
import sys

from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # scripts/<group>/<this file> -> the checkout
sys.path.insert(0, os.path.join(ROOT, "core"))
load_dotenv(os.path.join(ROOT, ".env"))

from inverse_core import notify  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("text")
ap.add_argument("--urgent", action="store_true")
ap.add_argument("--url")
a = ap.parse_args()
print("channels configured:", ", ".join(notify.channels()) or "none")
print("sent on:", ", ".join(notify.notify(a.text, urgent=a.urgent, url=a.url)) or "nothing")

"""Reach a person's phone when the crew needs a decision: free channels only, chosen by what .env holds.
- ntfy.sh push (NTFY_TOPIC): no account; the ntfy app on the phone subscribes to the topic; priority 5 rings like a call.
- Telegram (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID): a bot message.
- SMS through a carrier's email gateway (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, NOTIFY_SMS_TO such as 10digits@vtext.com): a
  short text, free with the carrier; the SMTP account is the sender's own.
- Textbelt (TEXTBELT_TO, a number with country code such as 1555xxxxxxx): one free text a day with the public key "textbelt", no
  account; TEXTBELT_KEY holds a paid key if more are wanted. Used for the alerts that matter (an approval, a merge), not for chatter.
Nothing here is required; with no channel configured notify() returns an empty list and the request stays in the chat and the
council's task cards. Never raises."""
from __future__ import annotations

import json
import os
import smtplib
import time
from email.message import EmailMessage

import requests

from . import chat


def channels():
    env = os.environ.get
    out = []
    if env("NTFY_TOPIC"):
        out.append("ntfy")
    if env("TELEGRAM_BOT_TOKEN") and env("TELEGRAM_CHAT_ID"):
        out.append("telegram")
    if env("SMTP_HOST") and env("SMTP_USER") and env("SMTP_PASS") and env("NOTIFY_SMS_TO"):
        out.append("sms")
    if env("TEXTBELT_TO"):
        out.append("textbelt")
    return out


def notify(text, title="INVERSE crew", urgent=False, url=None):
    """Send `text` on every configured channel; returns the names of the channels that accepted it."""
    sent, env = [], os.environ.get
    body = str(text)[:1500]
    if env("NTFY_TOPIC"):
        try:
            headers = {"Title": title, "Priority": "5" if urgent else "3", "Tags": "rotating_light" if urgent else "robot"}
            if url:
                headers["Click"] = url
            requests.post(f"https://ntfy.sh/{env('NTFY_TOPIC')}", data=body.encode("utf-8"), headers=headers, timeout=10).raise_for_status()
            sent.append("ntfy")
        except Exception:
            pass
    if env("TELEGRAM_BOT_TOKEN") and env("TELEGRAM_CHAT_ID"):
        try:
            requests.post(f"https://api.telegram.org/bot{env('TELEGRAM_BOT_TOKEN')}/sendMessage",
                          json={"chat_id": env("TELEGRAM_CHAT_ID"), "text": f"{title}\n{body}" + (f"\n{url}" if url else "")}, timeout=10).raise_for_status()
            sent.append("telegram")
        except Exception:
            pass
    if env("SMTP_HOST") and env("SMTP_USER") and env("SMTP_PASS") and env("NOTIFY_SMS_TO"):
        try:
            msg = EmailMessage()
            msg["From"], msg["To"], msg["Subject"] = env("SMTP_USER"), env("NOTIFY_SMS_TO"), title[:40]
            msg.set_content((body[:120] + (" " + url if url else ""))[:160])                 # a carrier gateway keeps about 160 characters
            with smtplib.SMTP(env("SMTP_HOST"), int(env("SMTP_PORT") or 587), timeout=15) as s:
                s.starttls()
                s.login(env("SMTP_USER"), env("SMTP_PASS"))
                s.send_message(msg)
            sent.append("sms")
        except Exception:
            pass
    if env("TEXTBELT_TO") and urgent:                                         # one free text a day: spent on what needs a person, never on chatter
        try:
            r = requests.post("https://textbelt.com/text", data={"phone": env("TEXTBELT_TO"), "message": (f"{title}: {body[:110]}" + (f" {url}" if url else ""))[:300],
                                                                   "key": env("TEXTBELT_KEY") or "textbelt"}, timeout=15)
            if r.ok and r.json().get("success"):
                sent.append("textbelt")
        except Exception:
            pass
    _log(title, body, sent, urgent, url)
    return sent


def _log(title, body, sent, urgent, url):
    """state/alerts.jsonl: when, what, and which channels took it, so the page can show that an alert left even when a phone never got it."""
    try:
        p = os.path.join(chat.root(), "state", "alerts.jsonl")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "title": title, "text": body[:300], "sent": sent, "urgent": bool(urgent), "url": url}) + "\n")
    except OSError:
        pass

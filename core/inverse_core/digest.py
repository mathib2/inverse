"""A short digest of what the crew said since the last one, sent to the phone on the ordinary channels, never urgent. Warden
calls send_if_due at the end of each cycle; NOTIFY_DIGEST_MINUTES (default 30, 0 turns it off) sets the pace. The text is made
by code from state/chat.jsonl: who spoke, what Vera decided, the last results and any alert, so a person away from the page
still knows what the agents are doing."""
from __future__ import annotations

import json
import os
import time
from collections import Counter

from . import chat, notify

NAMES = chat.NAMES


def summary(lines, minutes=30):
    """One paragraph, at most about 900 characters; '' when nothing was said."""
    lines = [m for m in lines if m.get("who") != "you"]
    if not lines:
        return ""
    by_who = Counter(str(m.get("who")) for m in lines)
    who = ", ".join(NAMES.get(w, w) for w, _ in by_who.most_common(4))
    parts = [f"Crew, last {minutes} min: {len(lines)} lines from {who}."]
    reviews = [m for m in lines if m.get("kind") == "review"]
    if reviews:
        accepted = sum(1 for m in reviews if str(m.get("text") or "").upper().startswith("ACCEPT"))
        parts.append(f"Vera: {accepted} accepted, {len(reviews) - accepted} sent back.")
    alerts = [m for m in lines if m.get("kind") == "alert"]
    if alerts:
        parts.append("Alert: " + str(alerts[-1].get("text") or "")[:140])
    for m in [m for m in lines if m.get("kind") in ("result", "answer")][-2:]:
        parts.append(f"{NAMES.get(str(m.get('who')), str(m.get('who')))}: {str(m.get('text') or '')[:120]}")
    return " ".join(parts)[:900]


def send_if_due(root, now=None):
    """Send the digest when the interval has passed and something was said; returns the text sent, or None."""
    minutes = int(os.environ.get("NOTIFY_DIGEST_MINUTES", "30") or 0)
    if minutes <= 0:
        return None
    p, now = os.path.join(root, "state", "digest.json"), now or time.time()
    try:
        with open(p, encoding="utf-8") as f:
            last = float(json.load(f).get("ts") or 0)
    except (OSError, ValueError):
        last = 0.0
    if now - last < minutes * 60:
        return None
    lines = [m for m in chat.tail(400, root) if float(m.get("ts") or 0) > last]
    text = summary(lines, minutes)
    sent = notify.notify(text, title="INVERSE live") if text else []
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"ts": now, "sent": sent, "lines": len(lines)}, f)
    except OSError:
        pass
    return text or None

"""A public HTTPS link to the crew UI, for people outside the tailnet: a Cloudflare quick tunnel (no account, no cost) from
https://<random>.trycloudflare.com to the UI on this machine's loopback. The UI's sign-in page guards it. The current link is
written to state/public_url.json, where the sidebar shows it to signed-in people, and sent to the phone when it changes. The
tunnel is restarted if it drops; a restart gives a new link. Run it through ~/.local/bin/inverse-public start|stop|status|url.

    PYTHONPATH=core python scripts/public_link.py --port 8501

Quick tunnels are Cloudflare's free tier without an account: no uptime promise and a new address after every restart. For a
link that never changes, Tailscale Funnel (docs/operations/ACCESS.md) needs a switch in the Tailscale admin console and sudo once."""
import argparse
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "core"))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"))
from inverse_core import chat, notify  # noqa: E402

URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def state_path(root=ROOT):
    return os.path.join(root, "state", "public_url.json")


def write_url(url, root=ROOT, now=None):
    p = state_path(root)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"url": url, "since": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now or time.time()))}, f)


def read_url(root=ROOT):
    try:
        with open(state_path(root), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def url_in(line):
    m = URL.search(str(line or ""))
    return m.group(0) if m else None


def run(port, binary):
    backoff = 5
    while True:
        cmd = [binary, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"]
        print(time.strftime("%H:%M:%S"), "starting:", " ".join(cmd), flush=True)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        announced = None
        for line in proc.stdout:
            print(line.rstrip(), flush=True)
            url = url_in(line)
            if url and url != announced:
                announced = url
                write_url(url)
                text = f"INVERSE is open at {url} (sign in with the crew's user and password)."
                sent = notify.notify(text, title="INVERSE public link", url=url)
                chat.say("warden", f"The public link is now {url}", kind="note", root_dir=ROOT, notified=sent)
                backoff = 5
        proc.wait()
        write_url("", now=time.time())
        print(time.strftime("%H:%M:%S"), f"tunnel ended ({proc.returncode}); restarting in {backoff} s", flush=True)
        time.sleep(backoff)
        backoff = min(backoff * 2, 300)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("UI_PORT", "8501")))
    ap.add_argument("--binary", default=os.path.expanduser("~/.local/bin/cloudflared"))
    a = ap.parse_args()
    run(a.port, a.binary)


if __name__ == "__main__":
    main()

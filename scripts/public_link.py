"""A public HTTPS link to the crew UI, for people outside the tailnet. The UI's sign-in page guards it. The current link is
written to state/public_url.json, where the sidebar shows it to signed-in people, and sent to the phone when it changes. Run it
through ~/.local/bin/inverse-public start|stop|status|url.

    PYTHONPATH=core python scripts/public_link.py --port 8501

Two ways, the permanent one first:
  Tailscale Funnel  https://<machine>.<tailnet>.ts.net, the same address forever. It works once the tailnet's owner has
                    allowed Funnel for this machine (one click on the link `tailscale funnel` prints, kept in state as
                    "funnel_enable"); this script then sets it up by itself, at start and every FUNNEL_RETRY_S while it
                    runs a quick tunnel, and stops the quick tunnel.
  Cloudflare quick tunnel  https://<random>.trycloudflare.com: no account and no cost, but no uptime promise and a new address
                    after every restart. Used while Funnel is not allowed."""
import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "core"))
from dotenv import load_dotenv

load_dotenv(os.path.join(ROOT, ".env"))
from inverse_core import chat, notify

URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
ENABLE = re.compile(r"https://login\.tailscale\.com/f/funnel\?node=\w+")
FUNNEL_RETRY_S = 900


def state_path(root=ROOT):
    return os.path.join(root, "state", "public_url.json")


def write_url(url, root=ROOT, now=None, **extra):
    p = state_path(root)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"url": url, "since": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now or time.time())), **extra}, f)


def read_url(root=ROOT):
    try:
        with open(state_path(root), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def url_in(line):
    m = URL.search(str(line or ""))
    return m.group(0) if m else None


def funnel(port, sh=subprocess.run):
    """("https://<machine>.<tailnet>.ts.net", None) once Funnel serves the UI, else (None, why). `tailscale funnel --bg` waits for
    the owner's approval when Funnel is not allowed yet, so it gets a short timeout; its approval link is kept in `why`."""
    try:
        out = sh(["tailscale", "funnel", "--bg", "--yes", str(port)], capture_output=True, text=True, timeout=20)
        text, ok = (out.stdout or "") + (out.stderr or ""), out.returncode == 0
    except subprocess.TimeoutExpired as e:
        text, ok = str(e.output or "") + str(e.stderr or ""), False
    except (OSError, subprocess.SubprocessError) as e:
        return None, f"tailscale: {e}"
    link = ENABLE.search(text)
    if link or not ok:
        why = f"Funnel is not allowed for this machine yet; the tailnet owner enables it at {link.group(0)}" if link else \
              ("this user may not change Tailscale's serve settings; run once: sudo tailscale set --operator=$USER" if "denied" in text.lower()
               else f"tailscale funnel failed: {text.strip()[:160]}")
        return None, why
    try:
        st = json.loads(sh(["tailscale", "status", "--json"], capture_output=True, text=True, timeout=10).stdout)
        name = str(st["Self"]["DNSName"]).rstrip(".")
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as e:
        return None, f"Funnel is on but the machine's name is unknown: {e}"
    return f"https://{name}", None


def announce(url, kind):
    write_url(url, kind=kind)
    lasting = " This address does not change." if kind == "funnel" else ""
    sent = notify.notify(f"INVERSE is open at {url} (sign in with the crew's user and password).{lasting}", title="INVERSE public link", url=url)
    chat.say("warden", f"The public link is now {url}", kind="note", root_dir=ROOT, notified=sent)


def run(port, binary):
    backoff, why = 5, None
    while True:
        url, why = funnel(port)
        if url:                                                               # the permanent address: nothing else to run
            print(time.strftime("%H:%M:%S"), "Tailscale Funnel serves", url, flush=True)
            if read_url().get("url") != url:
                announce(url, "funnel")
            while funnel(port)[0] == url:
                time.sleep(FUNNEL_RETRY_S)
            continue
        print(time.strftime("%H:%M:%S"), "no Funnel:", why, flush=True)
        cmd = [binary, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"]
        print(time.strftime("%H:%M:%S"), "starting:", " ".join(cmd), flush=True)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        allowed, done = threading.Event(), threading.Event()

        def watch_funnel():                                                   # the owner may allow Funnel at any time: switch to it
            while not done.wait(FUNNEL_RETRY_S):
                if funnel(port)[0]:
                    allowed.set()
                    proc.terminate()
                    return
        threading.Thread(target=watch_funnel, daemon=True).start()
        announced = None
        for line in proc.stdout:
            print(line.rstrip(), flush=True)
            url = url_in(line)
            if url and url != announced:
                announced = url
                announce(url, "quick")
                write_url(url, kind="quick", funnel_enable=why)
                backoff = 5
        proc.wait()
        done.set()
        if allowed.is_set():
            continue
        write_url("", now=time.time(), funnel_enable=why)
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

"""Set the crew UI's sign-in: writes UI_USER and UI_PASSWORD_HASH (a salted PBKDF2 hash, never the password) into .env, then
restart the UI. Usage: python scripts/admin/set_password.py [user]   (asks for the password twice)
       python scripts/admin/set_password.py [user] --stdin   (reads the password from one line of standard input, for automation)"""
import getpass
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # scripts/<group>/<this file> -> the checkout
sys.path.insert(0, os.path.join(ROOT, "ui"))
from auth import make_hash


def write_env(path, values):
    lines = []
    if os.path.exists(path):
        with open(path) as f:
            lines = f.read().splitlines()
    done = set()
    for i, line in enumerate(lines):
        k = line.split("=", 1)[0].strip()
        if k in values:
            lines[i] = f"{k}={values[k]}"
            done.add(k)
    lines += [f"{k}={v}" for k, v in values.items() if k not in done]
    with open(path, "w") as f:
        f.write("\n".join(lines).rstrip("\n") + "\n")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    user = (args[0] if args else "root").strip()
    if "--stdin" in sys.argv:
        password = sys.stdin.readline().rstrip("\r\n")
    else:
        password = getpass.getpass(f"Password for {user}: ")
        if password != getpass.getpass("Again: "):
            print("The two passwords differ; nothing written.")
            return 1
    if len(password) < 8:
        print("Use at least 8 characters; nothing written.")
        return 1
    write_env(os.path.join(ROOT, ".env"), {"UI_USER": user, "UI_PASSWORD_HASH": make_hash(password)})
    print(f"Written UI_USER={user} and UI_PASSWORD_HASH to .env. Restart the UI; every device must sign in again.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

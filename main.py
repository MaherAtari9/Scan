#!/usr/bin/env python3
"""
Discord username hunter - triple and semi-triple names.

- No token needed: it uses Discord's public username availability endpoint,
  so your own account is never involved.
- Respects rate limits automatically (retry_after) and never re-checks a name.
- Saves hits to available.txt and progress to checked.txt, so you can stop
  the run and resume it later.
- Sends Discord webhook alerts when the run starts and when a name is found.

Usage:
    pip install requests
    python discord_hunter.py                 # all patterns
    python discord_hunter.py --mode 3        # triple only
    python discord_hunter.py --mode semi     # semi-triple only
    python discord_hunter.py --webhook URL   # send alerts to another webhook
    python discord_hunter.py --no-webhook    # turn alerts off
    python discord_hunter.py --delay 1.5     # seconds between requests
"""
import argparse
import itertools
import os
import random
import sys
import time

import requests

URL = "https://discord.com/api/v9/unique-username/username-attempt-unauthed"
DEFAULT_WEBHOOK = "https://discord.com/api/webhooks/1565601762692436001/LhYepWSG_Psogr-cL0UqArL_VNEWo48fAghLeNyMC3pJ-XsYSA237VScS65QAU1dtqhP"
LETTERS = "abcdefghijklmnopqrstuvwxyz"
DIGITS = "0123456789"
ALNUM = LETTERS + DIGITS
SYMBOLS = "._"
AVAILABLE_FILE, CHECKED_FILE = "available.txt", "checked.txt"


def valid(name: str) -> bool:
    """Discord rules: a-z, 0-9, _ and . only, no '..', length 2-32."""
    return (2 <= len(name) <= 32 and ".." not in name
            and all(c in ALNUM + SYMBOLS for c in name))


def gen_triple():
    """Every 3-character name: letters, digits and symbols."""
    for t in itertools.product(ALNUM + SYMBOLS, repeat=3):
        yield "".join(t)


def gen_semi():
    """Semi-triple: 4 characters built from the nice-looking patterns."""
    for a, b, c in itertools.product(LETTERS, repeat=3):
        yield a + b + c + a          # abca
        yield a + a + b + b          # aabb
        yield a + b + a + b          # abab
        yield a + b + b + a          # abba
        yield a + a + a + b          # aaab
        for s in SYMBOLS:
            yield a + s + b + c      # a.bc
            yield a + b + s + c      # ab.c
            yield a + b + c + s      # abc_
            yield s + a + b + c      # _abc
    for a, b, c in itertools.product(LETTERS, repeat=3):
        for d in DIGITS:
            yield a + b + c + d      # abc1
            yield d + a + b + c      # 1abc


def load(path):
    """Read one name per line into a set (empty set if the file is missing)."""
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def notify(webhook, text):
    """Send one message to the Discord webhook. Never crashes the run."""
    if not webhook:
        return
    try:
        r = requests.post(webhook, json={"content": text}, timeout=10)
        if r.status_code >= 300:
            print(f"  [webhook] Discord rejected the message (HTTP {r.status_code})")
    except requests.RequestException as exc:
        print(f"  [webhook] message not delivered: {exc}")


def check(session, name):
    """True = available, False = taken. Retries on rate limit and errors."""
    backoff = 2
    while True:
        try:
            r = session.post(URL, json={"username": name}, timeout=15)
        except requests.RequestException:
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
            continue
        if r.status_code == 200:
            return not r.json().get("taken", True)
        if r.status_code == 429:
            try:
                wait = float(r.json().get("retry_after", 5))
            except Exception:
                wait = float(r.headers.get("Retry-After", 5))
            print(f"  [rate limit] waiting {wait:.1f}s")
            time.sleep(wait + 0.5)
            continue
        if r.status_code == 400:      # name not allowed by Discord
            return False
        time.sleep(backoff)
        backoff = min(backoff * 2, 60)


def main():
    ap = argparse.ArgumentParser(description="Discord triple / semi-triple username hunter")
    ap.add_argument("--mode", choices=["3", "semi", "all"], default="all")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between requests")
    ap.add_argument("--webhook", default=DEFAULT_WEBHOOK,
                    help="Discord webhook used for alerts")
    ap.add_argument("--no-webhook", action="store_true",
                    help="disable webhook alerts")
    ap.add_argument("--shuffle", action="store_true", help="check in random order")
    args = ap.parse_args()

    webhook = None if args.no_webhook else args.webhook

    names = []
    if args.mode in ("3", "all"):
        names += list(gen_triple())
    if args.mode in ("semi", "all"):
        names += list(gen_semi())
    names = list(dict.fromkeys(n for n in names if valid(n)))   # drop duplicates
    if args.shuffle:
        random.shuffle(names)

    checked, found = load(CHECKED_FILE), load(AVAILABLE_FILE)
    todo = [n for n in names if n not in checked]
    print(f"Total {len(names)} | remaining {len(todo)} | already available {len(found)}")

    notify(webhook, "🟢 **Username hunter started**\n"
                    f"Mode: `{args.mode}` | names to check: `{len(todo)}` | "
                    f"already checked: `{len(checked)}` | already found: `{len(found)}`")

    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0",
                            "Content-Type": "application/json"})
    with open(CHECKED_FILE, "a", encoding="utf-8") as cf, \
         open(AVAILABLE_FILE, "a", encoding="utf-8") as af:
        for i, name in enumerate(todo, 1):
            ok = check(session, name)
            cf.write(name + "\n")
            cf.flush()
            if ok:
                print(f"\n[{i}/{len(todo)}] AVAILABLE: {name}")
                af.write(name + "\n")
                af.flush()
                notify(webhook, f"✅ **Username available: `{name}`**\n"
                                f"Go claim it now at Discord settings before someone else does.")
            else:
                print(f"[{i}/{len(todo)}] taken: {name}", end="\r")
            time.sleep(args.delay)

    print("\nCheck finished. Results are in", AVAILABLE_FILE)
    notify(webhook, f"🏁 **Username hunter finished** (mode `{args.mode}`) — "
                    f"results saved in `{AVAILABLE_FILE}`")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped - run it again and it resumes where it left off.")
        sys.exit(0)

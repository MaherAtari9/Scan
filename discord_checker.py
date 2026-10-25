"""
Discord 3-char username checker + auto-claimer
Install:  pip install requests rich
Run:      python discord_checker.py
"""
import itertools
import random
import string
import time
import getpass
from collections import deque

import requests
from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

API = "https://discord.com/api/v9"
CHARS = string.ascii_lowercase + string.digits + "_."
DELAY = 0.3          # seconds between checks (lower = faster, but more rate limits / ban risk)
LOG_ROWS = 14


def all_names():
    # Reads your own list from names.txt (one username per line, next to this script).
    try:
        with open("names.txt", encoding="utf-8") as f:
            names = [l.strip().lower() for l in f if l.strip()]
        names = list(dict.fromkeys(names))
        if names:
            return names
    except FileNotFoundError:
        with open("names.txt", "w", encoding="utf-8") as f:
            f.write("abc\nxyz\n")
        print("Created names.txt - put one username per line, then run again.")
        raise SystemExit
    print("names.txt is empty.")
    raise SystemExit


def build_ui(stats, log):
    head = Table.grid(padding=(0, 3))
    head.add_row(
        f"[bold cyan]Checked:[/] {stats['checked']}/{stats['total']}",
        f"[bold red]Taken:[/] {stats['taken']}",
        f"[bold green]Available:[/] {stats['free']}",
        f"[bold yellow]Status:[/] {stats['status']}",
    )
    table = Table(expand=True, border_style="grey37")
    table.add_column("#", width=6, style="dim")
    table.add_column("Username", style="bold white")
    table.add_column("Result")
    for i, (name, res) in enumerate(log, start=max(1, stats["checked"] - len(log) + 1)):
        table.add_row(str(i), name, res)
    return Group(
        Panel(head, title="[bold]Discord Username Checker[/]", border_style="cyan"),
        table,
    )


def main():
    import os
    token = (os.environ.get("DISCORD_TOKEN") or input("Token: ")).strip().strip('"').strip("'")
    password = (os.environ.get("DISCORD_PASSWORD") or getpass.getpass("Account password (needed to claim): ")).strip()

    if not token:
        print("No token entered.")
        return

    s = requests.Session()
    s.headers.update({
        "Authorization": token,
        "Content-Type": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
    })

    me = s.get(f"{API}/users/@me")
    if me.status_code != 200:
        print(f"Login failed (HTTP {me.status_code}): {me.text[:200]}")
        print(f"Token length received: {len(token)} (a user token is usually 70+ characters)")
        return
    print(f"Logged in as: {me.json().get('username')}\n")

    names = all_names()
    stats = {"checked": 0, "taken": 0, "free": 0, "total": len(names), "status": "Checking..."}
    log = deque(maxlen=LOG_ROWS)

    with Live(build_ui(stats, log), refresh_per_second=8) as live:
        i = 0
        while i < len(names):
            name = names[i]
            try:
                r = s.post(f"{API}/users/@me/pomelo-attempt", json={"username": name}, timeout=15)
            except requests.RequestException:
                stats["status"] = "Connection error, retrying"
                live.update(build_ui(stats, log))
                time.sleep(3)
                continue

            if r.status_code == 429:
                wait = float(r.json().get("retry_after", 5)) + 1
                stats["status"] = f"Rate limited, waiting {wait:.0f}s"
                live.update(build_ui(stats, log))
                time.sleep(wait)
                continue
            if r.status_code == 401:
                stats["status"] = "Token expired"
                live.update(build_ui(stats, log))
                return
            if r.status_code != 200:
                log.append((name, "[yellow]Invalid[/]"))
                i += 1
                stats["checked"] += 1
                live.update(build_ui(stats, log))
                time.sleep(DELAY)
                continue

            taken = r.json().get("taken", True)
            stats["checked"] += 1
            i += 1

            if taken:
                stats["taken"] += 1
                log.append((name, "[red]Taken[/]"))
            else:
                stats["free"] += 1
                log.append((name, "[bold green]Available! Claiming...[/]"))
                stats["status"] = f"Claiming {name}"
                live.update(build_ui(stats, log))
                c = s.patch(f"{API}/users/@me", json={"username": name, "password": password})
                if c.status_code == 200:
                    log.append((name, "[bold green on black]✔ Claimed on your account[/]"))
                    stats["status"] = f"Done - {name}"
                    live.update(build_ui(stats, log))
                    return
                log.append((name, f"[yellow]Claim failed ({c.status_code})[/]"))
                stats["status"] = "Continuing"

            live.update(build_ui(stats, log))
            time.sleep(DELAY)

    print("Finished checking all usernames.")


if __name__ == "__main__":
    main()

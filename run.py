#!/usr/bin/env python3
"""LinkedIn Automation — CLI (Windows / macOS / Linux)

  python run.py start                 # first time: guided setup (mode, login, keywords, test, schedule)

  python run.py login                 # connect / re-connect your LinkedIn account
  python run.py setup                 # change who you want to connect with
  python run.py run --dry-run         # test: check 3 profiles, send nothing
  python run.py run                   # today's run (respects the daily quota)
  python run.py stats                 # report
  python run.py schedule              # run automatically every day (time from config.yaml)
  python run.py unschedule
"""
import argparse
import getpass
import os
import plistlib
import re
import subprocess
import sys
from pathlib import Path

from bot.config import CFG, LOGS, MY_PROFILE_PATH, ROOT, log

TASK_NAME = "LinkedInAutomation"
PLIST_LABEL = "com.linkedin-automation.daily"
PLIST_PATH = Path.home() / "Library/LaunchAgents" / f"{PLIST_LABEL}.plist"
PY = r".venv\Scripts\python" if sys.platform == "win32" else ".venv/bin/python"


def ask(q: str, default: str = "") -> str:
    ans = input(f"{q}{f' [{default}]' if default else ''}: ").strip()
    return ans or default


def yes(q: str, default=True) -> bool:
    ans = ask(f"{q} ({'Y/n' if default else 'y/N'})").lower()
    return default if not ans else ans.startswith("y")


# ---------------- login ----------------

def check_login() -> bool:
    """Is LinkedIn logged in inside the bot's browser profile?"""
    from playwright.sync_api import sync_playwright
    from bot.linkedin import open_browser

    with sync_playwright() as pw:
        ctx, page = open_browser(pw)
        try:
            page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            return "/feed" in page.url
        finally:
            ctx.close()


def login_flow() -> bool:
    from bot.linkedin import open_plain_chrome

    if check_login():
        print("✅ LinkedIn is already connected.")
        return True

    proc = open_plain_chrome("https://www.linkedin.com/login")
    if proc:
        quit_how = "press Cmd + Q" if sys.platform == "darwin" else "close the window (X)"
        print("\n👉 A new Chrome window has opened (normal Chrome, no automation).")
        print("   1. Log in to your LinkedIn account there (including OTP / 2FA).")
        print("   2. When your LinkedIn feed (home page) appears, wait 10 seconds,")
        print(f"   3. then {quit_how} on that Chrome — the login is saved only then.")
        print("   Type your password only in the browser — this tool never sees or stores it.")
        print("   ⏳ Waiting for that Chrome to close…")
        proc.wait()
    else:
        # Google Chrome not installed — log in inside the Playwright browser instead
        from playwright.sync_api import sync_playwright
        from bot.linkedin import open_browser
        with sync_playwright() as pw:
            ctx, page = open_browser(pw)
            page.goto("https://www.linkedin.com/login")
            print("\n👉 Log in to LinkedIn in the browser window that just opened.")
            input("   When your feed appears, press Enter here… ")
            ctx.close()

    ok = check_login()
    print("✅ LinkedIn connected — session saved." if ok
          else f"⚠️  Could not confirm the login. Try again: {PY} run.py login")
    return ok


def cmd_login(_):
    login_flow()


def setup_keywords(page):
    """FREE mode: suggest keywords from your headline, you confirm or edit them."""
    from bot import linkedin as li
    from bot.ai import load_my_profile, save_my_profile
    from bot.rules import DEFAULT_EXCLUDE, build_profile, suggest_keywords

    li.goto(page, "https://www.linkedin.com/in/me/")
    info = li.top_card_info(page)
    old = load_my_profile()
    print(f"\n   You: {info['name']} — {info['headline']}")
    print("\n   Who do you want to connect with? What words appear in THEIR headline/profile?")
    print("   Separate with commas, e.g.:  founder, marketing manager, D2C, HR head")
    default = ", ".join(old.ideal_connections if old else suggest_keywords(info["headline"]))
    targets = split_list(ask("   Target keywords", default))
    excl = split_list(ask("   Skip people whose headline has", ", ".join(
        old.not_relevant if old else DEFAULT_EXCLUDE)))
    queries = split_list(ask("   What to type in LinkedIn search", ", ".join(
        old.search_queries if old else targets)))
    if not targets:
        sys.exit("At least one target keyword is needed.")
    me = build_profile(info["name"], info["headline"], targets, excl, queries or targets)
    save_my_profile(me)
    return me


def split_list(text: str) -> list[str]:
    return [x.strip() for x in text.split(",") if x.strip()]


def setup_niche(page, redo: bool):
    from bot.ai import load_my_profile
    from bot.daily import setup_my_profile

    me = load_my_profile()
    if me and not redo:
        return me
    if CFG["ai"].get("mode") == "claude":
        return setup_my_profile(page)
    return setup_keywords(page)


def cmd_setup(_):
    from playwright.sync_api import sync_playwright
    from bot import linkedin as li

    with sync_playwright() as pw:
        ctx, page = li.open_browser(pw)
        try:
            li.ensure_logged_in(page)
            setup_niche(page, redo=True)
        finally:
            ctx.close()
    print(f"✅ Saved: {MY_PROFILE_PATH}")


# ---------------- start wizard ----------------

def ensure_api_key():
    if os.environ.get("ANTHROPIC_API_KEY"):
        print("✅ Claude API key found.")
        return
    print("\nAI mode needs a Claude API key (to score profiles and write notes).")
    print("Create one here: https://platform.claude.com/settings/keys")
    print("(Or put it in the .env file as ANTHROPIC_API_KEY=... and run this again.)")
    key = getpass.getpass("Paste your API key (it stays hidden): ").strip()
    if not key:
        sys.exit("Cannot continue AI mode without an API key.")
    env = ROOT / ".env"
    lines = [l for l in (env.read_text().splitlines() if env.exists() else [])
             if not l.startswith("ANTHROPIC_API_KEY=")]
    lines.append(f"ANTHROPIC_API_KEY={key}")
    env.write_text("\n".join(lines) + "\n")
    os.environ["ANTHROPIC_API_KEY"] = key
    print("✅ Saved to .env")


def set_config_line(key: str, value: str):
    """Change one line in config.yaml (keeps all comments)."""
    path = ROOT / "config.yaml"
    text = re.sub(rf"(^\s*{key}:\s*)(\"[^\"]*\"|\S+)", rf"\g<1>{value}", path.read_text(), count=1, flags=re.M)
    path.write_text(text)


def set_schedule_time(hhmm: str):
    set_config_line("time", f'"{hhmm}"')
    CFG["schedule"]["time"] = hhmm


def cmd_start(_):
    from playwright.sync_api import sync_playwright
    from bot import linkedin as li
    from bot.ai import load_my_profile

    print("\n=== LinkedIn Automation — setup ===\n")
    print("Step 1/5 · Mode")
    print("   FREE mode : picks people by your keywords, notes from templates (no cost)")
    print("   AI mode   : Claude reads each profile and writes a personal note (paid, ~$1/day)")
    use_ai = yes("   Use AI mode?", default=CFG["ai"].get("mode") == "claude")
    mode = "claude" if use_ai else "rules"
    set_config_line("mode", mode)
    CFG["ai"]["mode"] = mode
    if use_ai:
        ensure_api_key()
    else:
        print("✅ FREE mode.")

    print("\nStep 2/5 · Connect LinkedIn")
    if not login_flow():
        sys.exit(f"Cannot continue without a LinkedIn login. Run again: {PY} run.py start")

    print("\nStep 3/5 · Who to connect with")
    with sync_playwright() as pw:
        ctx, page = li.open_browser(pw)
        try:
            redo = load_my_profile() is not None and yes("Change your previous settings?", default=False)
            me = setup_niche(page, redo=redo)
            print(f"\n   Your niche      : {me.my_niche}")
            print("   Connect with    : " + "\n                     ".join(me.ideal_connections))
            print(f"   Search keywords : {', '.join(me.search_queries)}")
            print(f"   (to change later: {PY} run.py setup)")
        finally:
            ctx.close()

    print("\nStep 4/5 · Test run (checks 3 profiles, sends NOTHING)")
    if yes("Run the test?"):
        from bot.daily import run_daily
        run_daily(dry_run=True, force=True, max_invites=3)

    print("\nStep 5/5 · Run automatically every day")
    if yes("Set up the daily schedule?"):
        t = ask("Daily start time (24h HH:MM)", CFG["schedule"]["time"])
        if re.fullmatch(r"\d{1,2}:\d{2}", t):
            set_schedule_time(t)
        cmd_schedule(None)

    print("\n🎉 All set! Useful commands:")
    print(f"   {PY} run.py stats          # report")
    print(f"   {PY} run.py run            # run today's batch now")
    print(f"   {PY} run.py unschedule     # stop the daily run\n")


# ---------------- run / stats ----------------

def cmd_run(args):
    from bot.daily import run_daily
    max_inv = args.max if args.max is not None else (3 if args.dry_run else None)
    run_daily(scheduled=args.scheduled, dry_run=args.dry_run, force=args.force or args.dry_run,
              max_invites=max_inv)


def cmd_stats(_):
    from bot.db import DB
    db = DB()
    counts = db.status_counts()
    total, acc = db.acceptance_stats(min_age_days=0)
    print("\n📊 Profiles by status")
    for k, v in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"   {k:<16} {v}")
    print(f"\n   Sent in last 7 days : {db.sent_in_last_days(7)} / {CFG['limits']['weekly_cap']}")
    if total:
        print(f"   Acceptance rate     : {acc}/{total} = {acc * 100 // total}%")
    if db.get("cooldown_until"):
        print(f"   Paused until        : {db.get('cooldown_until')}")
    print("\n🗓  Recent runs")
    for r in db.recent_runs():
        print(f"   {r['day']}  quota {r['quota']:>2}  sent {r['sent']:>2}  visited {r['visited']:>2}  {r['summary'] or ''}")
    print()


# ---------------- scheduling (per OS) ----------------

def _run_cmd() -> list[str]:
    return [sys.executable, str(ROOT / "run.py"), "run", "--scheduled"]


def cmd_schedule(_):
    hh, mm = map(int, CFG["schedule"]["time"].split(":"))
    if sys.platform == "darwin":
        plist = {
            "Label": PLIST_LABEL,
            "ProgramArguments": _run_cmd(),
            "WorkingDirectory": str(ROOT),
            "StartCalendarInterval": {"Hour": hh, "Minute": mm},
            "StandardOutPath": str(LOGS / "scheduler.out.log"),
            "StandardErrorPath": str(LOGS / "scheduler.err.log"),
        }
        PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["launchctl", "unload", str(PLIST_PATH)], capture_output=True)
        with open(PLIST_PATH, "wb") as f:
            plistlib.dump(plist, f)
        subprocess.run(["launchctl", "load", str(PLIST_PATH)], check=True)
    elif sys.platform == "win32":
        tr = subprocess.list2cmdline(_run_cmd())
        subprocess.run(["schtasks", "/Create", "/F", "/SC", "DAILY", "/TN", TASK_NAME,
                        "/TR", tr, "/ST", f"{hh:02d}:{mm:02d}"], check=True)
    else:
        line = f"{mm} {hh} * * * cd '{ROOT}' && {subprocess.list2cmdline(_run_cmd())} >> '{LOGS}/scheduler.log' 2>&1  # {TASK_NAME}"
        cur = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
        new = "\n".join(l for l in cur.splitlines() if TASK_NAME not in l) + "\n" + line + "\n"
        subprocess.run(["crontab", "-"], input=new.lstrip(), text=True, check=True)
    print(f"✅ Will run every day at {hh:02d}:{mm:02d} (+ a random 0-{CFG['schedule']['start_jitter_minutes']} min delay).")
    print("   Your computer must be on and you must be logged in to it at that time.")


def cmd_unschedule(_):
    if sys.platform == "darwin":
        subprocess.run(["launchctl", "unload", str(PLIST_PATH)], capture_output=True)
        PLIST_PATH.unlink(missing_ok=True)
    elif sys.platform == "win32":
        subprocess.run(["schtasks", "/Delete", "/F", "/TN", TASK_NAME], capture_output=True)
    else:
        cur = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
        new = "\n".join(l for l in cur.splitlines() if TASK_NAME not in l) + "\n"
        subprocess.run(["crontab", "-"], input=new.lstrip(), text=True)
    print("✅ Daily schedule removed.")


def main():
    ap = argparse.ArgumentParser(description="LinkedIn connection automation")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("start", help="first-time guided setup").set_defaults(fn=cmd_start)
    sub.add_parser("login", help="connect / re-connect LinkedIn").set_defaults(fn=cmd_login)
    sub.add_parser("setup", help="change who to connect with").set_defaults(fn=cmd_setup)
    r = sub.add_parser("run", help="run today's batch")
    r.add_argument("--dry-run", action="store_true", help="check profiles, send nothing")
    r.add_argument("--force", action="store_true", help="run again even if today's run is done")
    r.add_argument("--max", type=int, help="override today's invite quota")
    r.add_argument("--scheduled", action="store_true", help=argparse.SUPPRESS)
    r.set_defaults(fn=cmd_run)
    sub.add_parser("stats", help="show report").set_defaults(fn=cmd_stats)
    sub.add_parser("schedule", help="run automatically every day").set_defaults(fn=cmd_schedule)
    sub.add_parser("unschedule", help="stop the daily run").set_defaults(fn=cmd_unschedule)
    args = ap.parse_args()

    from bot.ai import AIError
    from bot.linkedin import NotLoggedIn, SafetyStop
    try:
        args.fn(args)
    except KeyboardInterrupt:
        log.info("Stopped (Ctrl+C)")
    except NotLoggedIn as e:
        print(f"\n🔑 {e}")
        sys.exit(1)
    except (AIError, SafetyStop) as e:
        print(f"\n❌ {e}\n   Fix it and run again: {PY} run.py {args.cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()

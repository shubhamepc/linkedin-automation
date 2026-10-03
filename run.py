#!/usr/bin/env python3
"""LinkedIn Automation — CLI (Windows / macOS / Linux)

  python run.py start                 # ⭐ pehli baar: sab kuch step-by-step (key, login, niche, test, schedule)

  python run.py login                 # LinkedIn login (browser khulega, aap khud login karoge)
  python run.py setup                 # aapki profile se niche/ICP dobara banao
  python run.py run --dry-run         # test: 3 profiles visit + score + note, kuch send nahi
  python run.py run                   # aaj ka run (quota ke hisaab se)
  python run.py stats                 # report
  python run.py schedule              # roz config.yaml ke time par auto-run
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


def ask(q: str, default: str = "") -> str:
    ans = input(f"{q}{f' [{default}]' if default else ''}: ").strip()
    return ans or default


def yes(q: str, default=True) -> bool:
    ans = ask(f"{q} ({'Y/n' if default else 'y/N'})").lower()
    return default if not ans else ans.startswith("y")


# ---------------- login ----------------

def check_login() -> bool:
    """Bot wale browser profile mein LinkedIn logged-in hai ya nahi."""
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
        print("✅ LinkedIn pehle se connected hai.")
        return True

    proc = open_plain_chrome("https://www.linkedin.com/login")
    if proc:
        quit_key = "Cmd + Q" if sys.platform == "darwin" else "window band (X)"
        print("\n👉 Ek nayi Chrome window khuli hai (normal Chrome, koi automation nahi).")
        print("   1. Usme apne LinkedIn account se login karo (OTP/2FA bhi).")
        print("   2. Feed (home page) dikh jaye to 10 second ruko,")
        print(f"   3. phir us Chrome ko {quit_key} se band karo — tabhi login save hota hai.")
        print("   Password sirf browser mein daalna — yeh tool use store nahi karta.")
        print("   ⏳ Chrome band hone ka wait kar rahe hain…")
        proc.wait()
    else:
        # Chrome installed nahi — Playwright window mein hi login
        from playwright.sync_api import sync_playwright
        from bot.linkedin import open_browser
        with sync_playwright() as pw:
            ctx, page = open_browser(pw)
            page.goto("https://www.linkedin.com/login")
            print("\n👉 Khuli hui browser window mein LinkedIn login karo.")
            input("   Feed dikhne lage to yahan Enter dabao… ")
            ctx.close()

    ok = check_login()
    print("✅ LinkedIn connect ho gaya, session save hai." if ok
          else "⚠️  Login confirm nahi hua — dobara try karo: python run.py login")
    return ok


def cmd_login(_):
    login_flow()


def setup_keywords(page):
    """Free mode: aapki headline se suggestions, aap confirm/edit karo."""
    from bot import linkedin as li
    from bot.ai import load_my_profile, save_my_profile
    from bot.rules import DEFAULT_EXCLUDE, build_profile, suggest_keywords

    li.goto(page, "https://www.linkedin.com/in/me/")
    info = li.top_card_info(page)
    old = load_my_profile()
    print(f"\n   Aap: {info['name']} — {info['headline']}")
    print("\n   Kin logon se connect karna hai? Unki headline/profile mein kya likha hota hai?")
    print("   Comma se alag likho, e.g.:  founder, marketing manager, D2C, HR head")
    default = ", ".join(old.ideal_connections if old else suggest_keywords(info["headline"]))
    targets = split_list(ask("   Target keywords", default))
    excl = split_list(ask("   Inhe skip karo", ", ".join(old.not_relevant if old else DEFAULT_EXCLUDE)))
    queries = split_list(ask("   LinkedIn search mein kya type karein", ", ".join(
        old.search_queries if old else targets)))
    if not targets:
        sys.exit("Kam se kam ek target keyword chahiye.")
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
        print("✅ Claude API key mili.")
        return
    print("\nClaude API key chahiye (profiles score karne aur notes likhne ke liye).")
    print("Yahan banao: https://platform.claude.com/settings/keys")
    key = getpass.getpass("API key paste karo (dikhegi nahi): ").strip()
    if not key:
        sys.exit("API key ke bina aage nahi badh sakte.")
    env = ROOT / ".env"
    lines = [l for l in (env.read_text().splitlines() if env.exists() else [])
             if not l.startswith("ANTHROPIC_API_KEY=")]
    lines.append(f"ANTHROPIC_API_KEY={key}")
    env.write_text("\n".join(lines) + "\n")
    os.environ["ANTHROPIC_API_KEY"] = key
    print("✅ .env mein save ho gaya.")


def set_config_line(key: str, value: str):
    """config.yaml mein ek line badlo (comments waise hi rehte hain)."""
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
    print("   FREE mode : aapke keywords se profiles chunega, template se note (koi kharcha nahi)")
    print("   AI mode   : Claude har profile padhkar personal note likhega (paid, ~$1/din)")
    use_ai = yes("   AI mode use karein?", default=CFG["ai"].get("mode") == "claude")
    mode = "claude" if use_ai else "rules"
    set_config_line("mode", mode)
    CFG["ai"]["mode"] = mode
    if use_ai:
        ensure_api_key()
    else:
        print("✅ FREE mode.")

    print("\nStep 2/5 · LinkedIn connect")
    if not login_flow():
        sys.exit("Login ke bina aage nahi badh sakte. Dobara: python run.py start")

    print("\nStep 3/5 · Kin logon se connect karna hai")
    with sync_playwright() as pw:
        ctx, page = li.open_browser(pw)
        try:
            redo = load_my_profile() is not None and yes("Pehle wali settings badalni hain?", default=False)
            me = setup_niche(page, redo=redo)
            print(f"\n   Aapka niche     : {me.my_niche}")
            print("   Kisse connect   : " + "\n                     ".join(me.ideal_connections))
            print(f"   Search keywords : {', '.join(me.search_queries)}")
            print(f"   (badalna ho to edit karo: {MY_PROFILE_PATH})")
        finally:
            ctx.close()

    print("\nStep 4/5 · Test run (3 profiles dekhega, kuch SEND nahi karega)")
    if yes("Test run karein?"):
        from bot.daily import run_daily
        run_daily(dry_run=True, force=True, max_invites=3)

    print("\nStep 5/5 · Roz automatic chalana")
    if yes("Daily schedule set karein?"):
        t = ask("Roz kis time start ho (24h HH:MM)", CFG["schedule"]["time"])
        if re.fullmatch(r"\d{1,2}:\d{2}", t):
            set_schedule_time(t)
        cmd_schedule(None)

    print("\n🎉 Ho gaya! Useful commands:")
    print("   python run.py stats          # report")
    print("   python run.py run            # abhi manually aaj ka run")
    print("   python run.py unschedule     # auto-run band\n")


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
    print(f"\n   Last 7 days sent : {db.sent_in_last_days(7)} / {CFG['limits']['weekly_cap']}")
    if total:
        print(f"   Acceptance rate  : {acc}/{total} = {acc * 100 // total}%")
    if db.get("cooldown_until"):
        print(f"   Cooldown until   : {db.get('cooldown_until')}")
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
    print(f"✅ Roz {hh:02d}:{mm:02d} (+0-{CFG['schedule']['start_jitter_minutes']} min random) par chalega.")
    print("   Us waqt computer on hona chahiye aur aap usme logged-in hone chahiye.")


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
    print("✅ Daily schedule hata diya.")


def main():
    ap = argparse.ArgumentParser(description="LinkedIn connection automation")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("start", help="pehli baar ka guided setup").set_defaults(fn=cmd_start)
    sub.add_parser("login").set_defaults(fn=cmd_login)
    sub.add_parser("setup").set_defaults(fn=cmd_setup)
    r = sub.add_parser("run")
    r.add_argument("--dry-run", action="store_true", help="visit + score, kuch send nahi")
    r.add_argument("--force", action="store_true", help="aaj dobara chalao")
    r.add_argument("--max", type=int, help="aaj ka quota manually set karo")
    r.add_argument("--scheduled", action="store_true", help=argparse.SUPPRESS)
    r.set_defaults(fn=cmd_run)
    sub.add_parser("stats").set_defaults(fn=cmd_stats)
    sub.add_parser("schedule").set_defaults(fn=cmd_schedule)
    sub.add_parser("unschedule").set_defaults(fn=cmd_unschedule)
    args = ap.parse_args()
    from bot.ai import AIError
    try:
        args.fn(args)
    except KeyboardInterrupt:
        log.info("Ruk gaya (Ctrl+C)")
    except AIError as e:
        print(f"\n❌ {e}\n   Theek karke dobara chalao: python run.py {args.cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()

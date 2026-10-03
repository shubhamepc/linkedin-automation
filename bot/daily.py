"""Roz ka run: accepted sync -> purane invites withdraw -> naye leads -> visit, score, connect."""
import random
import subprocess
import sys
import time
from datetime import date, datetime, timedelta

from playwright.sync_api import Error as PWError, sync_playwright

from . import linkedin as li
from .ai import AIError, analyze_my_profile, evaluate_profile, load_my_profile, save_my_profile
from .config import CFG, MY_PROFILE_PATH, log
from .db import DB, now
from .pacing import Pacer, daily_quota, sleep_range
from .rules import evaluate_rules


def notify(title: str, msg: str):
    """Desktop notification — macOS / Linux par; baaki jagah sirf log."""
    msg = msg.replace('"', "'")
    if sys.platform == "darwin":
        cmd = ["osascript", "-e", f'display notification "{msg}" with title "{title}"']
    elif sys.platform.startswith("linux"):
        cmd = ["notify-send", title, msg]
    else:
        return
    try:
        subprocess.run(cmd, check=False, capture_output=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


def setup_my_profile(page):
    log.info("Aapki profile padh rahe hain taaki niche samajh sakein…")
    text = li.read_my_profile(page)
    me = analyze_my_profile(text)
    save_my_profile(me)
    log.info("Niche: %s", me.my_niche)
    log.info("Ideal connections: %s", "; ".join(me.ideal_connections))
    log.info("Search queries: %s", ", ".join(me.search_queries))
    log.info("Saved -> %s (chaho to edit kar sakte ho)", MY_PROFILE_PATH)
    return me


def harvest(db: DB, page, me, want: int):
    """Candidate pool kam ho to LinkedIn search se naye profiles laao."""
    queries = list(CFG["search"].get("extra_queries") or []) + me.search_queries
    tries = 0
    while len(db.next_candidates(want)) < want and tries < 3:
        tries += 1
        qi = int(db.get("query_index", 0)) % len(queries)
        q = queries[qi]
        start = int(db.get(f"query_page:{q}", 1))
        if start > 10:  # yeh query khatam, aage badho
            db.set("query_index", qi + 1)
            continue
        pages = CFG["search"]["pages_per_harvest"]
        added = 0
        for p in range(start, start + pages):
            urls = li.search_people(page, q, p)
            added += db.add_candidates(urls, q)
            sleep_range(8, 25)
            if not urls:
                start = 99
                break
        db.set(f"query_page:{q}", start + pages if start != 99 else 99)
        db.set("query_index", qi + 1)
        log.info("Search '%s': %d naye profiles", q, added)


def housekeeping(db: DB, page, pacer_sleep=True):
    # 1) accepted invites sync
    try:
        n = db.mark_accepted(li.recent_connections(page))
        if n:
            log.info("✅ %d invites accept hue", n)
    except PWError as e:
        log.warning("Connections sync fail: %s", e)

    # 2) purane pending invites withdraw (zyada pending = red flag)
    lim = CFG["limits"]
    for url in db.stale_pending(lim["withdraw_after_days"], lim["max_withdraw_per_day"]):
        try:
            li.visit_profile(page, url)
            state = li.connection_state(page)
            if state == "connected":
                db.mark_accepted([url])
            elif state == "pending" and li.withdraw_invite(page):
                db.update_profile(url, status="withdrawn")
                log.info("↩️  withdrawn: %s", url)
            else:
                db.update_profile(url, status="withdrawn")
        except PWError as e:
            log.warning("Withdraw fail %s: %s", url, e)
        if pacer_sleep:
            sleep_range(20, 60)


def run_daily(scheduled=False, dry_run=False, force=False, max_invites=None):
    db = DB()
    today = date.today().isoformat()

    if db.ran_today(today) and not force:
        log.info("Aaj ka run ho chuka hai. (--force se dobara chala sakte ho)")
        return

    quota, why = daily_quota(db)
    if max_invites is not None:
        quota, why = max_invites, "manual --max"
    log.info("Aaj ka quota: %d (%s)%s", quota, why, "  [DRY RUN — kuch send nahi hoga]" if dry_run else "")
    if quota <= 0:
        rid = db.start_run(today, 0)
        db.finish_run(rid, 0, 0, why)
        return

    if scheduled:
        jitter = random.uniform(0, CFG["schedule"]["start_jitter_minutes"])
        log.info("Start se pehle %.0f min ruk rahe hain (natural timing)", jitter)
        time.sleep(jitter * 60)

    # dry run ko alag din ki tarah record karo, taaki aaj ka asli run skip na ho
    run_id = db.start_run(f"{today}-dry" if dry_run else today, quota)
    visited = sent = 0
    summary = ""
    lim = CFG["limits"]
    max_visits = min(lim["max_profile_visits"], int(quota * lim["visits_per_invite"]) + 5)
    if dry_run:
        max_visits = quota
    min_score = CFG["ai"]["min_score"]

    with sync_playwright() as pw:
        ctx, page = li.open_browser(pw)
        try:
            li.ensure_logged_in(page)
            use_ai = CFG["ai"].get("mode") == "claude"
            me = load_my_profile()
            if not me:
                if not use_ai:
                    raise li.NotLoggedIn("Pehle setup karo: python run.py start  (keywords set karne hain)")
                me = setup_my_profile(page)

            if not dry_run:
                housekeeping(db, page)

            harvest(db, page, me, want=max_visits)
            pacer = Pacer(fast=dry_run)

            for url in db.next_candidates(max_visits):
                if sent >= quota or visited >= max_visits:
                    break
                visited += 1
                log.info("[%d/%d sent | visit %d] %s", sent, quota, visited, url)
                try:
                    text = li.visit_profile(page, url)
                    if not text:
                        db.update_profile(url, status="error", visited_at=now(), reason="page not found")
                        continue
                    state = li.connection_state(page)
                    if state in ("pending", "connected", "unavailable"):
                        db.update_profile(url, status="not_connectable", visited_at=now(), reason=state)
                        log.info("   skip: %s", state)
                        pacer.between_profiles()
                        continue

                    if use_ai:
                        ev = evaluate_profile(me, text)
                    else:
                        ev = evaluate_rules(me, li.top_card_info(page), text)
                    fields = dict(name=ev.full_name, headline=ev.headline, niche=ev.their_niche,
                                  score=ev.relevance_score, reason=ev.reason, note=ev.connection_note,
                                  visited_at=now())
                    log.info("   %s — %s | score %d | %s", ev.full_name, ev.their_niche,
                             ev.relevance_score, ev.reason)

                    if ev.relevance_score < min_score:
                        db.update_profile(url, status="low_score", **fields)
                    elif dry_run:
                        log.info("   [dry run] note: %s", ev.connection_note)
                        db.update_profile(url, **fields)  # status 'new' hi rahega
                    else:
                        result = li.send_invite(page, ev.connection_note, via_more=(state == "connect_in_more"))
                        log.info("   → %s", result)
                        if result in ("sent", "sent_without_note"):
                            sent += 1
                            if result == "sent_without_note":
                                fields["note"] = None
                            db.update_profile(url, status="sent", sent_at=now(), **fields)
                        elif result == "limit":
                            db.update_profile(url, **fields)
                            raise li.SafetyStop("LinkedIn weekly invitation limit aa gaya", cooldown_days=4)
                        else:
                            db.update_profile(url, status="not_connectable", **{**fields, "reason": result})
                except AIError as e:
                    log.error("AI error: %s", e)
                    if "API key" in str(e):
                        raise
                except PWError as e:
                    log.warning("Page error (%s): %s", url, str(e).splitlines()[0])
                    db.update_profile(url, status="error", visited_at=now(), reason=str(e)[:200])
                if sent < quota:  # quota poora ho gaya to aakhri wait ki zaroorat nahi
                    pacer.between_profiles()

            summary = f"{sent} invites bheje, {visited} profiles dekhe"
            notify("LinkedIn Automation", summary)

        except li.SafetyStop as e:
            until = (datetime.now() + timedelta(days=e.cooldown_days)).isoformat(timespec="minutes")
            db.set("cooldown_until", until)
            summary = f"RUKA: {e} — {until} tak pause"
            log.error("🛑 %s", summary)
            notify("LinkedIn Automation — STOPPED", str(e))
        except li.NotLoggedIn as e:
            summary = str(e)
            log.error("🔑 %s", e)
            notify("LinkedIn Automation — login chahiye", str(e))
        except AIError as e:
            summary = f"AI error: {e}"
            notify("LinkedIn Automation — error", str(e))
        finally:
            db.finish_run(run_id, visited, sent, summary)
            log.info("Done: %s", summary)
            sleep_range(2, 4)
            ctx.close()

"""Daily run: sync accepted -> withdraw old invites -> find new people -> visit, score, connect."""
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

PY = r".venv\Scripts\python" if sys.platform == "win32" else ".venv/bin/python"


class BrowserClosed(Exception):
    pass


def notify(title: str, msg: str):
    """Desktop notification on macOS / Linux; elsewhere only the log."""
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
    """AI mode: Claude reads your own profile and works out who you should connect with."""
    log.info("Reading your profile to understand your niche…")
    text = li.read_my_profile(page)
    me = analyze_my_profile(text)
    save_my_profile(me)
    log.info("Niche: %s", me.my_niche)
    log.info("Ideal connections: %s", "; ".join(me.ideal_connections))
    log.info("Search queries: %s", ", ".join(me.search_queries))
    log.info("Saved -> %s (you can edit it)", MY_PROFILE_PATH)
    return me


def harvest(db: DB, page, me, want: int):
    """Top up the candidate pool from LinkedIn people search."""
    queries = list(CFG["search"].get("extra_queries") or []) + me.search_queries
    tries = 0
    while len(db.next_candidates(want)) < want and tries < 3:
        tries += 1
        qi = int(db.get("query_index", 0)) % len(queries)
        q = queries[qi]
        start = int(db.get(f"query_page:{q}", 1))
        if start > 10:  # this query is used up, move on
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
        log.info("Search '%s': %d new profiles", q, added)


def housekeeping(db: DB, page):
    # 1) mark accepted invites
    try:
        n = db.mark_accepted(li.recent_connections(page))
        if n:
            log.info("✅ %d invites accepted", n)
    except PWError as e:
        log.warning("Could not sync connections: %s", str(e).splitlines()[0])

    # 2) withdraw old pending invites (too many pending invites is a red flag)
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
            log.warning("Withdraw failed %s: %s", url, str(e).splitlines()[0])
        sleep_range(20, 60)


def run_daily(scheduled=False, dry_run=False, force=False, max_invites=None):
    db = DB()
    today = date.today().isoformat()

    if db.ran_today(today) and not force:
        log.info("Today's run is already done. (Use --force to run again.)")
        return

    quota, why = daily_quota(db)
    if max_invites is not None:
        quota, why = max_invites, "manual --max"
    elif not dry_run:
        already = db.sent_since(today)  # an earlier interrupted run today
        if already:
            quota, why = max(0, quota - already), f"{why}, {already} already sent today"
    log.info("Today's quota: %d (%s)%s", quota, why, "  [DRY RUN — nothing will be sent]" if dry_run else "")
    if quota <= 0:
        rid = db.start_run(today, 0)
        db.finish_run(rid, 0, 0, why)
        return

    if scheduled:
        jitter = random.uniform(0, CFG["schedule"]["start_jitter_minutes"])
        log.info("Waiting %.0f min before starting (natural timing)", jitter)
        time.sleep(jitter * 60)

    # a dry run is recorded separately so it never blocks today's real run
    run_id = db.start_run(f"{today}-dry" if dry_run else today, quota)
    visited = sent = 0
    summary = ""
    completed = False  # login / AI / browser problems don't count as "today's run is done"
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
                    raise li.NotLoggedIn(f"Finish setup first: {PY} run.py start")
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
                        db.update_profile(url, **fields)  # stays 'new'
                    else:
                        month = date.today().strftime("%Y-%m")
                        note = None if db.get("notes_exhausted_month") == month else ev.connection_note
                        result = li.send_invite(page, note, via_more=(state == "connect_in_more"))
                        log.info("   → %s", result)
                        if result in ("sent_notes_exhausted", "notes_exhausted"):
                            db.set("notes_exhausted_month", month)
                        if result in ("sent", "sent_without_note", "sent_notes_exhausted"):
                            sent += 1
                            if result != "sent":
                                fields["note"] = None
                            db.update_profile(url, status="sent", sent_at=now(), **fields)
                        elif result == "limit":
                            db.update_profile(url, **fields)
                            raise li.SafetyStop("LinkedIn weekly invitation limit reached", cooldown_days=4)
                        else:
                            db.update_profile(url, status="not_connectable", **{**fields, "reason": result})
                except AIError as e:
                    log.error("AI error: %s", e)
                    if "API key" in str(e) or "credits" in str(e):
                        raise
                except PWError as e:
                    if "has been closed" in str(e):
                        raise BrowserClosed() from e
                    log.warning("Page error (%s): %s", url, str(e).splitlines()[0])
                    db.update_profile(url, status="error", visited_at=now(), reason=str(e)[:200])
                if sent < quota:  # no need to wait after the last invite
                    pacer.between_profiles()

            summary = f"sent {sent} invites, checked {visited} profiles"
            completed = True
            notify("LinkedIn Automation", summary)

        except li.SafetyStop as e:
            until = (datetime.now() + timedelta(days=e.cooldown_days)).isoformat(timespec="minutes")
            db.set("cooldown_until", until)
            summary = f"STOPPED: {e} — paused until {until}"
            completed = True
            log.error("🛑 %s", summary)
            notify("LinkedIn Automation — STOPPED", str(e))
        except li.NotLoggedIn as e:
            summary = str(e)
            log.error("🔑 %s", e)
            notify("LinkedIn Automation — action needed", str(e))
        except AIError as e:
            summary = f"AI error: {e}"
            log.error("❌ %s", summary)
            notify("LinkedIn Automation — error", str(e))
        except BrowserClosed:
            summary = (f"browser window was closed — stopped after {sent} invites. "
                       "Don't close the bot's Chrome window while it runs.")
            log.error("🛑 %s", summary)
        finally:
            db.finish_run(run_id, visited, sent, summary, completed=completed)
            log.info("Done: %s", summary)
            try:
                sleep_range(2, 4)
                ctx.close()
            except PWError:
                pass

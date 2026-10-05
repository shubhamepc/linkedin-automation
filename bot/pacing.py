"""How many invites per day, and human-like pacing between actions."""
import random
import time
from datetime import date, datetime

from .config import CFG, log

DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def sleep_range(lo: float, hi: float):
    time.sleep(random.uniform(lo, hi))


def human_scroll(page, steps=None):
    """Scroll like someone reading — mostly down, sometimes a little back up."""
    for _ in range(steps or random.randint(3, 6)):
        page.mouse.wheel(0, random.randint(250, 700))
        sleep_range(0.8, 3.0)
        if random.random() < 0.2:
            page.mouse.wheel(0, -random.randint(100, 300))
            sleep_range(0.5, 1.5)


def daily_quota(db, today: date | None = None) -> tuple[int, str]:
    """Today's invite quota and the reason for it."""
    today = today or date.today()
    lim = CFG["limits"]
    day = DAY_NAMES[today.weekday()]

    if day not in CFG["schedule"]["active_days"]:
        return 0, f"{day} is an off day"

    cooldown = db.get("cooldown_until")
    if cooldown and datetime.fromisoformat(cooldown) > datetime.now():
        return 0, f"paused until {cooldown} (after a LinkedIn warning/limit)"

    if random.random() < lim["skip_day_chance"]:
        return 0, "random rest day"

    first = db.first_sent_at()
    week_no = 0 if not first else (datetime.now() - datetime.fromisoformat(first)).days // 7
    if week_no < len(lim["warmup"]):
        lo, hi = lim["warmup"][week_no]
        why = f"warm-up week {week_no + 1}"
    else:
        lo, hi = lim["normal"]
        why = "normal"
    if day == "sat":
        lo, hi = min(lo, lim["saturday"][0]), min(hi, lim["saturday"][1])
        why += ", saturday light"

    quota = random.randint(lo, hi)

    total, acc = db.acceptance_stats()
    if total >= 40 and acc / total < lim["min_acceptance_rate"]:
        quota //= 2
        why += f", low acceptance ({acc}/{total}) so halved"

    room = lim["weekly_cap"] - db.sent_in_last_days(7)
    if room < quota:
        quota = max(0, room)
        why += f", near weekly cap ({lim['weekly_cap']})"

    return quota, why


class Pacer:
    """Gaps between profiles, with an occasional longer break."""

    def __init__(self, fast=False):
        p = dict(CFG["pacing"])
        if fast:  # test run: short gaps
            p.update(between_profiles_sec=[5, 12], break_every=[999, 999])
        self.p = p
        self.count = 0
        self.next_break = random.randint(*p["break_every"])

    def between_profiles(self):
        self.count += 1
        if self.count >= self.next_break:
            mins = random.uniform(*self.p["break_minutes"])
            log.info("☕ break: %.1f min", mins)
            time.sleep(mins * 60)
            self.count = 0
            self.next_break = random.randint(*self.p["break_every"])
        else:
            secs = random.uniform(*self.p["between_profiles_sec"])
            log.info("…%.0fs wait", secs)
            time.sleep(secs)

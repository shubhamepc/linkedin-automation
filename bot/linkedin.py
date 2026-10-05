"""LinkedIn page actions. Selectors target the English UI — keep your LinkedIn language set to English."""
import os
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from playwright.sync_api import Error as PWError, Page, TimeoutError as PWTimeout

from .config import BROWSER_PROFILE, CFG, log
from .pacing import human_scroll, sleep_range

BASE = "https://www.linkedin.com"


class SafetyStop(Exception):
    """LinkedIn showed a checkpoint / warning / limit — stop for today."""

    def __init__(self, msg, cooldown_days=2):
        super().__init__(msg)
        self.cooldown_days = cooldown_days


class NotLoggedIn(Exception):
    pass


def open_browser(pw):
    opts = dict(headless=CFG["browser"].get("headless", False), no_viewport=True)
    channel = CFG["browser"].get("channel") or None
    try:
        ctx = pw.chromium.launch_persistent_context(str(BROWSER_PROFILE), channel=channel, **opts)
    except PWError:
        if not channel:
            raise
        # Google Chrome not installed — use Playwright's Chromium
        log.info("Google Chrome not found, using built-in Chromium")
        ctx = pw.chromium.launch_persistent_context(str(BROWSER_PROFILE), **opts)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.set_default_timeout(15000)
    return ctx, page


def find_chrome() -> str | None:
    """Path of the installed Google Chrome (used to open a normal window for login)."""
    candidates = {
        "darwin": ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                   str(Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome")],
        "win32": [os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
                  os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
                  os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe")],
    }.get(sys.platform, [])
    for path in candidates:
        if Path(path).exists():
            return path
    return shutil.which("google-chrome") or shutil.which("google-chrome-stable")


def open_plain_chrome(url: str) -> subprocess.Popen | None:
    """A normal Chrome window without automation, using the same profile folder as the bot.
    Logging in here looks to LinkedIn like any regular browser."""
    chrome = find_chrome()
    if not chrome:
        return None
    BROWSER_PROFILE.mkdir(parents=True, exist_ok=True)
    args = [chrome, f"--user-data-dir={BROWSER_PROFILE}", "--no-first-run",
            "--no-default-browser-check", "--new-window"]
    # Encrypt cookies the way Playwright reads them, otherwise the bot won't see the login
    if sys.platform == "darwin":
        args.append("--use-mock-keychain")
    elif sys.platform.startswith("linux"):
        args.append("--password-store=basic")
    return subprocess.Popen(args + [url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ---------- helpers ----------

def normalize_profile_url(href: str | None) -> str | None:
    if not href:
        return None
    path = urlparse(href if href.startswith("http") else BASE + href).path
    m = re.match(r"^/in/([^/?#]+)", path)
    if not m:
        return None
    slug = unquote(m.group(1)).lower()
    if slug in ("me",) or slug.startswith("acoa"):  # ACoA... = hidden "LinkedIn Member" ids
        return None
    return f"{BASE}/in/{quote(slug)}/"


SAFETY_URL_MARKERS = ("/checkpoint/", "/authwall", "/challenge", "/uas/login")
SAFETY_TEXT = re.compile(
    r"unusual activity|security verification|let's do a quick security check|"
    r"account (has been )?restricted|temporarily restricted", re.I)
LIMIT_TEXT = re.compile(r"weekly invitation limit|reached the (weekly )?limit|"
                        r"too many (pending )?invitations", re.I)


def check_safety(page: Page):
    url = page.url
    if any(m in url for m in SAFETY_URL_MARKERS):
        if "/uas/login" in url or "/login" in url:
            raise NotLoggedIn("LinkedIn is not logged in (or the login expired) — run: python run.py login")
        raise SafetyStop(f"LinkedIn security check page: {url}", cooldown_days=3)
    try:
        body = page.locator("body").inner_text(timeout=5000)[:20000]
    except PWTimeout:
        return
    if SAFETY_TEXT.search(body):
        raise SafetyStop("LinkedIn ne unusual activity / security warning dikhaya", cooldown_days=3)


def goto(page: Page, url: str):
    page.goto(url, wait_until="domcontentloaded")
    sleep_range(2.5, 5)
    check_safety(page)


def ensure_logged_in(page: Page):
    goto(page, f"{BASE}/feed/")
    if "/feed" not in page.url:
        raise NotLoggedIn("LinkedIn is not logged in — run: python run.py login")


# ---------- my profile ----------

def read_my_profile(page: Page) -> str:
    goto(page, f"{BASE}/in/me/")
    human_scroll(page, steps=5)
    return page.locator("main").inner_text()[:12000]


# ---------- search ----------

def search_people(page: Page, query: str, page_no: int) -> list[str]:
    network = quote(str(CFG["search"]["network"]).replace("'", '"'))
    url = f"{BASE}/search/results/people/?keywords={quote(query)}&network={network}&page={page_no}"
    goto(page, url)
    human_scroll(page, steps=random.randint(2, 4))
    urls = []
    for a in page.locator("main a[href*='/in/']").all():
        u = normalize_profile_url(a.get_attribute("href"))
        if u and u not in urls:
            urls.append(u)
    return urls


# ---------- profile ----------

CONNECT_SEL = ('button[aria-label*="to connect"], a[aria-label*="to connect"], '
               'a[href*="/custom-invite/"]')
PENDING_SEL = 'button[aria-label*="Pending"], a[aria-label*="Pending"], button:has-text("Pending")'
MORE_SEL = 'button[aria-label="More actions"], button[aria-label="More"]'


def profile_name(page: Page) -> str:
    """Name from the page title 'Name | LinkedIn' (h1/h2 change often, the title does not)."""
    name = page.title().split("|")[0].strip()
    return re.sub(r"^\(\d+\)\s*", "", name)  # "(3) Name" = notification count


def _top_card(page: Page):
    """Profile top card: the innermost section whose heading is this person's name."""
    name = profile_name(page)
    for tag in ("h1", "h2"):
        heading = page.locator(tag, has_text=name) if name else page.locator(tag)
        card = page.locator("main section").filter(has=heading)
        if card.count():
            return card.last
    return page.locator("main section").first


def _connect_sel(page: Page) -> str:
    """Only THIS person's Connect button — never someone from 'People you may know'."""
    name = profile_name(page).replace('"', '\\"')
    if name:
        return (f'[aria-label="Invite {name} to connect"], '
                f'a[href*="/custom-invite/"][aria-label*="{name}"]')
    return CONNECT_SEL


def visit_profile(page: Page, url: str) -> str:
    goto(page, url)
    if "/in/" not in page.url or page.locator("text=This page doesn’t exist").count():
        return ""
    human_scroll(page)
    page.mouse.wheel(0, -5000)  # wapas top par (buttons wahin hain)
    sleep_range(1, 2.5)
    return page.locator("main").inner_text()[:8000]


SKIP_LINE = re.compile(r"^(·\s*)?(1st|2nd|3rd\+?)\b|degree connection|^(he|she|they)/|^verified|"
                       r"^contact info|followers|connections$", re.I)


def top_card_info(page: Page) -> dict:
    """Name, headline and current company from the profile top card."""
    top = _top_card(page)
    name = profile_name(page)

    lines = [l.strip() for l in top.inner_text().splitlines() if l.strip()]
    start = lines.index(name) + 1 if name in lines else 0
    headline = next((l for l in lines[start:] if len(l) > 3 and not SKIP_LINE.search(l)), "")

    company = ""
    btn = top.locator('[aria-label^="Current company"]')
    if btn.count():
        label = btn.first.get_attribute("aria-label") or ""
        company = re.sub(r"^Current company:\s*", "", label).split(". ")[0].strip(" .")
    if not company and "Contact info" in lines:
        # Top card: "... / Contact info / <current company> / <college> / 52 / connections"
        nxt = lines[lines.index("Contact info") + 1:][:1]
        if nxt and not re.search(r"^\d|connections|followers|mutual", nxt[0], re.I):
            company = nxt[0]
    if not company:
        m = re.search(r"(?:\bat\b|@)\s*([A-Z0-9][\w&.\- ]{1,40}?)(?:\s*[|•·,]|$)", headline)
        company = m.group(1).strip() if m else ""
    return {"name": name, "headline": headline, "company": company}


def connection_state(page: Page) -> str:
    """connect | connect_in_more | pending | connected | unavailable"""
    top = _top_card(page)
    if top.locator(PENDING_SEL).filter(visible=True).count():
        return "pending"
    if top.locator(_connect_sel(page)).filter(visible=True).count():
        return "connect"
    if re.search(r"·\s*1st\b", top.inner_text()):
        return "connected"
    more = top.locator(MORE_SEL).filter(visible=True)
    if more.count():
        more.first.click()
        sleep_range(0.8, 1.6)
        try:  # the menu animates open — give it a moment
            page.locator(_connect_sel(page)).filter(visible=True).first.wait_for(timeout=3000)
            found = True
        except PWTimeout:
            found = False
        page.keyboard.press("Escape")
        sleep_range(0.5, 1)
        if found:
            return "connect_in_more"
    return "unavailable"


def _dialog(page: Page):
    return page.locator('[role="dialog"]').filter(visible=True).last


def _close_dialog(page: Page):
    page.keyboard.press("Escape")
    sleep_range(0.5, 1)


NOTES_EXHAUSTED_TEXT = re.compile(r"out of free custom notes|personalized invites with premium", re.I)


def _open_connect_dialog(page: Page, via_more: bool):
    top = _top_card(page)
    if via_more:
        top.locator(MORE_SEL).filter(visible=True).first.click()
        sleep_range(0.8, 1.6)
        page.locator(_connect_sel(page)).filter(visible=True).first.click()
    else:
        top.locator(_connect_sel(page)).filter(visible=True).first.click()
    sleep_range(1.5, 3)
    try:
        dlg = _dialog(page)
        dlg.wait_for(state="visible", timeout=8000)
        return dlg
    except PWTimeout:
        return None


def send_invite(page: Page, note: str | None, via_more: bool) -> str:
    """Returns: sent | sent_without_note | sent_notes_exhausted | notes_exhausted |
    email_required | limit | failed"""
    dlg = _open_connect_dialog(page, via_more)
    if dlg is None:
        log.warning("Connect dialog did not open")
        return "failed"

    text = dlg.inner_text()
    if LIMIT_TEXT.search(text):
        _close_dialog(page)
        return "limit"
    if dlg.locator('input[type="email"], #email').count() or re.search(r"email address", text, re.I):
        _close_dialog(page)
        return "email_required"

    note_added = notes_exhausted = False
    if note:
        add = dlg.get_by_role("button", name=re.compile(r"add a (free )?note", re.I))
        if add.count():
            add.first.click()
            sleep_range(1, 2)
        if NOTES_EXHAUSTED_TEXT.search(_dialog(page).inner_text()):
            # Free account used up this month's custom notes — close the Premium offer, send without a note
            log.info("   LinkedIn free notes used up for this month (no Premium)")
            notes_exhausted = True
            _close_dialog(page)
            if not CFG["ai"].get("send_without_note_if_note_fails", True):
                return "notes_exhausted"
            page.reload(wait_until="domcontentloaded")  # the layout changes after the popup
            sleep_range(3, 5)
            dlg = _open_connect_dialog(page, via_more)
            if dlg is None:
                return "failed"
        else:
            box = _dialog(page).locator("textarea").first
            if box.count():
                box.click()
                sleep_range(0.5, 1.2)
                box.press_sequentially(note, delay=random.randint(35, 90))
                sleep_range(1.5, 4)
                note_added = True
            elif not CFG["ai"].get("send_without_note_if_note_fails", True):
                _close_dialog(page)
                return "failed"

    dlg = _dialog(page)
    send = dlg.get_by_role("button", name=re.compile(r"^send( invitation| now)?$", re.I))
    if not send.count():
        send = dlg.get_by_role("button", name=re.compile(r"send without a note", re.I))
    if not send.count():
        log.warning("Send button not found")
        _close_dialog(page)
        return "failed"
    send.first.click()
    sleep_range(2.5, 4.5)

    if LIMIT_TEXT.search(page.locator("body").inner_text()[:20000]):
        _close_dialog(page)
        return "limit"
    if _dialog(page).count():
        # dialog still open — something got stuck
        _close_dialog(page)
        return "failed"
    if note_added:
        return "sent"
    return "sent_notes_exhausted" if notes_exhausted else "sent_without_note"


def withdraw_invite(page: Page) -> bool:
    pending = _top_card(page).locator(PENDING_SEL).filter(visible=True)
    if not pending.count():
        return False
    pending.first.click()
    sleep_range(1, 2)
    try:
        btn = _dialog(page).get_by_role("button", name=re.compile(r"^withdraw$", re.I))
        btn.first.click(timeout=6000)
    except PWTimeout:
        _close_dialog(page)
        return False
    sleep_range(2, 3.5)
    return True


def recent_connections(page: Page) -> set[str]:
    goto(page, f"{BASE}/mynetwork/invite-connect/connections/")
    human_scroll(page, steps=4)
    out = set()
    for a in page.locator("main a[href*='/in/']").all():
        u = normalize_profile_url(a.get_attribute("href"))
        if u:
            out.add(u)
    return out

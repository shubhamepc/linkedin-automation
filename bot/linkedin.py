"""LinkedIn page actions. Selectors English UI ke liye hain — LinkedIn language English rakhein."""
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
    """LinkedIn ne checkpoint / warning / limit dikhaya — aaj ke liye ruk jao."""

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
        # Google Chrome installed nahi hai — Playwright ka Chromium use karo
        log.info("Chrome nahi mila, built-in Chromium use kar rahe hain")
        ctx = pw.chromium.launch_persistent_context(str(BROWSER_PROFILE), **opts)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.set_default_timeout(15000)
    return ctx, page


def find_chrome() -> str | None:
    """Installed Google Chrome ka path (login ke liye normal window kholne ke kaam aata hai)."""
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
    """Bina automation ke normal Chrome window — usi profile folder ke saath jo bot use karta hai.
    Login yahan karne se LinkedIn ko bilkul normal browser dikhta hai."""
    chrome = find_chrome()
    if not chrome:
        return None
    BROWSER_PROFILE.mkdir(parents=True, exist_ok=True)
    args = [chrome, f"--user-data-dir={BROWSER_PROFILE}", "--no-first-run",
            "--no-default-browser-check", "--new-window"]
    # Cookies usi tarah encrypt hon jaise Playwright padhta hai, warna bot ko login nahi dikhega
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
            raise NotLoggedIn("LinkedIn login expire ho gaya — `python run.py login` chalao")
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
        raise NotLoggedIn("LinkedIn par login nahi hai — `python run.py login` chalao")


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
    """Page title 'Naam | LinkedIn' se naam (h1/h2 badalte rehte hain, title nahi)."""
    name = page.title().split("|")[0].strip()
    return re.sub(r"^\(\d+\)\s*", "", name)  # "(3) Naam" = notification count


def _top_card(page: Page):
    """Profile ka top card: woh (sabse andar wala) section jiski heading mein us insaan ka naam hai."""
    name = profile_name(page)
    for tag in ("h1", "h2"):
        heading = page.locator(tag, has_text=name) if name else page.locator(tag)
        card = page.locator("main section").filter(has=heading)
        if card.count():
            return card.last
    return page.locator("main section").first


def _connect_sel(page: Page) -> str:
    """Sirf ISI insaan ka Connect button — 'People you may know' wale kisi aur ka nahi."""
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
    """Naam, headline, current company — profile ke top card se."""
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
        found = page.locator(_connect_sel(page)).filter(visible=True).count() > 0
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


def send_invite(page: Page, note: str | None, via_more: bool) -> str:
    """Returns: sent | sent_without_note | email_required | limit | failed"""
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
    except PWTimeout:
        log.warning("Connect dialog nahi khula")
        return "failed"

    text = dlg.inner_text()
    if LIMIT_TEXT.search(text):
        _close_dialog(page)
        return "limit"
    if dlg.locator('input[type="email"], #email').count() or re.search(r"email address", text, re.I):
        _close_dialog(page)
        return "email_required"

    note_added = False
    if note:
        add = dlg.get_by_role("button", name=re.compile(r"add a (free )?note", re.I))
        if add.count():
            add.first.click()
            sleep_range(1, 2)
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
        log.warning("Send button nahi mila")
        _close_dialog(page)
        return "failed"
    send.first.click()
    sleep_range(2.5, 4.5)

    if LIMIT_TEXT.search(page.locator("body").inner_text()[:20000]):
        _close_dialog(page)
        return "limit"
    if _dialog(page).count():
        # dialog abhi bhi khula hai — kuch atka
        _close_dialog(page)
        return "failed"
    return "sent" if note_added else "sent_without_note"


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

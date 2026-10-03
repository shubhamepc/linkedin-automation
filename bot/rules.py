"""Free mode (bina AI): keywords se score, templates se note."""
import random
import re

from .ai import Evaluation, MyProfile, fit_note
from .config import CFG

DEFAULT_EXCLUDE = ["student", "intern", "open to work", "seeking opportunities", "looking for job"]


def _has(keyword: str, text: str) -> bool:
    kw = keyword.strip().lower()
    return bool(kw) and re.search(r"(?<!\w)" + re.escape(kw) + r"(?!\w)", text) is not None


def suggest_keywords(headline: str) -> list[str]:
    """Headline ke tukdon se keyword suggestions, e.g. 'Founder @ X | D2C Growth' -> ['Founder', 'D2C Growth']."""
    parts = re.split(r"\s*(?:[|•·,/]| at | @ |@)\s*", headline or "")
    out = []
    for p in parts:
        p = p.strip(" -–")
        if p and 1 <= len(p.split()) <= 4 and p.lower() not in (o.lower() for o in out):
            out.append(p)
    return out[:5]


def build_profile(name: str, headline: str, targets, exclude, queries) -> MyProfile:
    return MyProfile(
        my_name=name, my_summary=headline, my_niche=headline, what_i_offer="",
        ideal_connections=targets, not_relevant=exclude, search_queries=queries,
        note_style="templates (free mode)",
    )


def evaluate_rules(me: MyProfile, info: dict, text: str) -> Evaluation:
    head = (info.get("headline") or "").lower()
    body = text.lower()
    full_name = info.get("name") or ""
    first = full_name.split()[0] if full_name else ""

    excluded = [k for k in me.not_relevant if _has(k, head)]
    head_hits = [k for k in me.ideal_connections if _has(k, head)]
    body_hits = [k for k in me.ideal_connections if k not in head_hits and _has(k, body)]

    if excluded:
        score, reason = 0, f"skip keyword: {', '.join(excluded)}"
    elif head_hits:
        score = min(100, 75 + 10 * (len(head_hits) - 1) + 5 * len(body_hits))
        reason = f"headline mein: {', '.join(head_hits)}"
    elif body_hits:
        score = min(80, 45 + 10 * len(body_hits))  # body mein match kam bharosemand
        reason = f"profile mein: {', '.join(body_hits)}"
    else:
        score, reason = 0, "koi keyword match nahi"

    topic = (head_hits or body_hits or ["your field"])[0]
    return Evaluation(
        first_name=first, full_name=full_name, headline=info.get("headline") or "",
        their_niche=topic, relevance_score=score, reason=reason,
        connection_note=make_note(me, first, info.get("company") or "", topic),
    )


def make_note(me: MyProfile, first_name: str, company: str, topic: str) -> str:
    r = CFG["rules"]
    pool = r["note_templates"] if company else r["note_templates_no_company"]
    values = {
        "first_name": first_name or "there",
        "company": company,
        "topic": topic,
        "my_name": (me.my_name.split() or [""])[0],
    }
    note = random.choice(pool).format_map(values)
    return fit_note(note, CFG["ai"]["note_max_chars"])

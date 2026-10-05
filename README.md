# LinkedIn Automation 🤝

Roz automatic: LinkedIn par aapke niche ke **relevant** logon ko dhundhta hai, unki profile visit karta hai,
AI se check karta hai ki woh aapke kaam ke hain ya nahi, aur **personalized note** ke saath connection request bhejta hai —
utni hi jitni ek normal insaan bhejta (organic limits).

Koi bhi apne LinkedIn account se use kar sakta hai. Sab kuch command prompt / terminal se.

| Mode | Kaise chunta hai | Note | Kharcha |
|---|---|---|---|
| **FREE** (default) | Aapke keywords profile ki headline/about mein match hon | Templates — naam + company khud bhar jaate hain | ₹0 |
| **AI** (optional) | Claude har profile padhkar 0-100 score deta hai | Har insaan ke liye alag personal note | ~$1/din (Claude API) |

---

## ⚡ Quick start

**Chahiye:** Python 3.10+, Google Chrome (recommended), LinkedIn account. **Premium** = har invite mein note; **free account** = mahine ke kuch free notes, uske baad bot apne aap bina note ke invite bhejta hai. AI mode ke liye [Claude API key](https://platform.claude.com/settings/keys) + credits.

### Windows
1. [ZIP download karo](https://github.com/shubhamepc/linkedin-automation/archive/refs/heads/main.zip) aur unzip karo
2. `setup.bat` par double-click karo

### macOS / Linux
```bash
git clone https://github.com/shubhamepc/linkedin-automation.git
cd linkedin-automation
chmod +x setup.sh && ./setup.sh
```

Setup ke baad `start` wizard khud chalega. Yeh 5 steps karata hai:

| Step | Kya hota hai |
|---|---|
| 1. Mode | FREE ya AI. AI chuna to Claude key poochta hai (`.env` mein save) |
| 2. LinkedIn connect | Normal Chrome window khulti hai — **aap khud login karte ho**, phir Cmd+Q / window band. Password tool kabhi nahi dekhta |
| 3. Kisse connect | FREE: aapki headline se keywords suggest, aap edit/confirm karo. AI: Claude aapki profile padhkar khud decide karta hai |
| 4. Test run | 3 profiles visit + score + note dikhata hai — **kuch send nahi** |
| 5. Schedule | Roz kis time chalana hai (Windows Task Scheduler / macOS launchd / Linux cron) |

---

## 🧠 Kaise kaam karta hai

```
Aapki profile ──AI──▶ niche + ideal connections + search keywords   (ek baar)

Roz:
 1. Accepted invites sync + 3 hafte purane pending invites withdraw
 2. LinkedIn search (2nd-degree) se naye profiles
 3. Har profile: visit → padhna (scroll) → AI score 0-100 + uska niche
 4. Score ≥ 70  →  Connect + personalized note (≤ 280 chars)
 5. Random gaps (40-140s) + beech mein breaks → report + notification
```

## 🛡️ Organic limits (account safety)

| | Default |
|---|---|
| Week 1 / Week 2 (warm-up) | 5-8 / 8-14 per day |
| Uske baad | 12-22 weekdays, 3-7 Saturday, Sunday off |
| Weekly cap | 80 (LinkedIn ~100 allow karta hai) |
| Start time | Roz alag (schedule + 0-75 min random) |
| Kabhi-kabhi | Poora din rest |
| Acceptance < 20% | Volume apne aap aadha |
| CAPTCHA / warning / limit | **Turant stop** + 3-4 din cooldown + notification |

Sab `config.yaml` mein badal sakte ho.

## 🔧 Commands

> Windows: `.venv\Scripts\python run.py ...`  · macOS/Linux: `.venv/bin/python run.py ...`

| Command | Kaam |
|---|---|
| `run.py start` | Guided setup (kabhi bhi dobara chala sakte ho) |
| `run.py run --dry-run` | Test: 3 profiles, kuch send nahi |
| `run.py run` | Abhi aaj ka run |
| `run.py run --max 5` | Aaj sirf 5 |
| `run.py stats` | Report: sent, accepted, acceptance rate |
| `run.py setup` | Niche dobara detect karo |
| `run.py login` | LinkedIn session expire ho jaye to |
| `run.py schedule` / `unschedule` | Daily auto-run on / off |

**Keywords / niche badalne:** `run.py setup` ya `data/my_profile.json` edit karo.
**Note templates (FREE mode):** `config.yaml` → `rules.note_templates`.
**AI mode on/off:** `config.yaml` → `ai.mode: claude` / `rules` (ya `run.py start` dobara).
**Apne keywords add karne:** `config.yaml` → `search.extra_queries`.

## ⚠️ Zaroori baatein

- LinkedIn ki User Agreement automation tools allow nahi karti. Isliye account restrict hone ka risk hai. Limits conservative rakhi hain, par risk zero nahi hai. **Use apni zimmedari par karein.**
- LinkedIn ki language **English** rakhein (buttons English text se pehchane jaate hain).
- Scheduled time par computer **on** hona chahiye aur aap usme logged-in hone chahiye. Run ke time browser window khulti hai, use band na karein.
- LinkedIn apna design badalta rehta hai. Koi button na mile to woh profile skip ho jaati hai. Details `logs/` mein milengi.
- AI mode cost: lagbhag $0.01-0.03 per profile (ek din mein 40-60 profiles). FREE mode mein koi kharcha nahi.

## 📁 Share karte waqt

`data/` (aapka LinkedIn login session + database), `.env` (API key) aur `logs/` **kabhi share mat karna**. `.gitignore` inhe pehle se exclude karta hai.
Zip banana ho to:

```bash
zip -r linkedin-automation.zip . -x ".venv/*" "data/*" "logs/*" ".env" "*__pycache__*"
```

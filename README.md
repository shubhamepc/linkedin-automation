# LinkedIn Automation 🤝

Grow your LinkedIn network on autopilot. Every day this tool:

1. searches LinkedIn for people in **your** niche (e.g. founders, CEOs, HR managers),
2. opens each profile and checks whether it matches what you're looking for,
3. sends a connection request — with a personalised note when your account allows it,
4. keeps the volume low and human-like, so it looks like normal use.

Everything runs from the Terminal (Mac) or Command Prompt (Windows), on your own computer, with your own LinkedIn account.

> ⚠️ **Read this first.** LinkedIn's User Agreement does not allow automation tools. Using one can get your account warned or temporarily restricted. This tool keeps limits conservative and stops itself at the first warning, but the risk is never zero. **Use it at your own risk.**

---

## Contents

1. [What you need](#1-what-you-need)
2. [Install on Mac](#2-install-on-mac)
3. [Install on Windows](#3-install-on-windows)
4. [The setup wizard, step by step](#4-the-setup-wizard-step-by-step)
5. [Your first real run](#5-your-first-real-run)
6. [Daily use](#6-daily-use)
7. [How it decides who to invite](#7-how-it-decides-who-to-invite)
8. [Safety limits](#8-safety-limits)
9. [Changing settings](#9-changing-settings)
10. [Troubleshooting](#10-troubleshooting)
11. [Update, stop or uninstall](#11-update-stop-or-uninstall)
12. [Privacy](#12-privacy)

---

## 1. What you need

| | |
|---|---|
| **Computer** | Mac (tested) or Windows 10/11. It must be **on** at the daily run time. |
| **Google Chrome** | Recommended. If it's missing, a built-in browser is installed instead. |
| **LinkedIn account** | Set LinkedIn's language to **English** (Settings → Account preferences → Language). |
| **LinkedIn Premium** | Optional. Premium = a note with every invite. Free account = a few free notes per month, then invites are sent without a note automatically. |
| **Claude API key** | Optional, only for AI mode (see below). FREE mode needs nothing. |

**Two modes:**

| | FREE mode (default) | AI mode (optional) |
|---|---|---|
| Who gets invited | Profiles whose headline/profile contains your keywords | Claude (AI) reads each profile and scores it 0–100 |
| Note | From templates; name and company filled in automatically | A unique note written for each person |
| Cost | Nothing | About $1/day of Claude API credits |

---

## 2. Install on Mac

1. Open **https://github.com/shubhamepc/linkedin-automation**
2. Click the green **Code** button → **Download ZIP**.
3. Open your **Downloads** folder and double-click the ZIP. You get a folder called `linkedin-automation-main`.
   👉 Move this folder to where you want to keep it (for example **Documents**) **now**. Don't move it after setup, or the daily schedule will stop working.
4. Open **Terminal** (press `Cmd + Space`, type `Terminal`, press Enter).
5. Type `cd ` (with a space after it), **drag the folder into the Terminal window**, and press **Enter**.
6. Type this and press **Enter**:
   ```bash
   bash setup.sh
   ```
   The first time takes 1–3 minutes. It installs everything it needs (including Python, if your Mac doesn't have a new enough version). Then the setup wizard starts automatically → go to [section 4](#4-the-setup-wizard-step-by-step).

---

## 3. Install on Windows

> Windows support is newer than Mac support. If something goes wrong, take a screenshot of the window and send it to whoever shared this tool with you.

1. **Install Python** (one time): go to **https://www.python.org/downloads/**, download, and run the installer.
   ⚠️ On the first screen of the installer, tick **"Add python.exe to PATH"**, then click **Install Now**.
2. Open **https://github.com/shubhamepc/linkedin-automation** → green **Code** button → **Download ZIP**.
3. Right-click the ZIP → **Extract All…** → choose a place to keep it (for example **Documents**). Don't move the folder after setup.
4. Open the extracted `linkedin-automation-main` folder and double-click **`setup.bat`**.
   If Windows shows "Windows protected your PC", click **More info** → **Run anyway**.
5. Wait 2–5 minutes while it installs. Then the setup wizard starts automatically → go to [section 4](#4-the-setup-wizard-step-by-step).

---

## 4. The setup wizard, step by step

The wizard asks a few questions. **Pressing Enter accepts the default shown in `[brackets]`.**
You can run it again at any time:

- Mac: `.venv/bin/python run.py start`
- Windows: `.venv\Scripts\python run.py start`

### Step 1/5 · Mode

```
Use AI mode? (y/N):
```
Type **`n`** (or just press Enter) for **FREE mode**. Type `y` only if you have a Claude API key with credits.

### Step 2/5 · Connect LinkedIn

A **new Chrome window** opens on the LinkedIn login page. It's a separate Chrome profile just for this tool, so your normal Chrome is not touched.

1. Log in with your LinkedIn email and password (and OTP / 2FA if asked).
2. Wait until your LinkedIn **feed** (home page) appears, then wait **10 more seconds**.
3. Close that Chrome:
   - **Mac:** click on that Chrome window, then press **`Cmd + Q`** (you'll see two Chrome icons in the Dock; this quits only the tool's one).
   - **Windows:** close the window with the **X**.

The Terminal then shows `✅ LinkedIn connected — session saved.`

> Your password is typed only into Chrome. The tool never sees or stores it. You only need to do this once (and again if LinkedIn logs you out someday).

### Step 3/5 · Who to connect with

A browser window opens by itself for a few seconds to read your own profile. **Don't touch it.**

```
You: Jane Doe — Web Developer at Acme
Target keywords [Web Developer, Acme]:
```
Type the words that appear in the **headlines of the people you want to meet**, separated by commas. For example:

- Selling web services to businesses → `founder, CEO, business owner, startup`
- Recruiting → `HR manager, talent acquisition, recruiter`
- Finding peers → `product manager, product owner`

Then:
```
Skip people whose headline has [student, intern, open to work, ...]:   ← press Enter
What to type in LinkedIn search [founder, CEO, ...]:                   ← press Enter
```

### Step 4/5 · Test run

```
Run the test? (Y/n):   ← press Enter
```
The tool checks 3 profiles and shows the score and the note it *would* send. **Nothing is sent.** Example:
```
Ashok Nehra — founder | score 85 | in headline: founder, CEO
[dry run] note: Hi Ashok, your work at ASN International caught my eye. Always good to connect…
```

### Step 5/5 · Daily schedule

```
Set up the daily schedule? (Y/n):          ← press Enter
Daily start time (24h HH:MM) [10:30]:      ← press Enter, or type e.g. 11:00
✅ Will run every day at 10:30 (+ a random 0-75 min delay).
```
Done! 🎉

---

## 5. Your first real run

Before leaving it on autopilot, send just 2 invites yourself and check them:

- Mac: `.venv/bin/python run.py run --max 2`
- Windows: `.venv\Scripts\python run.py run --max 2`

You'll see lines like `→ sent`. On LinkedIn, open **My Network → Manage → Sent** (invitations). Both invites should be there.

---

## 6. Daily use

You don't need to do anything. Every day at your scheduled time (plus a random delay):

- A Chrome window opens and works by itself for 30–90 minutes. **Don't close it.**
- On a Mac you get a notification at the end, e.g. *"sent 7 invites, checked 25 profiles"*.
- The computer must be **on** (a Mac that's asleep runs it when it wakes up).

**See your report anytime:**

- Mac: `.venv/bin/python run.py stats`
- Windows: `.venv\Scripts\python run.py stats`

```
📊 Profiles by status
   new              30     ← found, not checked yet
   sent              5     ← invite sent, waiting
   accepted          2     ← they accepted 🎉
   low_score         4     ← didn't match your keywords
   not_connectable   6     ← already connected / already invited

   Sent in last 7 days : 7 / 80
   Acceptance rate     : 2/7 = 28%
```
An acceptance rate above 20% is healthy. If it's lower, make your keywords more specific (`run.py setup`).

**All commands** (Mac: `.venv/bin/python run.py …`, Windows: `.venv\Scripts\python run.py …`):

| Command | What it does |
|---|---|
| `start` | The setup wizard (safe to run again) |
| `stats` | Report |
| `run --dry-run` | Test: check 3 profiles, send nothing |
| `run` | Run today's batch now (if the schedule hasn't already) |
| `run --max 5` | Run today with at most 5 invites |
| `setup` | Change your keywords |
| `login` | Log in to LinkedIn again |
| `schedule` / `unschedule` | Turn the daily run on / off |

---

## 7. How it decides who to invite

**FREE mode**

| Match | Score | Invited? |
|---|---|---|
| A target keyword in their **headline** | 75–100 | ✅ yes |
| Keywords only elsewhere on their profile | 55 (1 keyword), 65 (2), 75 (3+) | only with 3+ keywords |
| A "skip" keyword in their headline | 0 | ❌ no |
| Already connected / already invited | — | ❌ skipped |

The note is picked at random from templates, e.g.
*"Hi Ashok, your work at ASN International caught my eye. Always good to connect with people in a similar space. Happy to connect!"*

**AI mode:** Claude reads your own profile to understand your niche, then reads each person's profile, scores it 0–100 (70+ gets invited), and writes a note that mentions something specific from their profile.

---

## 8. Safety limits

| | Default |
|---|---|
| Week 1 / week 2 (warm-up) | 5–8 / 8–14 invites per day |
| After that | 12–22 on weekdays, 3–7 on Saturday, **Sunday off** |
| Weekly maximum | 80 (LinkedIn's own limit is ~100/week) |
| Start time | Different every day (your time + 0–75 min) |
| Between profiles | 40–140 seconds, plus a 3–9 min break every 5–9 profiles |
| Rest days | Occasionally skips a whole day |
| Low acceptance (< 20%) | Daily volume is halved automatically |
| Old invites | Invites pending for 21+ days are withdrawn |
| LinkedIn warning, security check or weekly limit | **Stops immediately** and pauses for 3–4 days |

---

## 9. Changing settings

All settings are in **`config.yaml`** (open it with any text editor: TextEdit on Mac, Notepad on Windows). Each line has a comment explaining it. The most useful ones:

| Setting | What it changes |
|---|---|
| `schedule.time` | Daily start time (run `schedule` again after changing it) |
| `schedule.active_days` | Which days it runs |
| `limits.normal` | Invites per day after the warm-up |
| `rules.note_templates` | Your note templates. Placeholders: `{first_name}`, `{company}`, `{topic}`, `{my_name}` |
| `ai.mode` | `rules` = FREE mode, `claude` = AI mode |
| `ai.min_score` | Minimum score to send an invite (default 70) |

Keep notes under 280 characters.

---

## 10. Troubleshooting

| Problem | Fix |
|---|---|
| `LinkedIn is not logged in` | Run `login` (see [section 4, step 2](#step-25--connect-linkedin)). Remember to fully close that Chrome at the end (`Cmd + Q` on Mac). |
| `Could not confirm the login` | You closed Chrome before the feed loaded, or too quickly. Run `login` again and wait 10 seconds on the feed before closing. |
| `browser window was closed` | Someone closed the bot's Chrome while it was working. It will continue tomorrow, or run `run` now. |
| `LinkedIn free notes used up for this month` | Normal on a free account. Invites continue without a note, and notes are tried again next month. |
| `STOPPED: … paused until …` | LinkedIn showed a warning or limit. The tool pauses by itself. Don't force it; let it rest. |
| `Today's run is already done` | It already ran today. Use `run --force` to run again (not recommended). |
| Nothing happened at the scheduled time | The computer was off or asleep, or the folder was moved. Run `schedule` again. |
| `command not found` / `not recognized` | You're not in the tool's folder. Mac: `cd ` + drag the folder in + Enter. Windows: open the folder, click the address bar, type `cmd`, press Enter. |
| Windows: `Python 3.10+ not found` | Reinstall Python and tick **"Add python.exe to PATH"**. |
| Lots of `skip: unavailable` | Check that LinkedIn's language is **English**. |

Logs for every day are in the **`logs`** folder. Send the latest one if you need help.

---

## 11. Update, stop or uninstall

**Update to the latest version:** download the ZIP again and copy its files over your folder. **Keep** your `data` folder, `.env` and `config.yaml`. Then run `bash setup.sh` (Mac) or `setup.bat` (Windows) again.

**Pause:** `unschedule` (start again later with `schedule`).

**Uninstall:** run `unschedule`, then delete the folder.

---

## 12. Privacy

- Everything stays on **your computer**. Nothing is sent anywhere except LinkedIn (and Claude, only in AI mode).
- Your LinkedIn login session is in the `data` folder, and your API key (AI mode) in `.env`. **Never share these** with anyone. If you send the folder to someone, delete `data`, `logs` and `.env` first.
- The tool never sees your LinkedIn password.

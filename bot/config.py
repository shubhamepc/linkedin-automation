import logging
import sys
from datetime import date
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LOGS = ROOT / "logs"
BROWSER_PROFILE = DATA / "browser-profile"
DB_PATH = DATA / "linkedin.db"
MY_PROFILE_PATH = DATA / "my_profile.json"

DATA.mkdir(exist_ok=True)
LOGS.mkdir(exist_ok=True)
load_dotenv(ROOT / ".env")

# Windows Command Prompt mein emoji / Hindi text crash na kare
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def load_config() -> dict:
    with open(ROOT / "config.yaml") as f:
        return yaml.safe_load(f)


CFG = load_config()


def setup_logging() -> logging.Logger:
    log = logging.getLogger("bot")
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s", "%H:%M:%S")
    fh = logging.FileHandler(LOGS / f"{date.today().isoformat()}.log", encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    log.addHandler(fh)
    log.addHandler(sh)
    return log


log = setup_logging()

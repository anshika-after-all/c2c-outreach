"""PDF section 6.2 — project paths and .env values."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
SESSION = ROOT / "session.json"
RECRUITERS = ROOT / "recruiters.csv"
HISTORY = ROOT / "email_sent_history.csv"
SCRATCH = ROOT / "scratch"
REPORT = ROOT / "analytics_report.html"

load_dotenv(ROOT / ".env")


def env(name: str, default: str = "") -> str:
    # Values are trimmed so a copied app password still logs in.
    return os.getenv(name, default).strip()

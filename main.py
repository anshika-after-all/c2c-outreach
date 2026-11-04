"""PDF sections 2 and 7 — menus for one candidate or every candidate.

Run from this folder:
    python main.py
Copy .env.example to .env first. Option 2 saves the LinkedIn session.
"""

import os
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

import db
from client_config import CANDIDATE_ROLES, CLIENTS, candidate, resume_path
from gmail_sender import customize_for, file_name, send_pending
from settings import SCRATCH, SESSION, env

console = Console()
SAMPLE_JD = (
    "Hiring a Java Developer in Dallas, TX. C2C contract. "
    "Looking for Java, Spring Boot, PostgreSQL, AWS, and Kafka."
)
MENU = """
[1] Run outreach for one candidate
[2] Setup/Test LinkedIn Login Session
[3] Check inbox for replies
[4] Send threaded follow-ups
[5] Analytics report
[6] Validate setup
[7] Customize one resume
[8] Run Full Pipeline for ALL Candidates (Automated Batch Mode)
[0] Exit
"""


def pick_client() -> str:
    keys = list(CLIENTS)
    for number, key in enumerate(keys, 1):
        person = CLIENTS[key]
        console.print(f"[{number}] {person['name']} — {CANDIDATE_ROLES[key]['primary_role']}")
    choice = Prompt.ask("Candidate", choices=[str(number) for number in range(1, len(keys) + 1)])
    return keys[int(choice) - 1]


def pick_roles(key: str):
    roles = CANDIDATE_ROLES[key]["search_roles"]
    for number, role in enumerate(roles, 1):
        console.print(f"[{number}] {role}")
    raw = Prompt.ask("Roles (numbers separated by commas, or all)", default="all")
    if raw.strip().lower() == "all":
        return list(roles)
    return [roles[int(part.strip()) - 1] for part in raw.split(",") if part.strip()]


def ask_mode() -> str:
    return Prompt.ask("Send mode", choices=["test", "live"], default="test")


def ask_limit() -> int:
    raw = Prompt.ask("Daily send limit", default="10")
    if not raw.isdigit() or int(raw) < 1:
        raise ValueError("Daily send limit must be a positive number")
    return int(raw)


def confirm_send() -> bool:
    return Prompt.ask("Type SEND to email recruiters") == "SEND"


def show_stats(stats):
    console.print(
        f"New rows {stats['saved']}. Dropped: no email {stats['no_email']}, "
        f"location/bench {stats['filtered']}, wrong role {stats['mismatch']}."
    )


def show_rows(rows):
    table = Table(title="Pending recruiters")
    for column in ("recruiter_name", "recruiter_email", "role"):
        table.add_column(column)
    for row in rows[:20]:
        table.add_row(row["recruiter_name"], row["recruiter_email"], row["role"])
    console.print(table)
    if len(rows) > 20:
        console.print(f"{len(rows) - 20} more not shown.")


def show_results(results):
    if not results:
        console.print("Nothing to send.")
        return
    for item in results:
        console.print(f"{item['status']:8} {item['email']}  {item['detail']}")


def option_one():
    # Scrape, show the rows, then wait for SEND before any live email goes out.
    key = pick_client()
    roles = pick_roles(key)
    mode = ask_mode()
    limit = ask_limit()
    profile = candidate(key)
    resume_path(key)
    from linkedin_scraper import LinkedInSession
    with LinkedInSession() as linkedin:
        stats = linkedin.scrape(key, roles)
    show_stats(stats)
    rows = db.pending(profile["name"], roles)
    show_rows(rows)
    if not rows:
        return
    if mode == "live" and not confirm_send():
        console.print("Stopped before sending.")
        return
    show_results(send_pending(profile, rows, mode, limit))


def option_login():
    from linkedin_login import login
    login()


def option_replies():
    from imap_reply_detector import check_replies
    report = check_replies()
    console.print(
        f"Searched since {report['since']}. "
        f"Checked {report['checked']} message(s). Marked {report['matched']} replied."
    )


def option_followups():
    from followup_sender import send_followups
    raw = Prompt.ask("Days since the first email", default="7")
    if not raw.isdigit():
        raise ValueError("Days must be a number")
    days = int(raw)
    mode = ask_mode()
    if mode == "live" and not confirm_send():
        console.print("Stopped before sending.")
        return
    target = date.today() - timedelta(days=days)
    console.print(f"Emails sent on {target.isoformat()} are eligible.")
    show_results(send_followups(days, mode))


def option_analytics():
    from analytics import summary_lines, write_report
    for line in summary_lines():
        console.print(line)
    console.print(f"Wrote {write_report()}")


def option_validate():
    for key in CLIENTS:
        try:
            console.print(f"Resume {key}: {resume_path(key)}")
        except FileNotFoundError as exc:
            console.print(f"Resume {key}: {exc}")
    for name in (
        "GMAIL_EMAIL", "GMAIL_APP_PASSWORD", "GEMINI_API_KEY",
        "GROQ_API_KEY", "OPENROUTER_API_KEY", "ADMIN_EMAIL",
    ):
        console.print(f"{name}: {'set' if env(name) else 'missing'}")
    console.print(f"session.json: {'found' if SESSION.exists() else 'missing'}")
    office = [
        Path(os.environ.get("ProgramFiles", "")) / "Microsoft Office/root/Office16/WINWORD.EXE",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft Office/root/Office16/WINWORD.EXE",
    ]
    word = any(path.exists() for path in office) or bool(shutil.which("winword"))
    console.print(f"Microsoft Word: {'found' if word else 'not found (needed to make PDFs)'}")


def option_customize():
    key = pick_client()
    profile = candidate(key)
    raw = Prompt.ask("Path to a .txt job description (blank uses a sample)", default="")
    job = Path(raw).read_text(encoding="utf-8") if raw.strip() else SAMPLE_JD
    destination = SCRATCH / file_name(profile["name"])
    console.print(customize_for(profile, job, resume_path(key), destination))


def option_all():
    # One browser session, then each candidate in client_config.py, under one daily cap.
    mode = ask_mode()
    limit = ask_limit()
    if mode == "live" and not confirm_send():
        console.print("Stopped before sending.")
        return
    from linkedin_scraper import LinkedInSession
    remaining = limit
    with LinkedInSession() as linkedin:
        for key in CLIENTS:
            if remaining <= 0:
                break
            profile = candidate(key)
            roles = list(CANDIDATE_ROLES[key]["search_roles"])
            console.print(f"\n[bold]{profile['name']}[/bold]")
            try:
                resume_path(key)
                stats = linkedin.scrape(key, roles)
            except Exception as exc:
                console.print(f"[red]{exc}[/red]")
                continue
            show_stats(stats)
            rows = db.pending(profile["name"], roles)
            show_rows(rows)
            results = send_pending(profile, rows, mode, remaining)
            show_results(results)
            remaining -= len(results)
    console.print(f"Processed {limit - remaining} recruiter(s).")


ACTIONS = {
    "1": option_one,
    "2": option_login,
    "3": option_replies,
    "4": option_followups,
    "5": option_analytics,
    "6": option_validate,
    "7": option_customize,
    "8": option_all,
}


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    db.ensure()
    while True:
        console.print(Panel(MENU.strip(), title="C2C Outreach"))
        choice = Prompt.ask("Choose", choices=[*ACTIONS.keys(), "0"], default="0")
        if choice == "0":
            break
        try:
            ACTIONS[choice]()
        except KeyboardInterrupt:
            console.print("\nStopped.")
        except Exception as exc:
            console.print(f"[red]{exc}[/red]")


if __name__ == "__main__":
    main()

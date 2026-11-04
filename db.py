"""PDF section 4 — recruiters.csv and email_sent_history.csv.

Missing columns are added the next time a file is opened, so old files
keep working when the header list grows.
"""

from datetime import datetime, timedelta

import pandas as pd

from settings import HISTORY, RECRUITERS, SCRATCH

RECRUITER_COLUMNS = [
    "recruiter_name", "recruiter_email", "role", "post_url",
    "job_description", "email_sent_status", "timestamp",
]
HISTORY_COLUMNS = [
    "recruiter_name", "recruiter_email", "role", "post_url", "candidate",
    "email_sent_status", "timestamp", "subject", "message_id",
    "followup_count", "last_followup_at", "replied",
]
COUNT_COLUMNS = {"followup_count", "replied"}


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _save(path, frame, columns):
    out = frame.copy()
    for column in columns:
        if column not in out.columns:
            out[column] = "0" if column in COUNT_COLUMNS else ""
    out[columns].fillna("").astype(str).to_csv(path, index=False, encoding="utf-8")


def _load(path, columns):
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")
    changed = list(frame.columns) != columns
    for column in columns:
        if column not in frame.columns:
            frame[column] = "0" if column in COUNT_COLUMNS else ""
    if changed:
        _save(path, frame, columns)
    return frame[columns]


def ensure():
    SCRATCH.mkdir(parents=True, exist_ok=True)
    for path, columns in ((RECRUITERS, RECRUITER_COLUMNS), (HISTORY, HISTORY_COLUMNS)):
        if not path.exists():
            _save(path, pd.DataFrame(), columns)


def load_recruiters():
    ensure()
    return _load(RECRUITERS, RECRUITER_COLUMNS)


def load_history():
    ensure()
    return _load(HISTORY, HISTORY_COLUMNS)


def add_recruiters(rows: list[dict]) -> int:
    # Same email + role + post is stored once.
    if not rows:
        return 0
    frame = load_recruiters()
    before = len(frame)
    frame = pd.concat([frame, pd.DataFrame(rows)], ignore_index=True)
    frame["recruiter_email"] = frame["recruiter_email"].str.lower()
    key = (
        frame["recruiter_email"] + "|" + frame["role"] + "|" + frame["post_url"]
        + "|" + frame["job_description"].str.slice(0, 120)
    )
    frame = frame.loc[~key.duplicated()].reset_index(drop=True)
    _save(RECRUITERS, frame, RECRUITER_COLUMNS)
    return len(frame) - before


def add_history(row: dict):
    frame = load_history()
    filled = {column: str(row.get(column, "")) for column in HISTORY_COLUMNS}
    filled["followup_count"] = filled["followup_count"] or "0"
    filled["replied"] = filled["replied"] or "0"
    frame = pd.concat([frame, pd.DataFrame([filled])], ignore_index=True)
    _save(HISTORY, frame, HISTORY_COLUMNS)


def set_recruiter_status(email: str, role: str, status: str, post_url: str = ""):
    frame = load_recruiters()
    mask = (frame["recruiter_email"].str.lower() == email.lower()) & (frame["role"] == role)
    if post_url:
        mask = mask & (frame["post_url"] == post_url)
    frame.loc[mask, "email_sent_status"] = status
    _save(RECRUITERS, frame, RECRUITER_COLUMNS)


def pending(candidate_name: str, roles) -> list[dict]:
    # Skip anyone this candidate already emailed. A failed try can run again.
    recruiters = load_recruiters()
    history = load_history()
    sent = set(
        history.loc[
            (history["candidate"] == candidate_name) & (history["email_sent_status"] == "sent"),
            "recruiter_email",
        ].str.lower()
    )
    role_set = set(roles)
    rows = []
    for record in recruiters.to_dict("records"):
        email = record["recruiter_email"].lower()
        if record["email_sent_status"] == "pending" and record["role"] in role_set and email not in sent:
            rows.append(record)
    return rows


def job_description(email: str, role: str) -> str:
    frame = load_recruiters()
    mask = (frame["recruiter_email"].str.lower() == email.lower()) & (frame["role"] == role)
    hit = frame.loc[mask]
    return "" if hit.empty else hit.iloc[-1]["job_description"]


def due_followups(days: int) -> list[dict]:
    # The send date must be exactly N calendar days ago, with no reply yet.
    target = (datetime.now().date() - timedelta(days=days)).isoformat()
    due = []
    for record in load_history().to_dict("records"):
        sent_on = str(record["timestamp"])[:10]
        if (
            record["email_sent_status"] == "sent"
            and record["followup_count"] in ("0", "")
            and record["replied"] in ("0", "")
            and sent_on == target
        ):
            due.append(record)
    return due


def mark_followup(email: str, candidate_name: str):
    frame = load_history()
    mask = (
        (frame["recruiter_email"].str.lower() == email.lower())
        & (frame["candidate"] == candidate_name)
        & (frame["email_sent_status"] == "sent")
    )
    for index in frame.index[mask]:
        frame.at[index, "followup_count"] = str(int(frame.at[index, "followup_count"] or "0") + 1)
        frame.at[index, "last_followup_at"] = now()
    _save(HISTORY, frame, HISTORY_COLUMNS)


def mark_replies(sender_emails) -> int:
    wanted = {email.lower() for email in sender_emails}
    frame = load_history()
    mask = (
        frame["recruiter_email"].str.lower().isin(wanted)
        & (frame["replied"] == "0")
        & (frame["email_sent_status"] == "sent")
    )
    count = int(mask.sum())
    if count:
        frame.loc[mask, "replied"] = "1"
        _save(HISTORY, frame, HISTORY_COLUMNS)
    return count


def oldest_unreplied():
    # IMAP searches from this day so it does not scan the whole mailbox.
    frame = load_history()
    mask = (frame["email_sent_status"] == "sent") & (frame["replied"] == "0")
    dates = [str(value)[:10] for value in frame.loc[mask, "timestamp"] if str(value)[:10]]
    if not dates:
        return datetime.now().date() - timedelta(days=30)
    return datetime.strptime(min(dates), "%Y-%m-%d").date()

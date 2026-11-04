"""Outreach counts and a dark HTML report."""

from html import escape
from datetime import datetime

import pandas as pd

import db
from settings import REPORT


def gather() -> dict:
    recruiters = db.load_recruiters()
    history = db.load_history()
    sent = history[history["email_sent_status"] == "sent"]
    followups = pd.to_numeric(history["followup_count"], errors="coerce").fillna(0).sum()
    by_candidate = sent.groupby("candidate").size().sort_values(ascending=False).to_dict() if len(sent) else {}
    recent = sent.tail(15)[["timestamp", "candidate", "recruiter_email", "role", "replied"]].to_dict("records")
    return {
        "scraped": len(recruiters),
        "pending": int((recruiters["email_sent_status"] == "pending").sum()),
        "mismatched": int((recruiters["email_sent_status"] == "mismatched_role").sum()),
        "sent": len(sent),
        "failed": int((history["email_sent_status"] == "failed").sum()),
        "replied": int((sent["replied"] == "1").sum()) if len(sent) else 0,
        "followups": int(followups),
        "by_candidate": by_candidate,
        "recent": list(reversed(recent)),
    }


def summary_lines(stats=None) -> list[str]:
    stats = stats or gather()
    rate = round(100 * stats["replied"] / stats["sent"], 1) if stats["sent"] else 0
    return [
        f"Scraped {stats['scraped']}   pending {stats['pending']}   mismatched {stats['mismatched']}",
        f"Sent {stats['sent']}   failed {stats['failed']}   replied {stats['replied']} ({rate}%)   follow-ups {stats['followups']}",
    ]


def _cards(stats) -> str:
    rate = round(100 * stats["replied"] / stats["sent"], 1) if stats["sent"] else 0
    labels = [
        ("Scraped", stats["scraped"]),
        ("Pending", stats["pending"]),
        ("Sent", stats["sent"]),
        ("Replied", f"{stats['replied']} ({rate}%)"),
        ("Follow-ups", stats["followups"]),
        ("Failed", stats["failed"]),
    ]
    return "".join(f"<div class='card'><b>{escape(str(value))}</b>{escape(label)}</div>" for label, value in labels)


def _table(headers, rows) -> str:
    head = "".join(f"<th>{escape(header)}</th>" for header in headers)
    body = []
    for row in rows:
        cells = "".join(f"<td>{escape(str(cell))}</td>" for cell in row)
        body.append(f"<tr>{cells}</tr>")
    if not body:
        body.append(f"<tr><td colspan='{len(headers)}'>None yet</td></tr>")
    return f"<table><tr>{head}</tr>{''.join(body)}</table>"


def render(stats) -> str:
    by_candidate = _table(["Candidate", "Sent"], list(stats["by_candidate"].items()))
    recent = _table(
        ["When", "Candidate", "Recruiter", "Role", "Replied"],
        [
            (row["timestamp"], row["candidate"], row["recruiter_email"], row["role"], "yes" if row["replied"] == "1" else "no")
            for row in stats["recent"]
        ],
    )
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>C2C Outreach</title>
<style>
body {{ margin: 0; background: #0d1117; color: #e6edf3; font: 16px/1.5 "Segoe UI", sans-serif; }}
main {{ max-width: 960px; margin: 0 auto; padding: 32px 20px 64px; }}
h1 {{ font-weight: 600; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; }}
.card {{ background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 16px; }}
.card b {{ display: block; font-size: 28px; color: #79c0ff; }}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid #30363d; }}
th {{ color: #8b949e; font-weight: 600; }}
h2 {{ margin-top: 32px; font-size: 18px; }}
footer {{ color: #8b949e; margin-top: 28px; }}
</style></head><body><main>
<h1>C2C Outreach</h1>
<section class="grid">{_cards(stats)}</section>
<h2>By candidate</h2>
{by_candidate}
<h2>Recent sends</h2>
{recent}
<footer>Generated {escape(generated)}</footer>
</main></body></html>
"""


def write_report() -> str:
    stats = gather()
    REPORT.write_text(render(stats), encoding="utf-8")
    return str(REPORT)

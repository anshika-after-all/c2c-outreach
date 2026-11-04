"""PDF section 5.4 — one threaded follow-up, sent on day N."""

import time

import db
from client_config import CLIENTS, candidate, resume_path
from gmail_sender import compose, deliver, file_name
from llm_client import complete_text
from settings import SCRATCH


def _pitch(profile, row, job_text: str) -> str:
    prompt = (
        "Write 1 or 2 sentences for a follow-up email. No greeting and no sign-off. "
        f"{profile['name']} is a {profile['experience']} {profile['primary_role']}. "
        f"Role: {row['role']}.\n\n{job_text[:3000]}"
    )
    try:
        return " ".join(complete_text(prompt).split())[:500]
    except Exception:
        return (
            f"I keep building as a {profile['primary_role']} and can start "
            f"{profile['availability'].lower()}."
        )


def _body(profile, row, pitch: str) -> str:
    first = str(row.get("recruiter_name", "")).split()
    greeting = first[0] if first and first[0].lower() != "recruiter" else "there"
    return (
        f"Hi {greeting},\n\n"
        f"Following up on my note. {pitch}\n\n"
        f"{profile['name']}\n{profile['phone']}\n{profile['linkedin']}\n"
    )


def send_followups(days: int, mode: str) -> list[dict]:
    by_name = {person["name"]: candidate(key) for key, person in CLIENTS.items()}
    results = []
    seen = set()
    for row in db.due_followups(days):
        if row["recruiter_email"].lower() in seen:
            continue
        seen.add(row["recruiter_email"].lower())
        profile = by_name.get(row["candidate"])
        if profile is None:
            results.append({
                "email": row["recruiter_email"],
                "status": "failed",
                "detail": "candidate is not in client_config.py",
            })
            continue
        pitch = _pitch(profile, row, db.job_description(row["recruiter_email"], row["role"]))
        body = _body(profile, row, pitch)
        subject = row["subject"] if str(row["subject"]).lower().startswith("re:") else f"Re: {row['subject']}"
        source = resume_path(profile["key"])
        try:
            if mode != "live":
                path = SCRATCH / f"followup_{int(time.time() * 1000)}.txt"
                path.write_text(f"To: {row['recruiter_email']}\nSubject: {subject}\n\n{body}", encoding="utf-8")
                results.append({"email": row["recruiter_email"], "status": "preview", "detail": str(path)})
                continue
            if profile.get("email", "").endswith("@example.com"):
                raise RuntimeError("Replace the sample candidate in client_config.py before a live send.")
            deliver(compose(
                profile, row, body, subject, source,
                file_name(profile["name"], source.suffix.lower() or ".pdf"),
                row.get("message_id", ""),
            ))
            db.mark_followup(row["recruiter_email"], profile["name"])
            results.append({"email": row["recruiter_email"], "status": "sent", "detail": subject})
        except Exception as exc:
            results.append({"email": row["recruiter_email"], "status": "failed", "detail": str(exc)})
        if mode == "live":
            time.sleep(3)
    return results

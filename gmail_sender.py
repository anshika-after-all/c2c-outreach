"""PDF section 5.2 — personalize a note and send it through Gmail."""

import smtplib
import time
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

import db
from client_config import resume_path
from filters import hook_sentence, top_keywords
from jane_customizer import customize as jane_customize
from llm_client import has_key
from resume_customizer import customize_resume
from settings import SCRATCH, env

# Section 8.2: add a client key here when their resume needs its own parser.
HOOKS = {
    "jane_doe": jane_customize,
}


def one_line(text) -> str:
    return " ".join(str(text).replace("\x00", "").split())


def file_name(name: str, suffix: str = ".pdf") -> str:
    # ASCII only. A new timestamp stops Gmail from reusing an old preview.
    base = "".join(ch for ch in name if ch.isascii() and ch.isalnum()) or "Candidate"
    return f"{base}_Resume_{int(time.time() * 1000)}{suffix}"


def customize_for(profile, job_description, source, destination):
    hook = HOOKS.get(profile["key"], customize_resume)
    return hook(job_description, source, destination, profile["key"])


def build_body(profile, row) -> str:
    first = one_line(row.get("recruiter_name", "")).split(" ")[0]
    if not first or first.lower() == "recruiter":
        first = "there"
    hook = hook_sentence(top_keywords(row.get("job_description", "")))
    return (
        f"Hi {first},\n\n"
        f"I saw your post for a {row['role']} and wanted to share my profile.\n\n"
        f"{hook}\n\n"
        f"I am a {profile['experience']} {profile['primary_role']} based in {profile['location']}. "
        f"Work authorization: {profile['work_auth']}. "
        f"Availability: {profile['availability']}. "
        f"Open to relocation: {profile['relocation']}.\n\n"
        "Resume attached.\n\n"
        f"{profile['name']}\n{profile['phone']}\n{profile['linkedin']}\n"
    )


def subject_for(profile, row) -> str:
    return one_line(f"{row['role']} | {profile['name']} | C2C | {profile['location']}")


def connect():
    # Port 587 with STARTTLS. If that is blocked, try SSL on 465.
    user = env("GMAIL_EMAIL")
    password = env("GMAIL_APP_PASSWORD").replace(" ", "")
    if not user or not password:
        raise RuntimeError("Set GMAIL_EMAIL and GMAIL_APP_PASSWORD in .env")
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=30)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(user, password)
        return server
    except Exception as first:
        try:
            server = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30)
            server.login(user, password)
            return server
        except Exception as second:
            raise RuntimeError(f"SMTP failed on 587 ({first}) and 465 ({second})") from None


def _copies(profile, recruiter_email):
    cc = []
    for address in (profile.get("email", ""), profile.get("lead_email", "")):
        address = address.strip()
        if address and address.lower() != recruiter_email.lower() and address not in cc:
            cc.append(address)
    bcc = env("ADMIN_EMAIL")
    if bcc.lower() == recruiter_email.lower():
        bcc = ""
    return cc, bcc


def attach(message, path, filename):
    path = Path(path)
    if path.suffix.lower() == ".docx":
        subtype = "vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        subtype = "pdf"
    message.add_attachment(path.read_bytes(), maintype="application", subtype=subtype, filename=filename)


def compose(profile, row, body, subject, attachment, filename, thread_id=""):
    message = EmailMessage()
    message["From"] = env("GMAIL_EMAIL")
    message["To"] = row["recruiter_email"]
    cc, bcc = _copies(profile, row["recruiter_email"])
    if cc:
        message["Cc"] = ", ".join(cc)
    if bcc:
        message["Bcc"] = bcc
    message["Subject"] = one_line(subject)
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid()
    if thread_id:
        thread = thread_id if str(thread_id).startswith("<") else f"<{str(thread_id).strip('<>')}>"
        message["In-Reply-To"] = thread
        message["References"] = thread
    message.set_content(body)
    if attachment:
        attach(message, attachment, filename)
    return message


def deliver(message) -> str:
    server = connect()
    try:
        server.send_message(message)
    finally:
        server.quit()
    return message["Message-ID"]


def _preview(row, subject, body, pdf):
    path = SCRATCH / f"preview_{int(time.time() * 1000)}.txt"
    attached = str(pdf) if pdf else "not customized (no AI key)"
    path.write_text(
        f"To: {row['recruiter_email']}\nSubject: {subject}\nAttachment: {attached}\n\n{body}",
        encoding="utf-8",
    )
    return path


def _history(profile, row, status, subject, message_id=""):
    db.add_history({
        "recruiter_name": row.get("recruiter_name", ""),
        "recruiter_email": row["recruiter_email"],
        "role": row.get("role", ""),
        "post_url": row.get("post_url", ""),
        "candidate": profile["name"],
        "email_sent_status": status,
        "timestamp": db.now(),
        "subject": subject,
        "message_id": message_id,
        "followup_count": "0",
        "last_followup_at": "",
        "replied": "0",
    })


def send_pending(profile, rows, mode, limit) -> list[dict]:
    # Test writes a preview and does not touch SMTP. Live customizes, sends, then waits 3 seconds.
    if mode == "live" and profile.get("email", "").endswith("@example.com"):
        raise RuntimeError("Replace the sample candidate in client_config.py before a live send.")
    results = []
    seen = set()
    for row in rows:
        if len(results) >= limit:
            break
        email = row["recruiter_email"].lower()
        if email in seen:
            continue
        seen.add(email)
        subject = ""
        try:
            pdf = None
            if mode == "live" or has_key():
                pdf = customize_for(
                    profile,
                    row.get("job_description", ""),
                    resume_path(profile["key"]),
                    SCRATCH / file_name(profile["name"]),
                )
            body = build_body(profile, row)
            subject = subject_for(profile, row)
            if mode != "live":
                results.append({
                    "email": row["recruiter_email"],
                    "status": "preview",
                    "detail": str(_preview(row, subject, body, pdf)),
                })
                continue
            message_id = deliver(compose(profile, row, body, subject, pdf, Path(pdf).name))
            _history(profile, row, "sent", subject, message_id)
            db.set_recruiter_status(row["recruiter_email"], row["role"], "sent", row.get("post_url", ""))
            results.append({"email": row["recruiter_email"], "status": "sent", "detail": subject})
        except Exception as exc:
            if mode == "live":
                _history(profile, row, "failed", subject)
            results.append({"email": row["recruiter_email"], "status": "failed", "detail": str(exc)})
        if mode == "live":
            time.sleep(3)
    return results

"""PDF section 5.5 — mark a recruiter replied when their address hits the inbox."""

import email
import imaplib
from email.utils import parseaddr

import db
from settings import env


def check_replies() -> dict:
    user = env("GMAIL_EMAIL")
    password = env("GMAIL_APP_PASSWORD").replace(" ", "")
    if not user or not password:
        raise RuntimeError("Set GMAIL_EMAIL and GMAIL_APP_PASSWORD in .env")
    since = db.oldest_unreplied().strftime("%d-%b-%Y")
    mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    try:
        mail.login(user, password)
        mail.select("INBOX", readonly=True)
        status, data = mail.search(None, f"(SINCE {since})")
        if status != "OK" or not data or not data[0]:
            return {"since": since, "checked": 0, "matched": 0}
        ids = data[0].split()
        senders = []
        for start in range(0, len(ids), 100):
            # Headers only, 100 at a time, so a large inbox stays light.
            fetched_status, fetched = mail.fetch(
                b",".join(ids[start : start + 100]),
                "(BODY.PEEK[HEADER.FIELDS (FROM)])",
            )
            if fetched_status != "OK":
                continue
            for part in fetched:
                if not isinstance(part, tuple) or not part[1]:
                    continue
                message = email.message_from_bytes(part[1])
                address = parseaddr(message.get("From", ""))[1].lower()
                if address:
                    senders.append(address)
        return {"since": since, "checked": len(ids), "matched": db.mark_replies(senders)}
    finally:
        try:
            mail.logout()
        except Exception:
            pass

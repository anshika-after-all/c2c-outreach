"""PDF section 5.1 — query text and the rules that keep or drop a post."""

import re
from urllib.parse import urlencode

from client_config import JD_KEYWORDS, NON_USA, USA_CITIES

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
STATE_RE = re.compile(
    r"\b(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|"
    r"MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|"
    r"WV|WI|WY|DC)\b"
)
SKIP_EMAIL_DOMAINS = ("linkedin.com", "example.com", "sentry.io")
BENCH_PHRASES = (
    "on my bench",
    "on the bench",
    "candidate available",
    "marketing my consultant",
    "my consultant is available",
)
# Title words that mean the post is hiring a different kind of engineer.
FOREIGN_DOMAINS = {
    "qa": ("qa", "quality assurance", "sdet", "tester"),
    "devops": ("devops", "site reliability", "sre"),
    "salesforce": ("salesforce", "sfdc"),
    "data": ("data scientist", "data analyst", "data engineer"),
    "dotnet": (".net", "dotnet", "c#"),
    "frontend": ("react", "angular", "frontend", "ui developer", "javascript"),
    "python": ("python",),
    "java": ("java",),
}
TITLE_HINTS = ("developer", "engineer", "architect", "scientist", "analyst", "qa", "sdet", "devops")


def _has_phrase(text: str, phrases) -> bool:
    low = text.lower()
    return any(re.search(rf"\b{re.escape(phrase)}\b", low) for phrase in phrases)


def build_query(role: str, exclusions) -> str:
    # Spec query: "<Role> + C2C -hotlist -fulltime -\"available consultants\" -Bench"
    parts = [role, "+ C2C", "-hotlist", "-fulltime", '-"available consultants"', "-Bench"]
    seen = " ".join(parts).lower()
    for raw in exclusions:
        word = str(raw).strip()
        if not word or word.lower() in seen:
            continue
        parts.append(f'-"{word}"' if " " in word else f"-{word}")
        seen += " " + word.lower()
    return " ".join(parts)


def search_url(role: str, exclusions) -> str:
    # Last 24 hours, newest first, United States geoUrn 103644278.
    params = {
        "keywords": build_query(role, exclusions),
        "origin": "FACETED_SEARCH",
        "datePosted": '"past-24h"',
        "sortBy": '"date_posted"',
        "geoUrn": "103644278",
    }
    return "https://www.linkedin.com/search/results/content/?" + urlencode(params)


def clean_email(raw: str) -> str:
    email = raw.strip().strip(".,;:<>\"'").lower()
    if not EMAIL_RE.fullmatch(email):
        return ""
    domain = email.split("@", 1)[1]
    if any(domain == skip or domain.endswith("." + skip) for skip in SKIP_EMAIL_DOMAINS):
        return ""
    return email


def emails_in(text: str) -> list[str]:
    found = []
    for match in EMAIL_RE.findall(text or ""):
        email = clean_email(match)
        if email and email not in found:
            found.append(email)
    return found


def is_bench_post(text: str) -> bool:
    low = text.lower()
    return any(phrase in low for phrase in BENCH_PHRASES)


def is_usa_job(text: str) -> bool:
    # A non-US place drops the post. "Remote" with no US place is not enough.
    if _has_phrase(text, NON_USA):
        return False
    if _has_phrase(text, USA_CITIES):
        return True
    if re.search(r"\b(usa|u\.s\.a\.?|u\.s\.|united states)\b", text, re.I) or re.search(r"\bUS\b", text):
        return True
    return bool(STATE_RE.search(text))


def job_title(text: str) -> str:
    # The hiring title is the first short line that looks like a role.
    for line in text.splitlines():
        line = line.strip()
        low = line.lower()
        if 3 <= len(line) <= 90 and any(hint in low for hint in TITLE_HINTS):
            return line
    return ""


def _domain_hit(text: str, words) -> bool:
    return any(re.search(rf"\b{re.escape(word)}\b", text) for word in words)


def is_domain_mismatch(text: str, roles) -> bool:
    # Drop the post when its title is a different craft and none of the title's crafts match.
    title = job_title(text).lower()
    if not title:
        return False
    found = [words for words in FOREIGN_DOMAINS.values() if _domain_hit(title, words)]
    if not found:
        return False
    role_blob = " ".join(roles).lower()
    return not any(_domain_hit(role_blob, words) for words in found)


def top_keywords(text: str, limit: int = 3) -> list[str]:
    # Pick up to 3 tools that actually appear, preferring the longer name.
    low = text.lower()
    hits = []
    for keyword in sorted(JD_KEYWORDS, key=len, reverse=True):
        if not re.search(rf"(?<![A-Za-z0-9]){re.escape(keyword)}(?![A-Za-z0-9])", low, re.I):
            continue
        if any(keyword.lower() in prev.lower() or prev.lower() in keyword.lower() for prev in hits):
            continue
        hits.append((low.find(keyword.lower()), keyword))
    hits.sort()
    return [keyword for _, keyword in hits[:limit]]


def hook_sentence(keywords: list[str]) -> str:
    if not keywords:
        return "My background lines up with the work described in your post."
    if len(keywords) == 1:
        listed = keywords[0]
    elif len(keywords) == 2:
        listed = f"{keywords[0]} and {keywords[1]}"
    else:
        listed = f"{', '.join(keywords[:-1])}, and {keywords[-1]}"
    return f"My hands-on experience with {listed} maps directly to what you are looking for."

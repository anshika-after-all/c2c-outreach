"""PDF section 5.1 — search LinkedIn and store recruiter posts."""

import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

import db
from client_config import candidate
from filters import clean_email, emails_in, is_bench_post, is_domain_mismatch, is_usa_job, search_url
from settings import SESSION

CARD_SELECTORS = (
    "div.feed-shared-update-v2",
    "li.reusable-search__result-container",
    "div[data-urn*='activity']",
)
MAX_CARDS = 25
SCROLLS = 6
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def _name_from_profile(url: str) -> str:
    match = re.search(r"/in/([^/?#]+)", url or "")
    if not match:
        return ""
    parts = [part for part in match.group(1).replace("-", " ").split() if not part.isdigit()]
    return " ".join(part.capitalize() for part in parts)


def _post_url(raw: str) -> str:
    # Drop query tracking. The card menu copies a long LinkedIn URL.
    raw = (raw or "").strip()
    if "linkedin.com" not in raw:
        return ""
    parsed = urlparse(raw)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")


class LinkedInSession:
    def __init__(self):
        self._play = None
        self._browser = None
        self.page = None

    def __enter__(self):
        if not SESSION.exists():
            raise FileNotFoundError("No session.json. Use menu option 2 to log in.")
        from playwright.sync_api import sync_playwright
        self._play = sync_playwright().start()
        self._browser = self._play.chromium.launch(headless=True)
        context = self._browser.new_context(
            storage_state=str(SESSION),
            user_agent=USER_AGENT,
            viewport={"width": 1400, "height": 900},
        )
        try:
            context.grant_permissions(["clipboard-read", "clipboard-write"], origin="https://www.linkedin.com")
        except Exception:
            pass
        self.page = context.new_page()
        return self

    def __exit__(self, *_args):
        if self._browser:
            self._browser.close()
        if self._play:
            self._play.stop()

    def scrape(self, key: str, roles) -> dict:
        profile = candidate(key)
        stats = {"saved": 0, "no_email": 0, "filtered": 0, "mismatch": 0}
        rows = []
        for role in roles:
            rows.extend(self._search_role(profile, role, stats))
        stats["saved"] = db.add_recruiters(rows)
        return stats

    def _search_role(self, profile, role, stats):
        page = self.page
        page.goto(
            search_url(role, profile["exclusion_keywords"]),
            wait_until="domcontentloaded",
            timeout=60_000,
        )
        page.wait_for_timeout(2000)
        if any(part in page.url for part in ("login", "checkpoint", "authwall")):
            raise RuntimeError("LinkedIn session expired or needs a security check. Run option 2.")
        for _ in range(SCROLLS):
            page.mouse.wheel(0, 4000)
            page.wait_for_timeout(1000)
            self._click_see_more(page)
        cards = self._cards(page)
        found = []
        own = {profile["email"].lower()}
        role_names = [profile["primary_role"], *profile["search_roles"]]
        for index in range(min(cards.count(), MAX_CARDS)):
            try:
                row = self._read_card(cards.nth(index), role, role_names, own, stats)
                if row:
                    found.append(row)
            except Exception:
                continue
            finally:
                page.keyboard.press("Escape")
        return found

    def _click_see_more(self, page):
        buttons = page.get_by_text(re.compile(r"see more", re.I))
        for index in range(min(buttons.count(), 8)):
            try:
                buttons.nth(index).click(timeout=500)
            except Exception:
                continue

    def _cards(self, page):
        for selector in CARD_SELECTORS:
            cards = page.locator(selector)
            if cards.count():
                return cards
        return page.locator(CARD_SELECTORS[0])

    def _copy_link(self, card) -> str:
        # LinkedIn hides the post URL. The control menu copies it to the clipboard.
        page = self.page
        try:
            page.evaluate("() => navigator.clipboard.writeText('')")
            menu = card.locator("button[aria-label*='control menu for post']")
            if menu.count() == 0:
                menu = card.locator("button[aria-label*='control menu' i]")
            if menu.count() == 0:
                return ""
            menu.first.click(timeout=3000)
            page.get_by_text(re.compile(r"copy link", re.I)).first.click(timeout=3000)
            page.wait_for_timeout(300)
            return _post_url(page.evaluate("() => navigator.clipboard.readText()"))
        except Exception:
            return ""

    def _read_card(self, card, role, roles, own, stats):
        card.scroll_into_view_if_needed(timeout=3000)
        soup = BeautifulSoup(card.inner_html(), "html.parser")
        text = soup.get_text("\n", strip=True)
        emails = []
        for link in soup.select("a[href^='mailto:']"):
            email = clean_email(link.get("href", "")[7:].split("?")[0])
            if email:
                emails.append(email)
        for email in emails_in(text):
            if email not in emails:
                emails.append(email)
        emails = [email for email in emails if email not in own]
        if not emails:
            stats["no_email"] += 1
            return None
        if is_bench_post(text) or not is_usa_job(text):
            stats["filtered"] += 1
            return None
        mismatched = is_domain_mismatch(text, roles)
        if mismatched:
            stats["mismatch"] += 1
        name = ""
        for link in soup.select("a[href*='/in/']"):
            name = _name_from_profile(link.get("href", ""))
            if name:
                break
        return {
            "recruiter_name": name or "Recruiter",
            "recruiter_email": emails[0],
            "role": role,
            "post_url": self._copy_link(card),
            "job_description": text[:20000],
            "email_sent_status": "mismatched_role" if mismatched else "pending",
            "timestamp": db.now(),
        }

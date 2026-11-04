"""PDF section 7.1 — open LinkedIn once and save cookies to session.json."""

from playwright.sync_api import sync_playwright

from settings import SESSION, env


def login():
    # The window stays open so you can finish a CAPTCHA or a 2FA code yourself.
    email = env("LINKEDIN_EMAIL")
    password = env("LINKEDIN_PASSWORD")
    with sync_playwright() as play:
        browser = play.chromium.launch(headless=False)
        page = browser.new_page()
        try:
            page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
            if email:
                page.fill("#username", email)
            if password:
                page.fill("#password", password)
                page.locator("button[type=submit]").click()
            print("Finish any CAPTCHA or 2FA in the browser. Waiting up to 5 minutes for the home feed.")
            page.wait_for_selector("nav.global-nav", timeout=300_000)
            page.context.storage_state(path=str(SESSION))
        finally:
            browser.close()
    print(f"Saved {SESSION.name}")

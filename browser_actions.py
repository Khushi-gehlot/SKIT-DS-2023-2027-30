"""
Playwright-driven browser automation.

This sits alongside actions.py, it does not replace it. The existing
`webbrowser` commands ("open youtube", "search google for X") still just hand a
URL to the default browser and forget about it - fast, zero setup, and right
for what they do.

Playwright is for the things `webbrowser` cannot do: interacting with a page
after it loads. Clicking the first search result, reading text back, filling a
form, waiting for an element to appear.

A single Chromium window is launched on first use and reused for every command
after that, so the user keeps one browser session rather than a new window per
command.

Setup (one time):
    pip install playwright
    python -m playwright install chromium
"""

import threading
import urllib.parse

from core import recognize_speech, speak

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    sync_playwright = None
    PLAYWRIGHT_AVAILABLE = False


class BrowserSession:
    """
    Owns one long-lived Chromium window.

    Launching a browser takes a couple of seconds, so we start it once and keep
    it. The lock matters because the always-on wake-word loop runs on a
    background thread: two commands arriving close together must not try to
    launch two browsers.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._playwright = None
        self._browser = None
        self._page = None

    # --- lifecycle ---

    def _ensure_started(self):
        """Launch the browser if it is not already running. Caller holds the lock."""
        if self._page is not None and not self._page.is_closed():
            return

        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError(
                "Playwright is not installed. Run:\n"
                "    pip install playwright\n"
                "    python -m playwright install chromium"
            )

        # headless=False so the user can actually see what the assistant does.
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=False)
        self._page = self._browser.new_page()
        self._page.set_default_timeout(15000)

    def close(self):
        """Shut the browser down. Safe to call when nothing is running."""
        with self._lock:
            for closer in (
                lambda: self._page and self._page.close(),
                lambda: self._browser and self._browser.close(),
                lambda: self._playwright and self._playwright.stop(),
            ):
                try:
                    closer()
                except Exception:
                    pass
            self._page = self._browser = self._playwright = None

    def is_running(self) -> bool:
        return self._page is not None and not self._page.is_closed()

    # --- navigation ---

    def goto(self, url: str):
        with self._lock:
            self._ensure_started()
            self._page.goto(url)
            return self._page

    def page(self):
        with self._lock:
            self._ensure_started()
            return self._page


# One session for the whole process.
session = BrowserSession()


def _guard(fn):
    """Run a browser action, turning any failure into spoken feedback."""
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except RuntimeError as e:
            print("Browser error:", e)
            speak("Playwright is not set up yet.")
        except Exception as e:
            print(f"Browser error: {type(e).__name__}: {e}")
            speak("Sorry, the browser action failed.")
        return None
    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


# =============== ACTIONS ===============

@_guard
def browser_open(url: str):
    """Open a URL in the controlled browser."""
    if not url.startswith("http"):
        url = "https://" + url
    speak("Opening the browser.")
    session.goto(url)


@_guard
def browser_search_google(query: str):
    """Search Google in the controlled browser."""
    speak(f"Searching Google for {query}")
    session.goto("https://www.google.com/search?q=" + urllib.parse.quote(query))


@_guard
def browser_search_youtube(query: str):
    """Search YouTube in the controlled browser."""
    speak(f"Searching YouTube for {query}")
    session.goto(
        "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query)
    )


@_guard
def browser_play_first_youtube_result(query: str):
    """
    Search YouTube and click the first video.

    This is the thing `webbrowser` cannot do: it needs to wait for results to
    render, then click an element on the page.
    """
    speak(f"Playing the first result for {query}")
    page = session.goto(
        "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query)
    )
    first = page.locator("ytd-video-renderer a#video-title").first
    first.wait_for(state="visible")
    first.click()


@_guard
def browser_page_title() -> str | None:
    """Read the current page title back to the user."""
    title = session.page().title()
    speak(f"The page is titled {title}")
    return title


@_guard
def browser_close():
    """Close the controlled browser."""
    if not session.is_running():
        speak("The browser is not open.")
        return
    speak("Closing the browser.")
    session.close()


# =============== VOICE WRAPPERS ===============
#
# Entries in COMMANDS must be callable with no arguments, so these ask for the
# search term by voice, the same pattern search_google_voice() uses.

def browser_play_youtube_voice():
    """Ask what to play, then play the first YouTube result."""
    speak("What should I play?")
    query = recognize_speech()
    if not query:
        speak("I did not catch that.")
        return
    browser_play_first_youtube_result(query)


def browser_search_google_voice():
    """Ask what to search, then search Google in the controlled browser."""
    speak("What do you want to search?")
    query = recognize_speech()
    if not query:
        speak("I did not catch that.")
        return
    browser_search_google(query)


# Quick manual check:  python browser_actions.py
if __name__ == "__main__":
    if not PLAYWRIGHT_AVAILABLE:
        print("Playwright not installed. Run:")
        print("    pip install playwright")
        print("    python -m playwright install chromium")
        raise SystemExit(1)

    print("Opening example.com ...")
    browser_open("https://example.com")
    print("Title:", browser_page_title())
    input("Press Enter to close the browser...")
    browser_close()

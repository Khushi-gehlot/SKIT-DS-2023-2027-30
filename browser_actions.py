"""
Playwright browser automation.

This sits alongside actions.py, it does not replace it. The `webbrowser`
commands ("open youtube") still hand a URL to the default browser and forget
about it - fast, zero setup, right for what they do.

Playwright is for what `webbrowser` cannot do: acting *inside* a page after it
loads. For an accessibility tool that is the whole game, because the hard part
of using the web without a mouse is not opening a page, it is clicking the
right link, scrolling to the right place and reading content back.

## Threading

Playwright's sync API is thread-affine: objects created on one thread cannot
be touched from another. Streamlit runs every rerun on a *different* script
thread and the always-on wake-word loop has its own, so a plain singleton
would work once and then raise greenlet errors.

Everything therefore runs on one dedicated worker thread. Public functions
submit a callable to that thread and block for the result. It also serialises
commands for free, so two overlapping voice commands cannot interleave
mid-navigation.

Setup (one time):
    pip install playwright
    python -m playwright install chromium
"""

from __future__ import annotations

import queue
import re
import threading
import urllib.parse
from dataclasses import dataclass
from typing import Any, Callable

from core import speak

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on install
    sync_playwright = None
    PlaywrightError = PlaywrightTimeout = Exception
    PLAYWRIGHT_AVAILABLE = False


NAV_TIMEOUT = 20_000      # page loads can be slow on bad connections
ACTION_TIMEOUT = 10_000   # finding and clicking an element should not be
MAX_LINKS = 25            # how many links we will read out at once


class BrowserError(RuntimeError):
    """Something went wrong that the user should be told about, in words."""


@dataclass
class Link:
    index: int
    text: str
    href: str | None


# =============== WORKER THREAD ===============

class _Worker:
    """
    Runs every Playwright call on one thread.

    Callers submit a function and block until it returns. Exceptions are
    carried back across the thread boundary rather than vanishing.
    """

    def __init__(self):
        self._jobs: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._start_lock = threading.Lock()

    def _ensure_thread(self):
        with self._start_lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(
                    target=self._run, name="playwright-worker", daemon=True
                )
                self._thread.start()

    def _run(self):
        while True:
            job, done = self._jobs.get()
            if job is None:          # shutdown sentinel
                done.put((None, None))
                return
            try:
                done.put((job(), None))
            except Exception as e:   # noqa: BLE001 - carried to the caller
                done.put((None, e))

    def submit(self, fn: Callable[[], Any], timeout: float = 60.0) -> Any:
        """Run fn on the worker thread and return its result."""
        self._ensure_thread()
        done: queue.Queue = queue.Queue()
        self._jobs.put((fn, done))
        try:
            result, error = done.get(timeout=timeout)
        except queue.Empty:
            raise BrowserError("The browser stopped responding.") from None
        if error is not None:
            raise error
        return result

    def shutdown(self):
        if self._thread and self._thread.is_alive():
            done: queue.Queue = queue.Queue()
            self._jobs.put((None, done))
            try:
                done.get(timeout=10)
            except queue.Empty:
                pass
        self._thread = None


_worker = _Worker()


# =============== SESSION (worker thread only) ===============

class _Session:
    """
    The browser itself. Every method here runs on the worker thread, so no
    locking is needed inside - the queue already serialises access.
    """

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._page = None

    # --- lifecycle ---

    def _alive(self) -> bool:
        """
        Is the session genuinely usable?

        page.is_closed() alone is not enough: when the browser process dies or
        the user closes the window, the page object can still answer False
        while every call through it raises "Target page, context or browser
        has been closed". Checking the browser connection as well is what
        makes recovery reliable.
        """
        try:
            return (
                self._page is not None
                and self._browser is not None
                and self._browser.is_connected()
                and not self._page.is_closed()
            )
        except Exception:
            return False

    def page(self):
        """The current page, launching or recovering the browser as needed."""
        if not PLAYWRIGHT_AVAILABLE:
            raise BrowserError(
                "Playwright is not installed. Run: pip install playwright "
                "and python -m playwright install chromium"
            )

        # The user may have closed the window, or the browser may have
        # crashed. Either way, rebuild rather than failing.
        if self._alive():
            return self._page

        self._teardown()
        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=False)
            context = self._browser.new_context()
            self._page = context.new_page()
            self._page.set_default_timeout(ACTION_TIMEOUT)
            self._page.set_default_navigation_timeout(NAV_TIMEOUT)
        except Exception as e:
            self._teardown()
            raise BrowserError(
                "Could not start the browser. If this is the first run, "
                "run: python -m playwright install chromium"
            ) from e
        return self._page

    def _teardown(self):
        for close in (
            lambda: self._page and self._page.close(),
            lambda: self._browser and self._browser.close(),
            lambda: self._playwright and self._playwright.stop(),
        ):
            try:
                close()
            except Exception:
                pass
        self._page = self._browser = self._playwright = None

    def is_running(self) -> bool:
        return self._alive()

    def close(self):
        self._teardown()

    # --- navigation ---

    def goto(self, url: str) -> str:
        page = self.page()
        try:
            page.goto(url, wait_until="domcontentloaded")
        except PlaywrightTimeout:
            # The page may still be usable even if some asset hung.
            raise BrowserError(f"{url} took too long to load.") from None
        except PlaywrightError as e:
            if "ERR_NAME_NOT_RESOLVED" in str(e):
                raise BrowserError(f"I could not find {url}.") from None
            if "ERR_INTERNET_DISCONNECTED" in str(e):
                raise BrowserError("There is no internet connection.") from None
            raise BrowserError(f"Could not open {url}.") from None
        return page.title() or url

    def back(self) -> str:
        page = self.page()
        if page.go_back(wait_until="domcontentloaded") is None:
            raise BrowserError("There is nothing to go back to.")
        return page.title()

    def forward(self) -> str:
        page = self.page()
        if page.go_forward(wait_until="domcontentloaded") is None:
            raise BrowserError("There is nothing to go forward to.")
        return page.title()

    def reload(self) -> str:
        page = self.page()
        page.reload(wait_until="domcontentloaded")
        return page.title()

    # --- scrolling ---

    def scroll(self, direction: str) -> str:
        page = self.page()
        # Scrolling the page itself, not the OS - unlike the PyAutoGUI
        # version this works regardless of which window has focus.
        if direction == "down":
            page.mouse.wheel(0, 600)
        elif direction == "up":
            page.mouse.wheel(0, -600)
        elif direction == "top":
            page.keyboard.press("Home")
        elif direction == "bottom":
            page.keyboard.press("End")
        else:
            raise BrowserError(f"I do not know how to scroll {direction}.")
        return direction

    # --- links ---

    def links(self, limit: int = MAX_LINKS) -> list[Link]:
        """Visible links with usable text, in page order."""
        page = self.page()
        found: list[Link] = []
        seen: set[str] = set()

        try:
            elements = page.locator("a:visible").all()
        except Exception:
            raise BrowserError(
                "The browser page is not available. Open a page first."
            ) from None

        for element in elements:
            if len(found) >= limit:
                break
            try:
                text = (element.inner_text(timeout=1000) or "").strip()
                text = re.sub(r"\s+", " ", text)
                if not text or len(text) > 120:
                    continue
                key = text.lower()
                if key in seen:
                    continue
                seen.add(key)
                found.append(Link(len(found) + 1, text, element.get_attribute("href")))
            except Exception:
                # Elements go stale as pages re-render; skip and continue.
                continue
        return found

    def click_by_text(self, wanted: str) -> str:
        """
        Click the link whose text best matches what was said.

        Matching is deliberately forgiving. Speech-to-text mangles link text,
        and a user who cannot point at the screen should not have to say a
        label character-perfect.
        """
        page = self.page()
        wanted_clean = _normalise(wanted)
        if not wanted_clean:
            raise BrowserError("I did not catch which link to click.")

        candidates = self.links(limit=200)
        if not candidates:
            raise BrowserError("I cannot find any links on this page.")

        best = _best_match(wanted_clean, candidates)
        if best is None:
            raise BrowserError(f"I could not find a link called {wanted}.")

        return self._click_link(best)

    def click_by_index(self, index: int) -> str:
        candidates = self.links()
        if not candidates:
            raise BrowserError("I cannot find any links on this page.")
        if index < 1 or index > len(candidates):
            raise BrowserError(
                f"There is no link number {index}. I can see {len(candidates)}."
            )
        return self._click_link(candidates[index - 1])

    def _click_link(self, link: Link) -> str:
        """Click a link, coping with new tabs, overlays and navigation."""
        page = self.page()
        locator = page.locator("a:visible").filter(has_text=re.compile(
            re.escape(link.text), re.IGNORECASE)).first

        try:
            locator.scroll_into_view_if_needed(timeout=3000)
        except Exception:
            pass  # not fatal; the click may still land

        # A link may open a new tab. Watch for one so we can follow it.
        context = page.context
        before = set(context.pages)

        try:
            locator.click(timeout=ACTION_TIMEOUT)
        except PlaywrightTimeout:
            # Usually a cookie banner or sticky header covering the element.
            try:
                locator.click(timeout=3000, force=True)
            except Exception:
                raise BrowserError(
                    f"I found '{link.text}' but could not click it. "
                    "Something may be covering it."
                ) from None
        except PlaywrightError:
            raise BrowserError(f"I could not click '{link.text}'.") from None

        # Follow a popup if one appeared.
        page.wait_for_timeout(500)
        new_pages = set(context.pages) - before
        if new_pages:
            self._page = new_pages.pop()
            self._page.set_default_timeout(ACTION_TIMEOUT)
            self._page.set_default_navigation_timeout(NAV_TIMEOUT)

        try:
            self._page.wait_for_load_state("domcontentloaded", timeout=NAV_TIMEOUT)
        except PlaywrightTimeout:
            pass  # clicked fine, the page is just slow

        return link.text

    # --- typing ---

    def _find_field(self, hint: str | None):
        """
        Locate the input the user means.

        Tried from most specific to least: the label or placeholder they
        named, then a search box, then the first visible text input. The
        fallback matters - on most pages there is exactly one obvious field,
        and making the user describe it precisely defeats the point.
        """
        page = self.page()
        attempts = []

        if hint:
            attempts += [
                lambda: page.get_by_label(hint, exact=False),
                lambda: page.get_by_placeholder(hint, exact=False),
                lambda: page.locator(f'[aria-label*="{hint}" i]'),
                lambda: page.locator(f'[name*="{hint}" i]'),
            ]

        attempts += [
            lambda: page.get_by_role("searchbox"),
            lambda: page.locator('input[type="search"]:visible'),
            lambda: page.locator('textarea:visible'),
            lambda: page.locator(
                'input[type="text"]:visible, input:not([type]):visible, '
                'input[type="email"]:visible, input[type="url"]:visible'
            ),
        ]

        for build in attempts:
            try:
                locator = build().first
                if locator.count() > 0 and locator.is_visible(timeout=1500):
                    return locator
            except Exception:
                continue
        return None

    def type_into(self, value: str, hint: str | None = None, submit: bool = False) -> str:
        page = self.page()
        field = self._find_field(hint)
        if field is None:
            raise BrowserError(
                f"I could not find a {hint or 'text'} box on this page."
            )

        try:
            field.scroll_into_view_if_needed(timeout=3000)
        except Exception:
            pass

        try:
            field.click(timeout=ACTION_TIMEOUT)
            field.fill("")          # clear anything already there
            field.fill(value)
        except PlaywrightTimeout:
            raise BrowserError("I found the box but could not type into it.") from None
        except PlaywrightError as e:
            raise BrowserError(f"I could not type into that box.") from None

        if submit:
            try:
                field.press("Enter")
                page.wait_for_load_state("domcontentloaded", timeout=NAV_TIMEOUT)
            except PlaywrightTimeout:
                pass  # submitted, page just slow
        return value

    def press_key(self, key: str) -> str:
        page = self.page()
        try:
            page.keyboard.press(key)
            page.wait_for_load_state("domcontentloaded", timeout=5000)
        except PlaywrightTimeout:
            pass
        except PlaywrightError:
            raise BrowserError(f"I could not press {key}.") from None
        return key

    # --- reading ---

    def read(self, limit: int = 1500) -> str:
        page = self.page()
        for selector in ("main", "article", "body"):
            try:
                text = page.inner_text(selector, timeout=2000)
                if text and text.strip():
                    return re.sub(r"\n{2,}", "\n", text.strip())[:limit]
            except Exception:
                continue
        raise BrowserError("There is nothing I can read on this page.")

    def title(self) -> str:
        return self.page().title() or "untitled"


_session = _Session()


# =============== MATCHING HELPERS ===============

def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


def _best_match(wanted: str, candidates: list[Link]) -> Link | None:
    """
    Pick the link that best matches spoken text.

    Tried in order: exact, prefix, substring, then word overlap. Word overlap
    is what rescues "click the contact us link" against a link reading
    "Contact Us Today".
    """
    scored = [(link, _normalise(link.text)) for link in candidates]

    for link, text in scored:
        if text == wanted:
            return link
    for link, text in scored:
        if text.startswith(wanted) or wanted.startswith(text):
            return link
    for link, text in scored:
        if wanted in text or text in wanted:
            return link

    wanted_words = set(wanted.split())
    if not wanted_words:
        return None

    best, best_score = None, 0.0
    for link, text in scored:
        words = set(text.split())
        if not words:
            continue
        overlap = len(wanted_words & words) / len(wanted_words)
        if overlap > best_score:
            best, best_score = link, overlap

    # Below half the words in common it is more likely a wrong click than a
    # right one, and a wrong click is worse than asking again.
    return best if best_score >= 0.5 else None


# Checked in order of how unambiguous each form is. Cardinals come last
# because "one" also appears in phrases like "the 3rd one", where treating it
# as the number would pick the wrong link.
_ORDINAL_WORDS = {
    "first": 1, "1st": 1,
    "second": 2, "2nd": 2,
    "third": 3, "3rd": 3,
    "fourth": 4, "4th": 4,
    "fifth": 5, "5th": 5,
    "sixth": 6, "6th": 6,
    "seventh": 7, "7th": 7,
    "eighth": 8, "8th": 8,
    "ninth": 9, "9th": 9,
    "tenth": 10, "10th": 10,
    "last": -1,
}

_CARDINAL_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

# Kept for callers that want the full mapping.
ORDINALS = {**_CARDINAL_WORDS, **_ORDINAL_WORDS}


def parse_ordinal(text: str) -> int | None:
    """
    "the second link" -> 2, "link number 3" -> 3, "the last one" -> -1.

    Returns None when no position is present. Order of checks matters:
    digits beat ordinal words beat cardinal words, so "the 3rd one" is 3 and
    not 1.
    """
    lowered = text.lower()

    digits = re.search(r"\b(\d{1,2})\b", lowered)
    if digits:
        return int(digits.group(1))

    for word, number in _ORDINAL_WORDS.items():
        if re.search(rf"\b{word}\b", lowered):
            return number

    for word, number in _CARDINAL_WORDS.items():
        if re.search(rf"\b{word}\b", lowered):
            return number

    return None


def normalise_url(raw: str) -> str:
    """
    Turn spoken text into a usable URL.

    Speech gives "github dot com" and "w w w dot example dot org"; both have
    to become something a browser will accept.
    """
    url = raw.strip().lower()
    url = re.sub(r"\s+dot\s+", ".", url)
    url = re.sub(r"\bw\s*w\s*w\b", "www", url)
    url = url.replace(" slash ", "/").replace(" ", "")
    if not url:
        raise BrowserError("I did not catch the address.")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


# =============== PUBLIC ACTIONS ===============
#
# Each submits to the worker thread and reports back in speech. They raise
# BrowserError with a sentence the assistant can say; executor.py turns that
# into a failed ExecutionResult.

def browser_open(url: str) -> str:
    target = normalise_url(url)
    speak(f"Opening {target.replace('https://', '')}")
    title = _worker.submit(lambda: _session.goto(target))
    return title


def browser_click_link(text: str) -> str:
    speak(f"Looking for {text}")
    clicked = _worker.submit(lambda: _session.click_by_text(text))
    speak(f"Opened {clicked}")
    return clicked


def browser_click_index(index: int) -> str:
    if index == -1:
        links = _worker.submit(lambda: _session.links())
        if not links:
            raise BrowserError("I cannot find any links on this page.")
        index = len(links)
    clicked = _worker.submit(lambda: _session.click_by_index(index))
    speak(f"Opened {clicked}")
    return clicked


def browser_type(value: str, field: str | None = None, submit: bool = False) -> str:
    """Type into a field on the page, optionally pressing Enter afterwards."""
    where = f" in the {field} box" if field else ""
    speak(f"Typing {value}{where}")
    typed = _worker.submit(lambda: _session.type_into(value, field, submit))
    return typed


def browser_press_enter() -> str:
    _worker.submit(lambda: _session.press_key("Enter"))
    speak("Submitted.")
    return "Enter"


def browser_back() -> str:
    title = _worker.submit(lambda: _session.back())
    speak(f"Back to {title}")
    return title


def browser_forward() -> str:
    title = _worker.submit(lambda: _session.forward())
    speak(f"Forward to {title}")
    return title


def browser_reload() -> str:
    title = _worker.submit(lambda: _session.reload())
    speak("Reloaded.")
    return title


def browser_scroll(direction: str) -> str:
    _worker.submit(lambda: _session.scroll(direction))
    return direction


def browser_list_links(limit: int = 10) -> list[Link]:
    """
    Read out numbered links so the user can pick one by number.

    This matters more than clicking by name: speech-to-text mangles link
    text, but "number three" is unambiguous.
    """
    links = _worker.submit(lambda: _session.links())
    if not links:
        raise BrowserError("I cannot find any links on this page.")
    shown = links[:limit]
    spoken = ". ".join(f"{link.index}, {link.text}" for link in shown)
    speak(f"I can see {len(links)} links. The first {len(shown)} are: {spoken}")
    return shown


def browser_read_page() -> str:
    text = _worker.submit(lambda: _session.read())
    speak(text[:600])
    return text


def browser_page_title() -> str:
    title = _worker.submit(lambda: _session.title())
    speak(f"The page is titled {title}")
    return title


def browser_close() -> str:
    if not _worker.submit(lambda: _session.is_running()):
        speak("The browser is not open.")
        return "already closed"
    speak("Closing the browser.")
    _worker.submit(lambda: _session.close())
    return "closed"


def browser_is_running() -> bool:
    try:
        return bool(_worker.submit(lambda: _session.is_running(), timeout=5))
    except Exception:
        return False


def browser_search(engine: str, query: str) -> str:
    """Search inside the controlled browser, so results can be acted on."""
    urls = {
        "google": "https://www.google.com/search?q=",
        "youtube": "https://www.youtube.com/results?search_query=",
    }
    base = urls.get(engine, urls["google"])
    speak(f"Searching {engine} for {query}")
    return _worker.submit(lambda: _session.goto(base + urllib.parse.quote(query)))


# Quick manual check:  python browser_actions.py
if __name__ == "__main__":
    if not PLAYWRIGHT_AVAILABLE:
        raise SystemExit(
            "Playwright not installed.\n"
            "  pip install playwright\n"
            "  python -m playwright install chromium"
        )

    browser_open("example.com")
    print("title:", browser_page_title())
    print("links:", [(l.index, l.text) for l in browser_list_links()])
    input("Press Enter to close...")
    browser_close()

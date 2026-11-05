"""
Intent execution: Intent in, ExecutionResult out.

This is the only module that knows how an intent is actually carried out.
The NLU layer never imports actions.py, which is what lets the matcher be
replaced by an LLM without touching anything that touches the operating
system.

Dispatch is a registry keyed by action name, not a chain of if-statements.
Registering a handler is one decorator, so a new capability - a plugin, a
Playwright command - plugs in without editing the dispatcher:

    @handler("open_app")
    def _open_app(intent): ...

Handlers return an ExecutionResult and never raise; execute() enforces that
anyway, because a crash in one action must not take down an always-on loop
the user cannot reach the keyboard to restart.
"""

from __future__ import annotations

from typing import Callable

import actions
import app_launcher
import browser_actions
from core import speak
from intent import ExecutionResult, Intent

# action name -> handler
HANDLERS: dict[str, Callable[[Intent], ExecutionResult]] = {}


def handler(action: str):
    """Register a function as the handler for an action."""
    def register(fn):
        HANDLERS[action] = fn
        return fn
    return register


def _result(intent: Intent, ok: bool, what: str) -> ExecutionResult:
    return (
        ExecutionResult.ok(f"Executed: {what}", intent)
        if ok
        else ExecutionResult.fail(f"Don't know how to {what}", intent)
    )


# =============== HANDLERS ===============
#
# Each maps a target to the function in actions.py that does the work. The
# lookup tables keep the mapping declarative and make the valid targets for
# each action obvious at a glance.

_APPS = {
    "notepad": actions.open_notepad,
    "calculator": actions.open_calculator,
    "command_prompt": actions.open_cmd,
    "file_explorer": actions.open_file_explorer,
    "control_panel": actions.open_control_panel,
    "task_manager": actions.open_task_manager,
}

_FOLDERS = {
    "downloads": actions.open_downloads_folder,
    "documents": actions.open_documents_folder,
    "desktop": actions.open_desktop_folder,
    "videos": actions.open_videos_folder,
    "pictures": actions.open_pictures_folder,
    "music": actions.open_music_folder,
    "this_pc": actions.open_this_pc,
}

_WEBSITES = {
    "youtube": actions.open_youtube,
    "google": actions.open_google,
}

_CURSOR_MOVES = {
    "up": actions.move_cursor_up,
    "down": actions.move_cursor_down,
    "left": actions.move_cursor_left,
    "right": actions.move_cursor_right,
}

_CLICKS = {
    "left": actions.click_cursor,
    "double": actions.double_click_cursor,
    "right": actions.right_click_cursor,
}

_SCROLLS = {"up": actions.scroll_up, "down": actions.scroll_down}

_WINDOWS = {
    "show_desktop": actions.show_desktop,
    "minimize": actions.minimize_window,
    "maximize": actions.maximize_window,
    "close": actions.close_window,
    "switch": actions.switch_window,
}

_VOLUME = {
    "up": actions.volume_up,
    "down": actions.volume_down,
    "mute": actions.mute_volume,
    "unmute": actions.unmute_volume,
}

_MEDIA = {
    "play_pause": actions.media_play_pause,
    "next": actions.media_next,
    "previous": actions.media_previous,
}

_POWER = {
    "shutdown": actions.shutdown_system,
    "restart": actions.restart_system,
    "lock": actions.lock_system,
    "sleep": actions.sleep_system,
}


def _simple(action: str, table: dict, noun: str):
    """Register a handler that just looks the target up in a table."""
    @handler(action)
    def run(intent: Intent, _table=table, _noun=noun) -> ExecutionResult:
        fn = _table.get(intent.target)
        if fn is None:
            return ExecutionResult.fail(f"Unknown {_noun}: {intent.target}", intent)
        fn()
        return ExecutionResult.ok(f"{_noun.capitalize()}: {intent.target}", intent)
    return run


_simple("open_app", _APPS, "application")
_simple("open_folder", _FOLDERS, "folder")
_simple("cursor_move", _CURSOR_MOVES, "cursor move")
_simple("cursor_click", _CLICKS, "click")
_simple("scroll", _SCROLLS, "scroll")
_simple("window", _WINDOWS, "window action")
_simple("volume", _VOLUME, "volume action")
_simple("media", _MEDIA, "media action")
_simple("power", _POWER, "power action")


@handler("open_website")
def _open_website(intent: Intent) -> ExecutionResult:
    """
    Open a site.

    Two shapes arrive here: a known shortcut ("open youtube"), and a spoken
    URL ("open website github.com") where target is "url" and the address is
    in params. The second is why this is not a plain lookup table.
    """
    if intent.target == "url":
        url = intent.params.get("query")
        if not url:
            url = actions.ask_for_query("Which website should I open?")
        if not url:
            return ExecutionResult.fail("No website given.", intent)
        # Speech gives "github dot com"; make it a usable host.
        url = url.replace(" dot ", ".").replace(" ", "")
        actions.open_url(url)
        return ExecutionResult.ok(f"Opened {url}", intent, data=url)

    known = {"youtube": "https://www.youtube.com", "google": "https://www.google.com"}
    url = known.get(intent.target)
    if url is None:
        return ExecutionResult.fail(f"Unknown website: {intent.target}", intent)

    if _ensure_controlled_browser():
        return _browser(
            lambda: browser_actions.browser_open(url), intent, f"Opened {intent.target}"
        )

    _WEBSITES[intent.target]()
    return ExecutionResult.ok(f"Opened {intent.target}", intent)


@handler("open_settings")
def _open_settings(intent: Intent) -> ExecutionResult:
    """Windows Settings pages are URIs, so one handler covers all of them."""
    page = "" if intent.target in (None, "home") else intent.target
    actions.open_settings_page(page)
    return ExecutionResult.ok(f"Opened settings: {intent.target}", intent)


def _ensure_controlled_browser() -> bool:
    """
    Make sure a browser the assistant can see into is running.

    Without this the system is split in two: `webbrowser.open` hands the page
    to whatever browser Windows prefers, which the assistant cannot read,
    while "click the first link" looks at a Playwright browser that is still
    blank. Routing every web action through one controlled browser is what
    makes "search for X" then "open the first result" work as a sequence -
    which is the whole point for someone navigating without a mouse.
    """
    try:
        if browser_actions.browser_is_running():
            return True
        browser_actions.launch_debuggable_browser()
        browser_actions.browser_attach()
        return True
    except Exception as e:
        print(f"Could not start a controlled browser ({type(e).__name__}: {e});"
              " falling back to the default one.")
        return False


@handler("search_web")
def _search_web(intent: Intent) -> ExecutionResult:
    query = intent.params.get("query")
    engine = intent.target or "google"

    if not query:
        # No query in the utterance - ask for it.
        query = actions.ask_for_query(f"What do you want to search on {engine}?")
        if not query:
            return ExecutionResult.fail("No search term given.", intent)

    if _ensure_controlled_browser():
        return _browser(
            lambda: browser_actions.browser_search(engine, query),
            intent, f"Searched {engine} for {query}",
        )

    actions.search_web(engine, query)
    return ExecutionResult.ok(f"Searched {engine} for {query}", intent)


@handler("screenshot")
def _screenshot(intent: Intent) -> ExecutionResult:
    path = actions.take_screenshot()
    return ExecutionResult.ok("Screenshot saved.", intent, data=path)


@handler("battery")
def _battery(intent: Intent) -> ExecutionResult:
    percent = actions.show_battery()
    return ExecutionResult.ok(f"Battery at {percent}%", intent, data=percent)


@handler("send_email")
def _send_email(intent: Intent) -> ExecutionResult:
    actions.send_email_voice()
    return ExecutionResult.ok("Email flow finished.", intent)


# =============== BROWSER (Playwright) ===============
#
# These drive a browser the assistant controls, as opposed to the open_website
# action which just hands a URL to the default browser. Every browser_actions
# function raises BrowserError with a sentence meant to be spoken, so one
# wrapper converts that into a failed result.

def _browser(fn, intent: Intent, success: str) -> ExecutionResult:
    """Run a browser action, turning BrowserError into a spoken failure."""
    try:
        value = fn()
    except browser_actions.BrowserError as e:
        # Expected, explainable failure - say it rather than logging a trace.
        speak(str(e))
        return ExecutionResult.fail(str(e), intent)
    except Exception as e:
        print(f"Browser error: {type(e).__name__}: {e}")
        speak("Sorry, the browser action failed.")
        return ExecutionResult.fail(f"Browser error: {e}", intent)
    return ExecutionResult.ok(success.format(value=value), intent, data=value)


@handler("open_installed_app")
def _open_installed_app(intent: Intent) -> ExecutionResult:
    """
    Open any application on this PC, not just a hard-coded handful.

    When several apps match closely nothing is launched - the candidates come
    back so the user can choose, which is far better than guessing wrong for
    someone who cannot easily close the wrong window.
    """
    name = intent.params.get("app") or intent.target
    if not name:
        name = actions.ask_for_query("Which app should I open?")
    if not name:
        return ExecutionResult.fail("No app named.", intent)

    launched, message, candidates = app_launcher.launch(name)
    if launched:
        speak(message)
        return ExecutionResult.ok(message, intent)

    if candidates:
        options = ", ".join(
            f"{n}, {c['name']}" for n, c in enumerate(candidates, 1)
        )
        question = f"I found a few. Which one: {options}?"
        speak(question)
        return ExecutionResult.fail(question, intent, )

    speak(message)
    return ExecutionResult.fail(message, intent)


@handler("browser_launch")
def _browser_launch(intent: Intent) -> ExecutionResult:
    """Start a browser the assistant is able to see into, then attach."""
    try:
        name = browser_actions.launch_debuggable_browser()
        browser_actions.browser_attach()
        return ExecutionResult.ok(f"Started {name} and connected to it.", intent)
    except browser_actions.BrowserError as e:
        speak(str(e))
        return ExecutionResult.fail(str(e), intent)


@handler("browser_attach")
def _browser_attach(intent: Intent) -> ExecutionResult:
    return _browser(
        lambda: browser_actions.browser_attach(), intent, "Looking at {value}"
    )


@handler("browser_open")
def _browser_open(intent: Intent) -> ExecutionResult:
    url = intent.params.get("query")
    if not url:
        url = actions.ask_for_query("Which website should I open?")
    if not url:
        return ExecutionResult.fail("No website given.", intent)
    _ensure_controlled_browser()
    return _browser(lambda: browser_actions.browser_open(url), intent, "Opened {value}")


@handler("browser_click")
def _browser_click(intent: Intent) -> ExecutionResult:
    """Click a link by position ("the second link") or by name."""
    _ensure_controlled_browser()
    if intent.target == "text":
        label = intent.params.get("text")
        if not label:
            return ExecutionResult.fail("No link name given.", intent)
        return _browser(
            lambda: browser_actions.browser_click_link(label), intent, "Clicked {value}"
        )

    ordinal = intent.params.get("ordinal")
    if ordinal is None:
        # "click link" with no position - list them so the user can choose by
        # number, which is far more reliable than naming a link aloud.
        return _browser(
            lambda: browser_actions.browser_list_links(), intent,
            "Listed links - say the number you want."
        )

    index = browser_actions.parse_ordinal(str(ordinal))
    if index is None:
        return ExecutionResult.fail(f"I did not understand '{ordinal}'.", intent)
    return _browser(
        lambda: browser_actions.browser_click_index(index), intent, "Clicked {value}"
    )


@handler("browser_type")
def _browser_type(intent: Intent) -> ExecutionResult:
    """
    Type into a text field, wherever the user happens to be.

    Two routes, chosen by what is in front of the user. On a web page the
    browser layer can find the field by its label, which is far more
    reliable than hoping the caret is in the right place. Everywhere else -
    Notepad, a WhatsApp message box, a spreadsheet cell - there is no such
    structure to query, so the text goes to whatever has keyboard focus.
    """
    value = intent.params.get("value")
    if not value:
        value = actions.ask_for_query("What should I type?")
    if not value:
        return ExecutionResult.fail("Nothing to type.", intent)

    field = intent.params.get("field")
    submit = bool(intent.params.get("submit"))
    newline = bool(intent.params.get("newline"))

    title = actions.active_window_title()

    # The browser route only applies when the browser is both under our
    # control and actually in front. Typing into a background page the user
    # cannot see would look like the command silently failed.
    if (
        not newline
        and browser_actions.browser_is_running()
        and actions._looks_like_browser(title)
    ):
        return _browser(
            lambda: browser_actions.browser_type(value, field, submit),
            intent, "Typed {value}",
        )

    if actions.type_text(value, submit=submit, newline=newline):
        return ExecutionResult.ok(f"Typed: {value}", intent, data=value)
    return ExecutionResult.fail("I could not type that.", intent)


@handler("type_clear")
def _type_clear(intent: Intent) -> ExecutionResult:
    """Empty the focused field, for correcting a misrecognised dictation."""
    if actions.clear_field():
        return ExecutionResult.ok("Cleared the field.", intent)
    return ExecutionResult.fail("I could not clear that.", intent)


@handler("browser_submit")
def _browser_submit(intent: Intent) -> ExecutionResult:
    return _browser(
        lambda: browser_actions.browser_press_enter(), intent, "Pressed Enter."
    )


@handler("close_app")
def _close_app(intent: Intent) -> ExecutionResult:
    """
    Close a window the user named, rather than the one in front.

    "close window" remains Alt+F4 on the focused window, which is what the
    user means when they do not name one. Naming one has to reach that
    window without the user bringing it to the front first, since bringing
    it to the front is exactly what they cannot do.
    """
    name = intent.params.get("app") or intent.target
    if not name:
        return ExecutionResult.fail("Say which window to close.", intent)

    if actions.close_named_window(name):
        return ExecutionResult.ok(f"Closed {name}.", intent)
    return ExecutionResult.fail(f"Did not close {name}.", intent)


@handler("list_windows")
def _list_windows(intent: Intent) -> ExecutionResult:
    """Read out what is open, so one can be named."""
    titles = actions.say_open_windows()
    return ExecutionResult.ok(f"{len(titles)} windows open.", intent, data=titles)


@handler("browser_fields")
def _browser_fields(intent: Intent) -> ExecutionResult:
    """
    Read out what can be filled in on this page.

    The form equivalent of listing links, and the step that has to come
    first: someone who cannot see the screen has no way of knowing a form
    is there, or what it is asking for.
    """
    _ensure_controlled_browser()
    return _browser(
        lambda: browser_actions.browser_describe_fields(),
        intent, "{value}",
    )


@handler("browser_fill")
def _browser_fill(intent: Intent) -> ExecutionResult:
    """Fill a numbered field: "fill field two with John"."""
    _ensure_controlled_browser()

    index = intent.params.get("index")
    try:
        index = int(index)
    except (TypeError, ValueError):
        return ExecutionResult.fail(
            "Say which field, for example 'fill field two with John'.", intent
        )

    value = intent.params.get("value")
    if not value:
        value = actions.ask_for_query(f"What should I put in field {index}?")
    if not value:
        return ExecutionResult.fail("Nothing to fill in.", intent)

    return _browser(
        lambda: browser_actions.browser_fill_field(index, value),
        intent, "{value}",
    )


@handler("browser_button")
def _browser_button(intent: Intent) -> ExecutionResult:
    """Press a button by name, or the form's submit button."""
    _ensure_controlled_browser()
    name = intent.params.get("button") or intent.target
    return _browser(
        lambda: browser_actions.browser_submit_form(name),
        intent, "Pressed {value}",
    )


@handler("browser_nav")
def _browser_nav(intent: Intent) -> ExecutionResult:
    moves = {
        "back": browser_actions.browser_back,
        "forward": browser_actions.browser_forward,
        "reload": browser_actions.browser_reload,
    }
    fn = moves.get(intent.target)
    if fn is None:
        return ExecutionResult.fail(f"Unknown navigation: {intent.target}", intent)
    return _browser(fn, intent, "Now on {value}")


@handler("browser_scroll")
def _browser_scroll(intent: Intent) -> ExecutionResult:
    _ensure_controlled_browser()
    return _browser(
        lambda: browser_actions.browser_scroll(intent.target or "down"),
        intent, "Scrolled {value}",
    )


@handler("browser_links")
def _browser_links(intent: Intent) -> ExecutionResult:
    _ensure_controlled_browser()
    return _browser(
        lambda: browser_actions.browser_list_links(), intent, "Links read out."
    )


@handler("browser_read")
def _browser_read(intent: Intent) -> ExecutionResult:
    _ensure_controlled_browser()
    return _browser(lambda: browser_actions.browser_read_page(), intent, "Page read.")


@handler("browser_title")
def _browser_title(intent: Intent) -> ExecutionResult:
    return _browser(lambda: browser_actions.browser_page_title(), intent, "{value}")


@handler("browser_close")
def _browser_close(intent: Intent) -> ExecutionResult:
    return _browser(lambda: browser_actions.browser_close(), intent, "Browser {value}.")


# =============== SPEAKER VERIFICATION ===============

@handler("enrol_voice")
def _enrol_voice(intent: Intent) -> ExecutionResult:
    ok = actions.enrol_voice()
    return (
        ExecutionResult.ok("Voice enrolled.", intent)
        if ok else ExecutionResult.fail("Enrolment did not complete.", intent)
    )


@handler("forget_voice")
def _forget_voice(intent: Intent) -> ExecutionResult:
    actions.forget_voice()
    return ExecutionResult.ok("Voiceprint removed.", intent)


@handler("check_voice")
def _check_voice(intent: Intent) -> ExecutionResult:
    score = actions.check_voice()
    return ExecutionResult.ok(
        f"Voice match: {score:.0%}" if score is not None else "Could not check.",
        intent, data=score,
    )


@handler("voice_status")
def _voice_status(intent: Intent) -> ExecutionResult:
    actions.voice_status()
    return ExecutionResult.ok("Reported voice status.", intent)


# =============== ENTRY POINT ===============

def execute(intent: Intent) -> ExecutionResult:
    """
    Carry out an intent.

    Never raises. Any failure - unknown action, missing handler, an exception
    inside an action - comes back as a failed ExecutionResult, because the
    always-on loop must survive whatever happens here.
    """
    if not intent.is_understood():
        return ExecutionResult.fail(
            f"I did not understand: {intent.raw_text}", intent
        )

    fn = HANDLERS.get(intent.action)
    if fn is None:
        return ExecutionResult.fail(
            f"No handler registered for action '{intent.action}'", intent
        )

    try:
        return fn(intent)
    except Exception as e:
        print(f"Execution error in '{intent.action}': {type(e).__name__}: {e}")
        return ExecutionResult.fail(
            f"Error while running {intent.action}: {e}", intent
        )


def registered_actions() -> list[str]:
    """Actions the executor can currently carry out."""
    return sorted(HANDLERS)

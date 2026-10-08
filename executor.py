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

    fn = _WEBSITES.get(intent.target)
    if fn is None:
        return ExecutionResult.fail(f"Unknown website: {intent.target}", intent)
    fn()
    return ExecutionResult.ok(f"Opened {intent.target}", intent)


@handler("open_settings")
def _open_settings(intent: Intent) -> ExecutionResult:
    """Windows Settings pages are URIs, so one handler covers all of them."""
    page = "" if intent.target in (None, "home") else intent.target
    actions.open_settings_page(page)
    return ExecutionResult.ok(f"Opened settings: {intent.target}", intent)


@handler("search_web")
def _search_web(intent: Intent) -> ExecutionResult:
    query = intent.params.get("query")
    engine = intent.target or "google"

    if not query:
        # No query in the utterance - ask for it.
        query = actions.ask_for_query(f"What do you want to search on {engine}?")
        if not query:
            return ExecutionResult.fail("No search term given.", intent)

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

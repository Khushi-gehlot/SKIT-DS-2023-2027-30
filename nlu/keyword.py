"""
Keyword intent engine.

The original matcher, rewritten to return Intent objects instead of calling
functions. It is deterministic, instant and works offline, which is exactly
what makes it the right fallback for when the LLM engine is unavailable or
unsure.

Matching happens in three stages:

1. Prefix commands that carry an argument - "search google for cats" - where
   the query is part of the utterance.
2. Exact dictionary lookup. O(1), handles clean input.
3. Substring scan, longest phrase first.

Stage 3's ordering is not cosmetic. Scanning in dictionary order meant
"settings" matched before all thirty specific settings commands and "click"
before "double click" - sixty of the hundred and fifty-nine commands were
unreachable. Sorting candidates by descending length fixes every one of them.
"""

from __future__ import annotations

import re

import config
from command_map import COMMANDS, phrases
from intent import Intent

ENGINE = "keyword"

# Prefix -> (action, target). The rest of the utterance becomes the query.
_QUERY_PREFIXES = {
    "search google for": ("search_web", "google"),
    "google search for": ("search_web", "google"),
    "search youtube for": ("search_web", "youtube"),
    "youtube search for": ("search_web", "youtube"),
    "search for": ("search_web", "google"),
    "open website": ("open_website", "url"),
    "go to website": ("open_website", "url"),
}

# Longest first, so "search google for" wins over "search for".
_PREFIXES_BY_LENGTH = sorted(_QUERY_PREFIXES, key=len, reverse=True)


# --- browser commands carrying an argument ---
#
# These cannot live in command_map because the interesting part is what the
# user said *after* the phrase: a URL, a link name, or a position.

_ORDINAL_WORDS = (
    r"first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|last"
    r"|1st|2nd|3rd|4th|5th|6th|7th|8th|9th|10th|\d{1,2}"
)

# "click the second link", "open link number three", "click the last link"
# The words people actually use. "turn on the first link" and "tap the third
# result" mean the same thing as "click"; refusing them because the verb is
# unusual is the kind of brittleness this system is meant to avoid.
_CLICK_VERBS = "click|open|follow|select|go to|turn on|tap|press|choose|pick|hit"
_CLICK_NOUNS = "link|result|one|video|item|option"

_CLICK_ORDINAL = re.compile(
    rf"\b(?:{_CLICK_VERBS})\b.*?\b(?:{_CLICK_NOUNS})\b.*?"
    rf"\b(?P<ord>{_ORDINAL_WORDS})\b"
    rf"|\b(?:{_CLICK_VERBS})\b.*?\b(?P<ord2>{_ORDINAL_WORDS})\b"
    rf".*?\b(?:{_CLICK_NOUNS})\b",
    re.IGNORECASE,
)

# "click the contact us link", "click on about"
_CLICK_TEXT = re.compile(
    r"\b(?:click|open|follow|select|press)\b\s*(?:on\s+)?(?:the\s+)?"
    r"(?P<text>.+?)"
    r"(?:\s+link|\s+button)?\s*$",
    re.IGNORECASE,
)

# "open github.com in the browser", "browse to example.org"
_BROWSER_OPEN = re.compile(
    r"\b(?:open|go to|browse to|visit|take me to)\b\s+(?P<url>\S+?)"
    r"(?:\s+in\s+(?:the\s+)?browser)?\s*$",
    re.IGNORECASE,
)

_BROWSER_HINT = re.compile(r"\b(?:in|using|with)\s+(?:the\s+)?browser\b", re.IGNORECASE)


# "close notepad", "close the word document", "quit spotify".
#
# Deliberately excludes the words that already mean something else: "close
# window" is Alt+F4 on the focused window and "close browser" shuts down the
# controlled session, both of which are listed verbatim in command_map and
# are matched before this rule is reached.
_CLOSE_NAMED = re.compile(
    r"^(?:please\s+)?(?:close|quit|exit|shut)\s+(?:down\s+)?(?:the\s+)?"
    r"(?P<app>[\w .+-]{2,40}?)"
    r"(?:\s+(?:window|app|application|program|tab|for me|please|now))?$",
    re.IGNORECASE,
)

_CLOSE_RESERVED = {
    "window", "windows", "this", "that", "it", "everything", "all",
    "browser", "tab", "current window", "this window", "the window",
    # The machine itself. "shut down the computer" is a power command, and
    # routing it here would quietly look for a window called "computer" and
    # report that it could not find one - the worst possible outcome for a
    # sensitive action, because it neither does the thing nor says it did
    # not understand.
    "computer", "my computer", "the computer", "pc", "my pc", "laptop",
    "my laptop", "system", "the system", "machine", "the machine",
    "everything down", "down",
}


_ORDINAL_VALUES = {
    "first": 1, "1st": 1, "one": 1,
    "second": 2, "2nd": 2, "two": 2,
    "third": 3, "3rd": 3, "three": 3,
    "fourth": 4, "4th": 4, "four": 4,
    "fifth": 5, "5th": 5, "five": 5,
    "sixth": 6, "6th": 6, "six": 6,
    "seventh": 7, "7th": 7, "seven": 7,
    "eighth": 8, "8th": 8, "eight": 8,
    "ninth": 9, "9th": 9, "nine": 9,
    "tenth": 10, "10th": 10, "ten": 10,
}

_FIELD_NUMBER = r"first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth" \
                r"|one|two|three|four|five|six|seven|eight|nine|ten" \
                r"|1st|2nd|3rd|4th|5th|6th|7th|8th|9th|10th|\d{1,2}"


def _original_case(pattern: "re.Pattern", text: str, fallback: str | None) -> str | None:
    """
    Recover a captured value with its original capitalisation.

    Matching happens against lowercased, punctuation-stripped text, which
    is right for recognising commands and wrong for the data inside them:
    typing a name into a form as "john" rather than "John" is visibly
    wrong, and the user cannot see the page to correct it. So the same
    pattern is re-run against the untouched text and that capture is
    preferred when it is there.
    """
    try:
        match = pattern.search(text)
        if match:
            value = (match.group("value") or "").strip()
            if value:
                return value.rstrip(".,!?")
    except (re.error, IndexError):
        pass
    return (fallback or "").strip() or None


def _as_number(word: str | None) -> int | None:
    """"second" or "2" or "2nd" -> 2. None if it is not a number at all."""
    if not word:
        return None
    word = word.strip().lower()
    if word in _ORDINAL_VALUES:
        return _ORDINAL_VALUES[word]
    return int(word) if word.isdigit() else None


# "fill field two with John", "set the third field to yes"
_FILL_BY_NUMBER = re.compile(
    r"\b(?:fill|set|put|type|enter|write)\b\s*(?:in\s+)?(?:the\s+)?"
    rf"(?:field|box|input)\s+(?:number\s+)?(?P<index>{_FIELD_NUMBER})\b"
    r"(?:\s+(?:with|to|as)\s+(?P<value>.+?))?\s*$",
    re.IGNORECASE,
)

# "set the third field to visa", "fill the second box with yes" - the
# number comes before the noun, which is how most people say it.
_FILL_ORDINAL_FIRST = re.compile(
    r"\b(?:fill|set|put|type|enter|write)\b\s*(?:in\s+)?(?:the\s+)?"
    rf"(?P<index>{_FIELD_NUMBER})\s+(?:field|box|input)\b"
    r"(?:\s+(?:with|to|as)\s+(?P<value>.+?))?\s*$",
    re.IGNORECASE,
)

# "put John in field two", "type yes into box 3" - value stated first.
_FILL_VALUE_FIRST = re.compile(
    r"\b(?:fill|set|put|type|enter|write)\b\s+(?P<value>.+?)\s+"
    r"(?:in|into|in the|into the)\s+(?:the\s+)?(?:field|box|input)\s+"
    rf"(?:number\s+)?(?P<index>{_FIELD_NUMBER})\s*$",
    re.IGNORECASE,
)

# "what can I fill in", "list the fields", "read the form"
_FORM_FIELDS = re.compile(
    r"\b(?:what\s+(?:can\s+i\s+)?fill|list\s+(?:the\s+)?(?:fields|form)"
    r"|read\s+(?:the\s+)?form|show\s+(?:me\s+)?(?:the\s+)?(?:fields|form)"
    r"|what\s+(?:fields|boxes)\b"
    # "fill in the form" is a request for help with it, not an instruction
    # to type the words "the form" somewhere. Listing what it wants is the
    # only sensible first move.
    r"|fill\s+(?:in\s+)?(?:the\s+)?form\b)",
    re.IGNORECASE,
)

# "press the submit button", "click continue button", "submit the form"
_PRESS_BUTTON = re.compile(
    r"\b(?:press|click|hit|tap|push)\b\s*(?:on\s+)?(?:the\s+)?"
    r"(?P<name>.+?)\s+button\s*$"
    r"|^(?:please\s+)?submit(?:\s+the\s+form)?\s*$",
    re.IGNORECASE,
)


# "type github in the search box", "enter my email in the email field",
# "search for cats and press enter", "type hello"
_TYPE_INTO = re.compile(
    r"\b(?:type|enter|write|fill in|put|say|dictate|message)\b\s+(?:in\s+)?"
    r"(?P<value>.+?)"
    r"(?:\s+(?:in|into|in the|into the)\s+(?:the\s+)?(?P<field>[\w\s]+?)"
    r"(?:\s*(?:box|field|bar|input))?)?"
    r"(?P<submit>\s+and\s+(?:press\s+enter|submit|search|go|send|send it))?\s*$",
    re.IGNORECASE,
)


# "open chrome", "launch vs code", "start whatsapp". Checked after the fixed
# phrases so "open notepad" still uses the dedicated handler.
_OPEN_APP = re.compile(
    r"^(?:please\s+)?(?:open|launch|start|run)\s+(?:the\s+)?(?P<app>[\w .+-]{2,40}?)"
    r"(?:\s+(?:app|application|program|for me|please|now))?$",
    re.IGNORECASE,
)


def _app_intent(cleaned: str, text: str, source: str) -> Intent | None:
    """Match "open <anything>" against the applications actually installed."""
    match = _OPEN_APP.match(cleaned)
    if not match:
        return None

    name = match.group("app").strip()
    if not name:
        return None

    try:
        import app_launcher
        if not app_launcher.find(name):
            return None            # not an installed app; let other rules try
    except Exception:
        return None

    return Intent(
        action="open_installed_app",
        target=None,
        params={"app": name},
        confidence=config.CONFIDENCE_PARTIAL,
        raw_text=text, source=source, engine=ENGINE,
    )


def _close_intent(cleaned: str, text: str, source: str) -> Intent | None:
    """Match "close <something named>". None if nothing was named."""
    match = _CLOSE_NAMED.match(cleaned)
    if not match:
        return None

    name = match.group("app").strip()
    if not name or name in _CLOSE_RESERVED:
        return None

    return Intent(
        action="close_app",
        target=name,
        params={"app": name},
        confidence=config.CONFIDENCE_PARTIAL,
        raw_text=text, source=source, engine=ENGINE,
    )


def _browser_intent(cleaned: str, text: str, source: str) -> Intent | None:
    """Match the browser commands that carry an argument. None if no match."""

    # --- forms ---
    #
    # Checked before _TYPE_INTO, which would otherwise swallow "fill field
    # two with John" as "type 'field two with John'".

    if _FORM_FIELDS.search(cleaned):
        return Intent(
            action="browser_fields",
            confidence=config.CONFIDENCE_PARTIAL,
            raw_text=text, source=source, engine=ENGINE,
        )

    for pattern in (_FILL_BY_NUMBER, _FILL_ORDINAL_FIRST, _FILL_VALUE_FIRST):
        match = pattern.search(cleaned)
        if not match:
            continue
        index = _as_number(match.group("index"))
        if index is None:
            continue
        return Intent(
            action="browser_fill",
            target="field",
            params={
                "index": index,
                "value": _original_case(pattern, text, match.group("value")),
            },
            confidence=config.CONFIDENCE_PARTIAL,
            raw_text=text, source=source, engine=ENGINE,
        )

    match = _PRESS_BUTTON.search(cleaned)
    if match:
        name = (match.group("name") or "").strip() or None
        # "press the link button" is a link click, not a form button.
        if name not in ("link", "enter", "key"):
            return Intent(
                action="browser_button",
                target=name,
                params={"button": name},
                confidence=config.CONFIDENCE_PARTIAL,
                raw_text=text, source=source, engine=ENGINE,
            )

    # "type github in the search box"
    # search, not match: the verb is rarely the first word. People say
    # "just type hello", and with a wake-word model the name is not
    # stripped from the transcript, so "jarvis type hello" arrives intact.
    # Anchoring to the start rejected both.
    match = _TYPE_INTO.search(cleaned)
    if match and match.group("value"):
        # Dictation keeps the capitalisation the recogniser produced.
        # Matching runs on lowercased text, which is right for spotting the
        # command and wrong for the words being typed - a message sent
        # entirely in lower case is visibly wrong to whoever receives it.
        value = _original_case(_TYPE_INTO, text, match.group("value"))
        field = (match.group("field") or "").strip() or None
        if field in ("", "the", "a"):
            field = None
        if value:
            return Intent(
                action="browser_type",
                target="field",
                params={
                    "value": value,
                    "field": field,
                    "submit": bool(match.group("submit")),
                },
                confidence=config.CONFIDENCE_PARTIAL,
                raw_text=text, source=source, engine=ENGINE,
            )

    # "click the second link" / "open link number 3"
    match = _CLICK_ORDINAL.search(cleaned)
    if match:
        word = match.group("ord") or match.group("ord2")
        return Intent(
            action="browser_click",
            target="index",
            params={"ordinal": word},
            confidence=config.CONFIDENCE_EXACT,
            raw_text=text, source=source, engine=ENGINE,
        )

    # "open github.com in the browser" - only when the browser is named, so
    # plain "open youtube" still goes to the fast webbrowser command.
    if _BROWSER_HINT.search(cleaned):
        match = _BROWSER_OPEN.search(_BROWSER_HINT.sub("", cleaned).strip())
        if match:
            return Intent(
                action="browser_open",
                target="url",
                params={"query": match.group("url")},
                confidence=config.CONFIDENCE_EXACT,
                raw_text=text, source=source, engine=ENGINE,
            )

    # "click the contact us link" - requires the word link/button, otherwise
    # "click" on its own would swallow the plain cursor-click command.
    if re.search(r"\b(?:link|button)\b", cleaned):
        match = _CLICK_TEXT.search(cleaned)
        if match:
            label = match.group("text").strip()
            label = re.sub(r"\b(?:link|button)\b", "", label).strip()
            if label and label not in ("the", "a", "that", "this"):
                return Intent(
                    action="browser_click",
                    target="text",
                    params={"text": label},
                    confidence=config.CONFIDENCE_PARTIAL,
                    raw_text=text, source=source, engine=ENGINE,
                )
    return None


def get_intent(text: str, source: str = "text") -> Intent:
    """Resolve recognised text to a single Intent. Never raises."""
    if not text or not text.strip():
        return Intent.unknown(raw_text=text or "", source=source)

    cleaned = text.lower().strip()

    # --- 0. browser commands carrying an argument ---
    # Checked before the dictionary so "click the second link" is not
    # swallowed by the plain "click" cursor command.
    browser = _browser_intent(cleaned, text, source)
    if browser is not None:
        return browser

    # --- 1. prefix commands carrying an argument ---
    for prefix in _PREFIXES_BY_LENGTH:
        if prefix in cleaned:
            action, target = _QUERY_PREFIXES[prefix]
            query = cleaned.split(prefix, 1)[1].strip()
            if query:
                return Intent(
                    action=action,
                    target=target,
                    params={"query": query},
                    confidence=config.CONFIDENCE_EXACT,
                    raw_text=text,
                    source=source,
                    engine=ENGINE,
                )
            # No query spoken - fall through so the handler can prompt for it.
            return Intent(
                action=action,
                target=target,
                confidence=config.CONFIDENCE_PARTIAL,
                raw_text=text,
                source=source,
                engine=ENGINE,
            )

    # --- 2. exact match ---
    if cleaned in COMMANDS:
        action, target = COMMANDS[cleaned]
        return Intent(
            action=action,
            target=target,
            confidence=config.CONFIDENCE_EXACT,
            raw_text=text,
            source=source,
            engine=ENGINE,
        )

    # --- 2b. "open <any installed app>" ---
    # After the exact dictionary, so "open notepad" keeps its dedicated
    # handler, but before the substring scan, so "open chrome" is not
    # swallowed by some shorter phrase that happens to appear inside it.
    app = _app_intent(cleaned, text, source)
    if app is not None:
        return app

    # --- 2c. "close <a named window>" ---
    # After the exact dictionary so "close window" and "close browser" keep
    # their own meanings, and before the substring scan so "close notepad"
    # is not swallowed by the word "close" inside a shorter phrase.
    closing = _close_intent(cleaned, text, source)
    if closing is not None:
        return closing

    # --- 3. substring match, longest phrase first ---
    for phrase in phrases():
        if phrase in cleaned:
            action, target = COMMANDS[phrase]
            return Intent(
                action=action,
                target=target,
                confidence=config.CONFIDENCE_PARTIAL,
                raw_text=text,
                source=source,
                engine=ENGINE,
            )

    return Intent.unknown(raw_text=text, source=source)

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
_CLICK_ORDINAL = re.compile(
    rf"\b(?:click|open|follow|select|go to)\b.*?\b(?:link|result|one)\b.*?"
    rf"\b(?P<ord>{_ORDINAL_WORDS})\b"
    rf"|\b(?:click|open|follow|select|go to)\b.*?\b(?P<ord2>{_ORDINAL_WORDS})\b"
    rf".*?\b(?:link|result|one)\b",
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


# "type github in the search box", "enter my email in the email field",
# "search for cats and press enter", "type hello"
_TYPE_INTO = re.compile(
    r"\b(?:type|enter|write|fill in|put)\b\s+(?:in\s+)?"
    r"(?P<value>.+?)"
    r"(?:\s+(?:in|into|in the|into the)\s+(?:the\s+)?(?P<field>[\w\s]+?)"
    r"(?:\s*(?:box|field|bar|input))?)?"
    r"(?P<submit>\s+and\s+(?:press\s+enter|submit|search|go))?\s*$",
    re.IGNORECASE,
)


def _browser_intent(cleaned: str, text: str, source: str) -> Intent | None:
    """Match the browser commands that carry an argument. None if no match."""

    # "type github in the search box"
    match = _TYPE_INTO.match(cleaned)
    if match and match.group("value"):
        value = match.group("value").strip()
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

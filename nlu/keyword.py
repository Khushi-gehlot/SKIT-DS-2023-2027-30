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


def get_intent(text: str, source: str = "text") -> Intent:
    """Resolve recognised text to a single Intent. Never raises."""
    if not text or not text.strip():
        return Intent.unknown(raw_text=text or "", source=source)

    cleaned = text.lower().strip()

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

"""
Natural language understanding: text in, Intent out.

This package is the seam between "what was said" and "what was meant". It
owns the choice of engine so nothing downstream has to care:

    nlu.get_intent("please open notepad")
        -> Intent(action="open_app", target="notepad", confidence=1.0)

Two engines, same signature:

    keyword.py  deterministic phrase matching. Instant, offline, exact.
    llm.py      free-speech understanding. Sprint 1. Not implemented yet.

The policy below is "LLM first, keyword fallback": try the smarter engine, and
drop to the reliable one whenever the LLM is disabled, unavailable, errors, or
reports low confidence. That fallback is what keeps the assistant usable
offline, which matters for an accessibility tool - a user who cannot reach the
keyboard should not be stranded by a dropped connection.
"""

from __future__ import annotations

import config
from intent import Intent

from . import keyword, llm

__all__ = ["get_intent", "get_intents"]


def get_intent(text: str, source: str = "text") -> Intent:
    """
    Resolve recognised text to a single Intent.

    Never raises. Unrecognised input comes back as Intent.unknown(), which the
    caller can act on just like any other intent.
    """
    if config.USE_LLM_INTENT and llm.AVAILABLE:
        try:
            intent = llm.get_intent(text, source)
            if intent.is_understood() and intent.confidence >= config.MIN_CONFIDENCE:
                return intent
            # Understood poorly, or not at all: let the keyword engine try.
        except Exception as e:
            # A model being slow, rate-limited or offline must never take the
            # assistant down with it.
            print(f"LLM intent engine failed ({type(e).__name__}: {e}); using keywords.")

    return keyword.get_intent(text, source)


def get_intents(text: str, source: str = "text") -> list[Intent]:
    """
    Resolve text to one or more Intents.

    Multi-step requests ("open Chrome and search for X") are a Sprint 3
    deliverable; for now this returns at most one. It exists already so
    callers can be written against the final shape and will not need changing
    when multi-step lands.
    """
    intent = get_intent(text, source)
    return [intent] if intent.is_understood() else [intent]

"""
Natural language understanding: text in, Intent out.

This package is the seam between "what was said" and "what was meant". It
owns the choice of engine so nothing downstream has to care:

    nlu.get_intent("could you turn the sound up a bit")
        -> Intent(action="volume", target="up", confidence=0.95, engine="llm")

Two engines, same signature:

    keyword.py  exact phrase matching. Instant, free, offline, no surprises.
    llm.py      free-speech understanding via Mistral. Handles anything.

## The routing policy

1. Keyword first, but only an *exact* match. "open notepad" is already
   unambiguous, so paying a network round trip for it would make the common
   case slow for no gain.
2. Otherwise the LLM, which is where the value is - the phrasings nobody
   thought to add to command_map.
3. Keyword again as a fallback, this time allowing partial matches, if the
   LLM is unavailable, errors, or answers with low confidence.

Step 3 is not a nicety. This is an accessibility tool: a user who cannot
reach the keyboard must not lose control of their machine because an API is
down or the wifi dropped. The keyword engine means the assistant degrades to
"only understands fixed phrases" rather than "stops working".
"""

from __future__ import annotations

import config
from intent import Intent

from . import keyword, llm

__all__ = ["get_intent", "get_intents", "active_engines"]


def get_intent(text: str, source: str = "text") -> Intent:
    """
    Resolve recognised text to a single Intent.

    Never raises. Unrecognised input comes back as Intent.unknown(), which the
    caller can act on just like any other intent.
    """
    if not text or not text.strip():
        return Intent.unknown(raw_text=text or "", source=source)

    # --- 1. exact keyword match: instant, skip the model entirely ---
    if config.KEYWORD_FAST_PATH:
        quick = keyword.get_intent(text, source)
        if quick.is_understood() and quick.confidence >= config.CONFIDENCE_EXACT:
            return quick

    # --- 2. the LLM, for everything phrased freely ---
    if config.USE_LLM_INTENT and llm.is_available():
        try:
            guess = llm.get_intent(text, source)
            if guess.is_understood() and guess.confidence >= config.LLM_MIN_CONFIDENCE:
                return guess
            # Understood poorly or not at all: let keywords have a go.
        except Exception as e:
            # Defensive: llm.get_intent already swallows its own failures, but
            # a bug in it must not take the assistant down.
            print(f"LLM engine raised ({type(e).__name__}: {e}); using keywords.")

    # --- 3. keyword fallback, partial matches allowed ---
    return keyword.get_intent(text, source)


def get_intents(text: str, source: str = "text") -> list[Intent]:
    """
    Resolve text to one or more Intents.

    Multi-step requests ("open Chrome and search for X") are a Sprint 3
    deliverable; for now this returns exactly one. It exists already so
    callers are written against the final shape.
    """
    return [get_intent(text, source)]


def active_engines() -> dict[str, bool | str]:
    """Which engines are in play. Shown in the UI and useful when debugging."""
    return {
        "keyword": True,
        "keyword_fast_path": config.KEYWORD_FAST_PATH,
        "llm": config.USE_LLM_INTENT and llm.is_available(),
        "llm_model": config.MISTRAL_MODEL if llm.is_available() else "not configured",
    }

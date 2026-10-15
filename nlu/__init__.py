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

__all__ = ["get_intent", "get_intents", "active_engines", "stats", "reset_stats"]


# How each utterance was resolved. Counting this is the only way to answer
# "does the LLM actually earn its place?" - the keyword matcher handles most
# traffic, so the LLM's value is entirely in the tail it rescues.
_STATS = {
    "total": 0,
    "keyword_exact": 0,      # resolved instantly, no API call
    "llm_confident": 0,      # the LLM understood something keywords could not
    "llm_low_confidence": 0, # the LLM guessed, but not firmly enough to run
    "keyword_fallback": 0,   # partial phrase match after the LLM declined
    "unknown": 0,            # nothing understood it
    "llm_errors": 0,         # the engine raised rather than returning unknown
}


def stats() -> dict[str, int | float]:
    """Counts of how utterances were resolved, plus derived percentages."""
    out = dict(_STATS)
    total = out["total"] or 1
    out["llm_rescue_rate"] = round(
        100.0 * out["llm_confident"] / total, 1
    )
    out["understood_rate"] = round(
        100.0 * (total - out["unknown"]) / total, 1
    )
    return out


def reset_stats():
    for key in _STATS:
        _STATS[key] = 0


def get_intent(text: str, source: str = "text") -> Intent:
    """
    Resolve recognised text to a single Intent.

    Never raises. Unrecognised input comes back as Intent.unknown(), which the
    caller can act on just like any other intent.
    """
    if not text or not text.strip():
        return Intent.unknown(raw_text=text or "", source=source)

    _STATS["total"] += 1

    # --- 1. keyword match ---
    # Computed once and reused. An exact hit returns immediately; anything
    # weaker is kept as the fallback for step 3 rather than being recomputed.
    matched = keyword.get_intent(text, source)
    if (
        config.KEYWORD_FAST_PATH
        and matched.is_understood()
        and matched.confidence >= config.CONFIDENCE_EXACT
    ):
        _STATS["keyword_exact"] += 1
        return matched

    # --- 2. the LLM, for everything phrased freely ---
    hedged: Intent | None = None
    if config.USE_LLM_INTENT and llm.is_available():
        try:
            guess = llm.get_intent(text, source)
            if guess.is_understood():
                if guess.confidence >= config.LLM_MIN_CONFIDENCE:
                    _STATS["llm_confident"] += 1
                    return guess
                # Understood, but not firmly. Hold it: if the keyword matcher
                # has nothing better, this guess is still worth showing the
                # user - it is more useful than "I do not recognise that".
                hedged = guess
        except Exception as e:
            # Defensive: llm.get_intent already swallows its own failures, but
            # a bug in it must not take the assistant down.
            _STATS["llm_errors"] += 1
            print(f"LLM engine raised ({type(e).__name__}: {e}); using keywords.")

    # --- 3. keyword fallback, partial matches allowed ---
    if matched.is_understood():
        _STATS["keyword_fallback"] += 1
        return matched

    # --- 4. nothing solid: return the hedged guess if there was one ---
    # It keeps its low confidence, which is what stops the pipeline running
    # it. The user is told what was guessed instead.
    if hedged is not None:
        _STATS["llm_low_confidence"] += 1
        return hedged

    _STATS["unknown"] += 1
    return matched


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
        "llm_provider": llm.provider_name(),
        "llm_model": llm.model_name(),
    }

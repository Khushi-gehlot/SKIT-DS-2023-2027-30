"""
LLM intent engine.

NOT IMPLEMENTED YET - this is the Sprint 1 deliverable.

The job: map free speech to {action, target, params} so the user can say
"could you turn the sound up a bit" instead of the exact phrase "volume up".
The keyword engine only matches phrases it already knows; this one is meant to
understand intent it has never seen.

Contract this module must honour:

    get_intent(text, source) -> Intent

Return an Intent with engine="llm" and an honest confidence. When unsure,
return a low confidence or Intent.unknown() - nlu/__init__.py will fall back
to the keyword engine. Never raise: a failed LLM call must degrade to the
fallback, not break the pipeline.

Implementation sketch:

1. Build a prompt listing the valid actions (command_map.ACTIONS) and the
   targets each accepts, then ask for JSON only.
2. Parse the response with Intent.from_dict(), which already ignores unknown
   keys and tolerates missing optional ones.
3. Validate that `action` is one the executor actually handles. A model will
   occasionally invent an action; that must become unknown, not a crash.
4. Cache or short-circuit obvious matches - no point paying latency on
   "open notepad" when the keyword engine already nails it.

For multi-step requests ("open Chrome and search for X") this should
eventually return several Intents; get_intents() below is the hook for that,
left for Sprint 3.
"""

from __future__ import annotations

from intent import Intent

ENGINE = "llm"

# Flipped on once a model is wired up. nlu/__init__.py checks this before
# attempting to use the engine.
AVAILABLE = False


def get_intent(text: str, source: str = "text") -> Intent:
    """Map free speech to an Intent. Not implemented - returns unknown."""
    return Intent.unknown(raw_text=text, source=source)


def get_intents(text: str, source: str = "text") -> list[Intent]:
    """
    Multi-step hook for Sprint 3: "open Chrome and search for X" is two
    intents. Not implemented.
    """
    intent = get_intent(text, source)
    return [intent] if intent.is_understood() else []

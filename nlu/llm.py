"""
LLM intent engine (Mistral).

Turns free speech into an Intent, so the user can say "could you turn the
sound up a bit" instead of the exact phrase "volume up". The keyword engine
only matches phrases it already knows; this one understands requests it has
never seen.

Mistral was chosen because its free tier needs no card, the small models are
fast enough for a voice loop, and the API is plain HTTP - no SDK, so the only
dependency is `requests`, which the project already had.

    MISTRAL_API_KEY=...        in .env

No vector database. The capability catalogue is small enough to list in the
prompt, and doing so is both lighter and more accurate than retrieval - see
the note in prompt.py.

Contract: get_intent() returns an Intent with engine="llm" and never raises.
Every failure path - no key, network down, rate limited, malformed JSON,
invented action - degrades to Intent.unknown() so nlu/__init__.py can fall
back to keyword matching. An assistant whose user cannot reach the keyboard
must not be stranded by someone else's outage.
"""

from __future__ import annotations

import json
import re

import config
from command_map import ACTIONS
from intent import Intent, try_parse

from .prompt import system_prompt

try:
    import requests
except ImportError:
    requests = None

ENGINE = "llm"

# Fields the model is allowed to set. Everything else on the Intent is
# provenance that we fill in ourselves - a model should not be telling us what
# the user said or when.
_MODEL_FIELDS = {"action", "target", "params", "confidence"}

_VALID_ACTIONS = set(ACTIONS)


def is_available() -> bool:
    """Whether the engine can actually be used right now."""
    return bool(requests and config.MISTRAL_API_KEY)


# Read by nlu/__init__.py to decide whether to try this engine at all.
AVAILABLE = is_available()


def _extract_json(text: str) -> dict | None:
    """
    Pull a JSON object out of a model response.

    Models wrap JSON in markdown fences or add a sentence of commentary often
    enough that handling it is cheaper than retrying.
    """
    text = text.strip()

    # ```json ... ``` or ``` ... ```
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fall back to the first {...} block in the response.
    brace = re.search(r"\{.*\}", text, re.DOTALL)
    if brace:
        try:
            return json.loads(brace.group(0))
        except json.JSONDecodeError:
            return None
    return None


def _call_mistral(text: str) -> str | None:
    """Send one classification request. Returns the raw reply, or None."""
    try:
        response = requests.post(
            config.MISTRAL_API_URL,
            headers={
                "Authorization": f"Bearer {config.MISTRAL_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": config.MISTRAL_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt()},
                    {"role": "user", "content": text},
                ],
                "temperature": config.LLM_TEMPERATURE,
                "max_tokens": config.LLM_MAX_TOKENS,
                "response_format": {"type": "json_object"},
            },
            timeout=config.LLM_TIMEOUT,
        )
    except requests.exceptions.Timeout:
        print(f"LLM timed out after {config.LLM_TIMEOUT}s; falling back to keywords.")
        return None
    except requests.exceptions.RequestException as e:
        print(f"LLM unreachable ({type(e).__name__}); falling back to keywords.")
        return None

    if response.status_code == 401:
        print("LLM rejected the API key. Check MISTRAL_API_KEY in .env.")
        return None
    if response.status_code == 429:
        print("LLM rate limit reached; falling back to keywords.")
        return None
    if not response.ok:
        print(f"LLM returned HTTP {response.status_code}; falling back to keywords.")
        return None

    try:
        return response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError) as e:
        print(f"Unexpected LLM response shape ({type(e).__name__}).")
        return None


def get_intent(text: str, source: str = "text") -> Intent:
    """Map free speech to an Intent. Returns Intent.unknown() on any failure."""
    if not text or not text.strip():
        return Intent.unknown(raw_text=text or "", source=source)

    if not is_available():
        return Intent.unknown(raw_text=text, source=source)

    reply = _call_mistral(text.strip())
    if reply is None:
        return Intent.unknown(raw_text=text, source=source)

    data = _extract_json(reply)
    if data is None:
        print(f"LLM did not return JSON: {reply[:120]!r}")
        return Intent.unknown(raw_text=text, source=source)

    # Keep only what the model is allowed to decide, then add our own
    # provenance. This also drops any extra field it invented, which would
    # otherwise fail contract validation.
    payload = {k: v for k, v in data.items() if k in _MODEL_FIELDS}
    payload.update(raw_text=text, source=source, engine=ENGINE)
    payload.setdefault("params", {})

    # A model will occasionally return "null" as a string, or a number as a
    # string. Normalise the cheap cases rather than discarding a good answer.
    if payload.get("target") in ("null", "none", ""):
        payload["target"] = None
    if isinstance(payload.get("confidence"), str):
        try:
            payload["confidence"] = float(payload["confidence"])
        except ValueError:
            payload["confidence"] = 0.0

    intent, errors = try_parse(payload, known_actions=_VALID_ACTIONS)
    if errors:
        # Most often an invented action. Falling back beats acting on it.
        print(f"LLM output failed the intent contract: {'; '.join(errors)}")
        return Intent.unknown(raw_text=text, source=source)

    return intent


def get_intents(text: str, source: str = "text") -> list[Intent]:
    """
    Multi-step hook for Sprint 3: "open Chrome and search for X" is two
    intents. Single-intent for now.
    """
    intent = get_intent(text, source)
    return [intent]

"""
LLM intent engine.

Turns free speech into an Intent, so the user can say "could you turn the
sound up a bit" instead of the exact phrase "volume up". The keyword engine
only matches phrases it already knows; this one understands requests it has
never seen.

Several providers are supported and the first with a key configured is used.
They all speak the OpenAI-compatible /chat/completions shape, so supporting
more than one costs almost nothing - and it means a provider outage or a
provisioning problem does not block the whole feature.

    GROQ_API_KEY=...       in .env    (preferred: free, fast, no card)
    MISTRAL_API_KEY=...
    HF_API_KEY=...

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


# =============== PROVIDERS ===============
#
# Tried in this order; the first with a key wins. Groq is first because
# latency is what matters for a voice assistant - the user is waiting
# mid-sentence, and Groq answers in about a second.

PROVIDERS = [
    ("groq", lambda: (config.GROQ_API_KEY, config.GROQ_API_URL, config.GROQ_MODEL)),
    ("mistral", lambda: (config.MISTRAL_API_KEY, config.MISTRAL_API_URL, config.MISTRAL_MODEL)),
    ("huggingface", lambda: (config.HF_API_KEY, config.HF_API_URL, config.HF_MODEL)),
]


def active_provider() -> tuple[str, str, str, str] | None:
    """(name, key, url, model) for the first configured provider, or None."""
    for name, resolve in PROVIDERS:
        key, url, model = resolve()
        if key:
            return name, key, url, model
    return None


def is_available() -> bool:
    """Whether the engine can actually be used right now."""
    return bool(requests and active_provider())


def provider_name() -> str:
    found = active_provider()
    return found[0] if found else "none"


def model_name() -> str:
    found = active_provider()
    return found[3] if found else "not configured"


# Read by nlu/__init__.py to decide whether to try this engine at all.
AVAILABLE = is_available()

# Fields the model is allowed to set. Everything else on the Intent is
# provenance we fill in ourselves - a model should not be telling us what the
# user said or when.
_MODEL_FIELDS = {"action", "target", "params", "confidence"}

_VALID_ACTIONS = set(ACTIONS)


def extract_json(text: str) -> dict | None:
    """Public alias - the link resolver parses replies the same way."""
    return _extract_json(text)


def _extract_json(text: str) -> dict | None:
    """
    Pull a JSON object out of a model response.

    Models wrap JSON in markdown fences or add a sentence of commentary often
    enough that handling it is cheaper than retrying.
    """
    text = text.strip()

    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    brace = re.search(r"\{.*\}", text, re.DOTALL)
    if brace:
        try:
            return json.loads(brace.group(0))
        except json.JSONDecodeError:
            return None
    return None


def _call_llm(text: str, json_mode: bool = True) -> str | None:
    """Classify one utterance as an intent. Returns the raw reply, or None."""
    return ask(system_prompt(), text, json_mode=json_mode)


def ask(system: str, user: str, json_mode: bool = True,
        max_tokens: int | None = None) -> str | None:
    """
    Send one request to whichever provider is configured.

    Separated from intent classification so other features can reuse the
    provider table, the fallback chain and the error handling rather than
    duplicating all of it. The link resolver is the first such caller.

    json_mode asks the provider to guarantee valid JSON. It is worth having,
    but providers reject some prompts outright with "Failed to generate JSON"
    - so a 400 retries once without it. Responses are parsed leniently
    anyway, which makes the guarantee a convenience rather than a
    requirement.
    """
    found = active_provider()
    if found is None:
        return None
    name, key, url, model = found

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": config.LLM_TEMPERATURE,
        "max_tokens": max_tokens or config.LLM_MAX_TOKENS,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=config.LLM_TIMEOUT,
        )
    except requests.exceptions.Timeout:
        print(f"{name} timed out after {config.LLM_TIMEOUT}s; falling back to keywords.")
        return None
    except requests.exceptions.RequestException as e:
        print(f"{name} unreachable ({type(e).__name__}); falling back to keywords.")
        return None

    if response.status_code == 401:
        print(f"{name} rejected the API key. Check your .env.")
        return None
    if response.status_code == 404:
        print(f"{name} does not offer model '{model}'. Set a different one in .env.")
        return None
    if response.status_code == 429:
        print(f"{name} rate limit reached; falling back to keywords.")
        return None
    if response.status_code == 503:
        # Hugging Face parks idle models and wakes them on demand.
        print(f"{name} model is still loading; falling back to keywords.")
        return None
    if response.status_code == 400 and json_mode:
        # Some prompts make strict JSON mode fail. Ask again without it and
        # lean on the lenient parser instead of losing the answer.
        print(f"{name} rejected JSON mode; retrying without it.")
        return ask(system, user, json_mode=False, max_tokens=max_tokens)

    if not response.ok:
        print(
            f"{name} returned HTTP {response.status_code}: "
            f"{response.text[:120]}; falling back to keywords."
        )
        return None

    try:
        return response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError) as e:
        print(f"Unexpected response shape from {name} ({type(e).__name__}).")
        return None


def get_intent(text: str, source: str = "text") -> Intent:
    """Map free speech to an Intent. Returns Intent.unknown() on any failure."""
    if not text or not text.strip():
        return Intent.unknown(raw_text=text or "", source=source)

    if not is_available():
        return Intent.unknown(raw_text=text, source=source)

    reply = _call_llm(text.strip())
    if reply is None:
        return Intent.unknown(raw_text=text, source=source)

    data = _extract_json(reply)
    if data is None:
        print(f"{provider_name()} did not return JSON: {reply[:120]!r}")
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
    return [get_intent(text, source)]

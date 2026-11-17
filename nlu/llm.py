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
    ("gemini", lambda: (config.GEMINI_API_KEY, config.GEMINI_API_URL, config.GEMINI_MODEL)),
    ("mistral", lambda: (config.MISTRAL_API_KEY, config.MISTRAL_API_URL, config.MISTRAL_MODEL)),
    ("huggingface", lambda: (config.HF_API_KEY, config.HF_API_URL, config.HF_MODEL)),
    # Last because it is the slowest, and first choice for nobody with a
    # working key - but it is the only entry with no quota and no network,
    # so it is what remains when every hosted tier is exhausted. The key is
    # a placeholder: a local server does not authenticate.
    ("ollama", lambda: (
        "local" if config.OLLAMA_ENABLED else "",
        config.OLLAMA_API_URL, config.OLLAMA_MODEL,
    )),
]


def configured_providers() -> list[tuple[str, str, str, str]]:
    """
    Every provider that has a key, in order of preference.

    A list rather than a single choice because free tiers run out. Holding
    only the first configured provider meant a rate limit dropped the
    assistant straight to keyword matching while a second, perfectly usable
    provider sat unused.
    """
    found = []
    for name, resolve in PROVIDERS:
        key, url, model = resolve()
        if key:
            found.append((name, key, url, model))

    # A pinned provider moves to the front rather than replacing the list,
    # so choosing one does not give up the fallbacks behind it.
    if config.LLM_PROVIDER:
        found.sort(key=lambda p: p[0] != config.LLM_PROVIDER)

    return found


def active_provider() -> tuple[str, str, str, str] | None:
    """(name, key, url, model) for the first configured provider, or None."""
    providers = configured_providers()
    return providers[0] if providers else None


def is_available() -> bool:
    """Whether the engine can actually be used right now."""
    return bool(requests and active_provider())


# Which provider produced the most recent reply, for honest logging
# when the chain has failed over.
_last_provider: str | None = None


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

def valid_actions() -> set[str]:
    """
    Every action a reply may name.

    The union of the phrase table and what the executor can actually run.
    command_map alone is not enough: dictation, form filling and closing a
    named window are reached through the matcher's rules and appear in no
    fixed phrase, so validating against the table rejected the model's
    answer for capabilities the system genuinely has.

    Imported lazily to keep nlu free of a hard dependency on the executor.
    """
    actions = set(ACTIONS)
    try:
        import executor
        actions |= set(executor.registered_actions())
    except Exception:
        pass
    return actions


# Reasoning models think out loud before answering, in a tagged block that
# is not part of the reply. DeepSeek-R1 and its distils use <think>; other
# families use slightly different tags, so all the common ones are stripped.
_REASONING_BLOCK = re.compile(
    r"<(think|thinking|reasoning)>.*?</\1>", re.DOTALL | re.IGNORECASE
)

# A truncated reply can leave the opening tag with no closing one, in which
# case everything after it is reasoning that never finished.
_UNCLOSED_REASONING = re.compile(
    r"<(think|thinking|reasoning)>.*$", re.DOTALL | re.IGNORECASE
)


def _is_reasoning_model(model: str) -> bool:
    """Whether this model thinks out loud before answering."""
    lowered = (model or "").lower()
    return any(
        marker in lowered
        for marker in (
            "r1", "reason", "-think", "qwq", "o1", "o3", "deepseek-v3.1",
            # gpt-oss thinks before answering too, and does it in a separate
            # "reasoning" field. With an ordinary token budget it spends the
            # whole allowance deliberating, finishes with reason "length",
            # and returns an empty string as the answer - which looked like
            # a provider fault rather than a budget one.
            "gpt-oss",
        )
    )


def strip_reasoning(text: str) -> str:
    """
    Remove a reasoning model's visible thinking from its reply.

    Without this, a DeepSeek-R1 response is several paragraphs of
    deliberation followed by the JSON, and the parser - which looks for the
    first {...} it can find - picks up a brace from inside the reasoning
    instead of the answer.
    """
    if not text:
        return text
    cleaned = _REASONING_BLOCK.sub("", text)
    cleaned = _UNCLOSED_REASONING.sub("", cleaned)
    return cleaned.strip()


def extract_json(text: str) -> dict | None:
    """Public alias - the link resolver parses replies the same way."""
    return _extract_json(text)


def _extract_json(text: str) -> dict | None:
    """
    Pull a JSON object out of a model response.

    Models wrap JSON in markdown fences or add a sentence of commentary often
    enough that handling it is cheaper than retrying.
    """
    text = strip_reasoning(text).strip()

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
    providers = configured_providers()
    if not providers:
        return None

    # Try each configured provider in turn. Only conditions that another
    # provider could survive are worth moving on for - a rate limit, an
    # outage, a model this account cannot see. A malformed prompt would
    # fail everywhere, so it is not retried.
    for position, provider in enumerate(providers):
        answer, retryable = _ask_one(provider, system, user, json_mode, max_tokens)
        if answer is not None:
            return answer
        if not retryable:
            return None
        if position + 1 < len(providers):
            print(f"  trying {providers[position + 1][0]} instead.")
    return None


def _ask_one(provider, system: str, user: str, json_mode: bool,
             max_tokens: int | None) -> tuple[str | None, bool]:
    """
    One request to one provider.

    Returns (answer, retryable). `retryable` says whether a different
    provider might succeed where this one did not.
    """
    global _last_provider
    name, key, url, model = provider
    _last_provider = name

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": config.LLM_TEMPERATURE,
        # Reasoning models spend most of their output thinking before they
        # answer. The ordinary budget is sized for a one-line JSON object,
        # so a reasoning model would be cut off mid-deliberation and return
        # nothing usable at all.
        "max_tokens": max_tokens or (
            config.LLM_REASONING_MAX_TOKENS if _is_reasoning_model(model)
            else config.LLM_MAX_TOKENS
        ),
    }
    if _is_reasoning_model(model) and config.LLM_REASONING_EFFORT:
        # Ask the model to think less. Classification needs no deliberation,
        # and on gpt-oss the difference is an answer in about a second
        # against one that never arrives because the budget ran out first.
        # Providers that do not know the field ignore it.
        body["reasoning_effort"] = config.LLM_REASONING_EFFORT

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
            # Reasoning models need far longer than the budget set for a
            # one-line classification: the deliberation is generated token
            # by token before the answer starts.
            timeout=(
                config.LLM_REASONING_TIMEOUT if _is_reasoning_model(model)
                else config.LLM_TIMEOUT
            ),
        )
    except requests.exceptions.Timeout:
        limit = (
            config.LLM_REASONING_TIMEOUT if _is_reasoning_model(model)
            else config.LLM_TIMEOUT
        )
        print(f"{name} timed out after {limit}s.")
        return None, True
    except requests.exceptions.RequestException as e:
        print(f"{name} unreachable ({type(e).__name__}).")
        return None, True

    if response.status_code == 401:
        print(f"{name} rejected the API key. Check your .env.")
        return None, True
    if response.status_code == 404:
        print(f"{name} does not offer model '{model}'. Set a different one in .env.")
        return None, True
    if response.status_code == 429:
        print(f"{name} rate limit reached.")
        return None, True
    if response.status_code == 503:
        # Hugging Face parks idle models and wakes them on demand.
        print(f"{name} model is still loading.")
        return None, True
    if response.status_code == 400 and json_mode:
        # Some prompts make strict JSON mode fail. Ask the same provider
        # again without it and lean on the lenient parser instead of losing
        # the answer. Not a reason to move on - the next provider would
        # most likely reject it too.
        print(f"{name} rejected JSON mode; retrying without it.")
        return _ask_one(provider, system, user, False, max_tokens)

    if not response.ok:
        print(
            f"{name} returned HTTP {response.status_code}: "
            f"{response.text[:120]}"
        )
        return None, True

    try:
        return response.json()["choices"][0]["message"]["content"], False
    except (KeyError, IndexError, ValueError) as e:
        print(f"Unexpected response shape from {name} ({type(e).__name__}).")
        return None, True


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
        # The provider that actually answered, not the first one configured.
        # Reporting provider_name() here blamed whichever provider sits at
        # the top of the chain even when it had already failed over - so a
        # timeout on one engine was logged as a parsing fault in another.
        print(f"{_last_provider or provider_name()} did not return JSON: "
              f"{reply[:120]!r}")
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

    intent, errors = try_parse(payload, known_actions=valid_actions())
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

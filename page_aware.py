"""
Resolve a command by showing the model what is actually on the page.

The ordinary intent engine works from words alone. That is correct for
"open notepad" and useless for "open the one about pricing", because
nothing in the sentence says which link that is - the answer is on the
screen, not in the phrase.

So when a request cannot be placed and a browser is open, the page's own
links and form fields are listed, numbered, and sent to the model together
with what the user said. The model answers with a command from the system's
own vocabulary, referring to those numbers.

This sits above both nlu and browser_actions because it needs both, and
neither should import the other: the intent engine has no business knowing
a browser exists, and the browser has no business classifying intents.

    resolve("go to the pricing one")
        -> Intent(action="browser_click", params={"ordinal": "7"})

Returns None whenever it cannot help - no browser, no model, nothing on the
page, or an answer it does not believe - so the caller simply carries on
reporting that it did not understand.
"""

from __future__ import annotations

import config
from intent import Intent, try_parse
from nlu import llm

# Enough of the page for the model to choose from without burying the
# answer in tokens. Pages routinely carry a hundred links of navigation
# furniture; the ones a person means are almost always near the top.
MAX_LINKS = 30
MAX_FIELDS = 12

ENGINE = "page_aware"

SYSTEM_PROMPT = """You turn a spoken request into one command, using what is \
actually on the web page in front of the user.

You are given the page title, a numbered list of its links, a numbered list \
of the boxes that can be filled in, and what the user said.

Reply with ONE JSON object and nothing else:

{"action": "<one of the allowed actions>", "target": <string or null>, \
"params": {...}, "confidence": 0.0-1.0}

The actions you may use, and what they need:

  browser_click   params {"ordinal": "<number from the LINKS list>"}
                  target "index". Use this to follow a link.
  browser_fill    params {"index": <number from the FIELDS list>, \
"value": "<text>"}  - put text in one of the boxes.
  browser_button  params {"button": "<the wording on the button>"} or null \
for the form's submit button.
  browser_fields  no params - read out what can be filled in.
  browser_read    no params - read the page text aloud.
  browser_scroll  target "up", "down", "top" or "bottom".
  browser_nav     target "back", "forward" or "reload".
  browser_type    params {"value": "<text>", "submit": true/false} - type \
into whatever box is focused.

Rules:
- Only ever refer to numbers that appear in the lists you were given.
- Never invent a link, a field or a number.
- If the request does not correspond to anything on this page, answer \
{"action": "unknown", "confidence": 0.0}.
- confidence is how sure you are, honestly. Below 0.5 means you are guessing.
"""


def is_available() -> bool:
    """Whether page-aware resolution can run at all."""
    if not config.PAGE_AWARE_INTENT or not llm.is_available():
        return False
    try:
        import browser_actions
        return browser_actions.browser_is_running()
    except Exception:
        return False


def _describe_page() -> tuple[str, str] | None:
    """(title, catalogue) for the live page, or None if nothing is readable."""
    try:
        import browser_actions

        links = browser_actions.browser_list_links(limit=MAX_LINKS)
        fields = []
        try:
            fields = browser_actions.browser_fields(MAX_FIELDS)
        except Exception:
            # A page with no form is normal, and a failure to enumerate
            # fields should not cost us the links we did get.
            pass

        title = browser_actions.browser_page_title()
    except Exception as e:
        print(f"Could not read the page ({type(e).__name__}).")
        return None

    if not links and not fields:
        return None

    parts = []
    if links:
        parts.append("LINKS:")
        parts += [f"{link.index}. {link.text}" for link in links]
    if fields:
        parts.append("")
        parts.append("FIELDS:")
        parts += [f"{f.index}. {f.label} ({f.kind})" for f in fields]

    return title or "this page", "\n".join(parts)


def resolve(text: str, source: str = "voice") -> Intent | None:
    """
    Work out what the user meant, given what is on the page.

    Never raises: this is a last resort after the ordinary engine has
    already given up, so a failure here must leave the caller exactly where
    it was rather than turning "I did not understand" into a crash.
    """
    if not text or not text.strip() or not is_available():
        return None

    described = _describe_page()
    if described is None:
        return None
    title, catalogue = described

    user_message = (
        f"PAGE: {title}\n\n{catalogue}\n\nThe user said: \"{text}\""
    )

    try:
        answer = llm.ask(SYSTEM_PROMPT, user_message, json_mode=True)
    except Exception as e:
        print(f"Page-aware resolver failed ({type(e).__name__}).")
        return None

    if not answer:
        return None

    payload = llm.extract_json(answer) if hasattr(llm, "extract_json") else None
    if payload is None:
        payload = _loose_json(answer)
    if not isinstance(payload, dict):
        return None

    payload.setdefault("params", {})
    payload["raw_text"] = text
    payload["source"] = source
    payload["engine"] = ENGINE

    intent, errors = try_parse(payload, known_actions=llm.valid_actions())
    if errors:
        print(f"Page-aware resolver returned an invalid intent: {errors[0]}")
        return None
    if not intent.is_understood():
        return None
    if intent.confidence < config.LLM_MIN_CONFIDENCE:
        print(f"Page-aware resolver was only {intent.confidence:.0%} sure; ignoring.")
        return None

    print(
        f"Page-aware resolver chose {intent.action} "
        f"{intent.params} ({intent.confidence:.0%})."
    )
    return intent


def _loose_json(answer: str):
    """Pull the first JSON object out of a reply that may be wrapped in prose."""
    import json
    import re

    match = re.search(r"\{.*\}", answer, re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except ValueError:
        return None

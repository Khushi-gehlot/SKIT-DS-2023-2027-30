# The Intent Contract

**Version 1.0**

Every module in Vyasa passes intents around in this shape. Nothing else is
shared between the speech layer, the NLU layer, authentication and execution —
which is precisely what makes each of them replaceable.

If you are writing a module that *produces* intents (an LLM engine, a new
matcher) or *consumes* them (an executor, a logger, a UI), this document is
the agreement you are coding against.

- Machine-readable version: [`intent_schema.json`](intent_schema.json)
- Python implementation: [`intent.py`](intent.py)

---

## Why an intent object exists

Before this refactor, recognising a command and performing it were the same
step: the matcher found `"open notepad"` and immediately called
`open_notepad()`. There was no moment at which the system knew *what the user
wanted* without having already done it.

The intent object is that moment. It is a **noun, not a verb** — a description
of intention that nothing has acted on yet. Creating one has no side effects.

That single change buys four things:

1. **Swappable modules.** The keyword matcher and the LLM both emit this
   shape, so either can be replaced without touching the executor. Same at the
   other end: Google STT or Whisper, the NLU layer cannot tell.
2. **Testing without consequences.** Asserting that `"open notepad"` produces
   `{"action": "open_app", "target": "notepad"}` does not open Notepad.
   Previously, testing the matcher meant launching applications — and testing
   `"shutdown"` was not something you did twice.
3. **Confirmation before action.** A sensitive intent can be held, verified,
   or refused *before* it runs, rather than `shutdown_system()` starting and
   asking mid-flight.
4. **Meaningful logs.** Store intents and you can measure what users actually
   ask for and where the matcher fails.

---

## The Intent object

```json
{
  "action": "open_app",
  "target": "notepad",
  "params": {},
  "confidence": 1.0,
  "raw_text": "please open notepad",
  "source": "voice",
  "engine": "keyword",
  "timestamp": "2026-10-09T14:30:00",
  "sensitive": false
}
```

| Field | Type | Required | Default | Meaning |
|---|---|---|---|---|
| `action` | string | **yes** | — | Kind of operation. Must be one the executor handles, or `"unknown"`. |
| `target` | string / null | no | `null` | What it applies to. Null for actions that take none. |
| `params` | object | no | `{}` | Extra data, e.g. `{"query": "..."}`. Free-form by design. |
| `confidence` | number 0–1 | no | `0.0` | How sure the producer is. |
| `raw_text` | string | no | `""` | Exactly what was heard or typed. |
| `source` | `"voice"` \| `"text"` | no | `"text"` | How it arrived. |
| `engine` | string | no | `"keyword"` | Which NLU produced it. |
| `timestamp` | string (ISO 8601) | no | now | When it was created. |
| `sensitive` | boolean | no | `false` | Needs speaker verification before running. |

`additionalProperties` is **false**. An unrecognised field is an error, not
something to ignore — a typo in a generated response should be caught, not
silently dropped.

### Notes on individual fields

**`action` and `target` split the way they do** so that similar commands share
one handler. Thirty-four Windows Settings pages are one `open_settings` action
with thirty-four targets, not thirty-four actions. Adding a settings page is a
line of data; adding a *kind* of capability is a new handler.

**`confidence` is meant to be acted on.** Below `config.MIN_CONFIDENCE` the
caller should ask the user to repeat rather than guess. For an accessibility
tool, acting on a bad guess is worse than asking again — the user may not be
able to undo it quickly.

**`source` affects authentication.** A typed command has no audio, so it
cannot be voice-verified. That is a real limitation, not an oversight.

**`sensitive` is set automatically** from `SENSITIVE_ACTIONS` in `intent.py`
(currently `power` and `send_email`) in `__post_init__`, so a producer that
forgets to set it still gets correct behaviour. Verifying every "scroll down"
would be slow and hostile; verifying "shutdown" is the point.

---

## Valid actions and targets

Generated from `command_map.py`. `ACTIONS` in that module is the live list,
and a test asserts the executor has a handler for every one.

| Action | Valid targets | Params |
|---|---|---|
| `open_app` | `calculator`, `command_prompt`, `control_panel`, `file_explorer`, `notepad`, `task_manager` | — |
| `open_folder` | `desktop`, `documents`, `downloads`, `music`, `pictures`, `this_pc`, `videos` | — |
| `open_settings` | any `ms-settings:` page key — `display`, `sound`, `bluetooth`, `network-wifi`, `windowsupdate`, …, or `home` | — |
| `open_website` | `google`, `youtube`, or `url` | `query` = the address, when target is `url` |
| `search_web` | `google`, `youtube` | `query` = search term (prompted for if absent) |
| `cursor_move` | `up`, `down`, `left`, `right` | — |
| `cursor_click` | `left`, `double`, `right` | — |
| `scroll` | `up`, `down` | — |
| `window` | `show_desktop`, `minimize`, `maximize`, `close`, `switch` | — |
| `volume` | `up`, `down`, `mute`, `unmute` | — |
| `media` | `play_pause`, `next`, `previous` | — |
| `power` | `shutdown`, `restart`, `lock`, `sleep` | — **sensitive** |
| `screenshot` | `null` | — |
| `battery` | `null` | — |
| `send_email` | `null` | — **sensitive** |
| `unknown` | `null` | — the "I did not understand" intent |

---

## Rules for producers

A producer is anything that turns text into intents: `nlu/keyword.py` today,
`nlu/llm.py` next sprint.

1. **Always return an Intent.** Never `None`, never raise. Unrecognised input
   is `Intent.unknown(raw_text=...)`, which downstream code handles like any
   other intent.
2. **Report confidence honestly.** A guess at 0.95 is worse than a guess at
   0.4, because the caller cannot tell it should double-check.
3. **Set `engine`** to your own name so logs can tell producers apart.
4. **Only emit actions the executor handles.** A model will occasionally
   invent one; validate before returning, and downgrade to `unknown` rather
   than passing it on.
5. **Never perform the action.** Producing an intent has no side effects. A
   producer that opens a browser has broken the contract.

### Validating generated JSON

An LLM returns text, which may be malformed. Validate before it goes anywhere:

```python
from command_map import ACTIONS
from intent import try_parse

intent, errors = try_parse(response_json, known_actions=set(ACTIONS))
if errors:
    # fall back to the keyword engine rather than guessing
    ...
```

`validate()` returns a list of problems rather than raising, so the LLM engine
can inspect what went wrong and decide whether to retry or fall back.
`parse()` raises `IntentValidationError` when you would rather fail loudly.

---

## Rules for consumers

A consumer is anything that acts on intents: `executor.py`, `auth.py`, the UI,
a logger.

1. **Check `is_understood()` first.** `action == "unknown"` means the user
   said something the system could not place; tell them, do not guess.
2. **Treat `sensitive` as binding.** If it is true, the intent goes through
   `authenticate()` before `execute()`. No shortcuts.
3. **Never raise.** `execute()` returns a failed `ExecutionResult` instead,
   because an always-on assistant must survive a broken action — the user may
   not be able to reach the keyboard to restart it.
4. **Do not mutate intents.** Treat them as a record of what was requested. If
   a stage needs to change something, build a new one.

---

## ExecutionResult

What comes back from `execute()`. Failures are data, not exceptions.

```json
{
  "success": true,
  "message": "Opened notepad",
  "intent": { "...": "the intent that produced this" },
  "data": null
}
```

| Field | Type | Meaning |
|---|---|---|
| `success` | boolean | Did it work |
| `message` | string | Human-readable, safe to speak aloud or show in the UI |
| `intent` | object / null | The intent this came from, for logging |
| `data` | any | Optional payload, e.g. a screenshot path or battery percentage |

## AuthResult

What comes back from `authenticate()`.

| Field | Type | Meaning |
|---|---|---|
| `allowed` | boolean | May this intent run |
| `message` | string | Why — shown to the user when refused |
| `speaker` | string / null | Who was identified, once enrolment exists |
| `similarity` | number / null | Cosine similarity against the stored voiceprint |

A result object rather than a bare boolean, so the assistant can say *why* it
refused instead of failing mutely — which matters when the user cannot see a
log.

---

## Changing this contract

The contract is the one thing four people depend on simultaneously. Changing
it is cheap now and expensive later.

- **Adding an optional field** is backward compatible. Give it a default and
  add it to `_SCHEMA` in `intent.py` and to `intent_schema.json`.
- **Adding an action** means a new handler in `executor.py`. A test asserts
  every action in `command_map.ACTIONS` has one.
- **Renaming or removing a field** is a breaking change. Bump the version in
  this file and in the schema, and say so to the team — every producer and
  consumer has to move together.

### Why these field names

`action` / `target` / `params` matches what the LLM intent engine is specified
to emit in Sprint 1. The contract was written against the *future* producer on
purpose: if the keyword matcher used different names, every intent would need
translating at the boundary, and the two engines would not be interchangeable
in the way the whole design depends on.

"""
The intent contract.

Every module in the pipeline speaks this shape. Nothing else is shared between
the speech layer, the NLU layer and the execution layer, which is what makes
them swappable:

    audio --transcribe()--> text --get_intent()--> Intent --execute()--> Result

An Intent describes *what the user wants*. It carries no knowledge of how the
request will be carried out, and creating one has no side effects. That is the
whole point - the system can inspect, log, confirm or reject an intent before
anything happens.

The field names match what the LLM intent engine is specified to emit
({action, target, params}), so the keyword matcher and the LLM are drop-in
replacements for each other.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field, asdict
from typing import Any


# Actions that change or risk the user's system badly enough to deserve a
# confirmation, and - once speaker verification lands - a voice check.
SENSITIVE_ACTIONS = {"power", "send_email"}

UNKNOWN = "unknown"


@dataclass
class Intent:
    """
    One thing the user wants done.

    action : the kind of operation, e.g. "open_app", "volume", "power"
    target : what it applies to,     e.g. "notepad", "up", "shutdown"
    params : extra data,             e.g. {"query": "python tutorials"}
    """

    action: str = UNKNOWN
    target: str | None = None
    params: dict[str, Any] = field(default_factory=dict)

    # How confident the matcher is, 0.0-1.0. The keyword matcher reports 1.0
    # for an exact hit and lower for a partial one; the LLM will report its own.
    confidence: float = 0.0

    # Provenance, for logging and for deciding whether to ask the user again.
    raw_text: str = ""
    source: str = "text"          # "voice" | "text"
    engine: str = "keyword"       # which NLU produced this: "keyword" | "llm"
    timestamp: str = field(
        default_factory=lambda: datetime.datetime.now().isoformat(timespec="seconds")
    )

    # Set by the matcher; read by authenticate() to decide whether to challenge.
    sensitive: bool = False

    def __post_init__(self):
        # Keep the flag honest even if a caller forgets to set it.
        if self.action in SENSITIVE_ACTIONS:
            self.sensitive = True

    # --- predicates ---

    def is_understood(self) -> bool:
        return self.action != UNKNOWN

    # --- serialisation ---

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready. Used for logging, and for what the LLM returns."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Intent":
        """
        Build an Intent from a dict, ignoring unknown keys.

        Tolerant on purpose: an LLM will occasionally return extra fields or
        omit optional ones, and that should not crash the pipeline.
        """
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})

    @classmethod
    def unknown(cls, raw_text: str = "", source: str = "text") -> "Intent":
        """The 'I did not understand that' intent."""
        return cls(action=UNKNOWN, raw_text=raw_text, source=source, confidence=0.0)

    def __str__(self) -> str:
        bits = [self.action]
        if self.target:
            bits.append(f"target={self.target}")
        if self.params:
            bits.append(f"params={self.params}")
        return f"Intent({', '.join(bits)}, confidence={self.confidence:.2f})"


class IntentValidationError(ValueError):
    """Raised when a dict does not satisfy the intent contract."""


# Field -> (expected type, required). Anything not listed is rejected by
# strict validation, so a typo in an LLM response is caught rather than
# silently ignored.
_SCHEMA: dict[str, tuple[type | tuple[type, ...], bool]] = {
    "action": (str, True),
    "target": ((str, type(None)), False),
    "params": (dict, False),
    "confidence": ((int, float), False),
    "raw_text": (str, False),
    "source": (str, False),
    "engine": (str, False),
    "timestamp": (str, False),
    "sensitive": (bool, False),
}

VALID_SOURCES = {"voice", "text"}


def validate(data: dict[str, Any], known_actions: set[str] | None = None) -> list[str]:
    """
    Check a dict against the intent contract. Returns a list of problems,
    empty if it is valid.

    Returning errors rather than raising is deliberate: the LLM engine needs
    to inspect what went wrong and decide whether to retry or fall back,
    which an exception makes awkward.

    `known_actions` is optional because the contract itself does not own the
    list of valid actions - command_map does. Pass it in to also check that
    the action is one the system can actually carry out.
    """
    errors: list[str] = []

    if not isinstance(data, dict):
        return [f"expected an object, got {type(data).__name__}"]

    for key in data:
        if key not in _SCHEMA:
            errors.append(f"unknown field '{key}'")

    for field_name, (expected, required) in _SCHEMA.items():
        if field_name not in data:
            if required:
                errors.append(f"missing required field '{field_name}'")
            continue
        value = data[field_name]
        if not isinstance(value, expected):
            names = (
                expected.__name__
                if isinstance(expected, type)
                else " or ".join(t.__name__ for t in expected)
            )
            errors.append(
                f"field '{field_name}' should be {names}, got {type(value).__name__}"
            )

    action = data.get("action")
    if isinstance(action, str):
        if not action:
            errors.append("field 'action' must not be empty")
        elif known_actions is not None and action not in known_actions and action != UNKNOWN:
            errors.append(f"unknown action '{action}'")

    confidence = data.get("confidence")
    if isinstance(confidence, (int, float)) and not 0.0 <= confidence <= 1.0:
        errors.append(f"confidence must be between 0 and 1, got {confidence}")

    source = data.get("source")
    if isinstance(source, str) and source not in VALID_SOURCES:
        errors.append(f"source must be one of {sorted(VALID_SOURCES)}, got '{source}'")

    return errors


def parse(data: dict[str, Any], known_actions: set[str] | None = None) -> Intent:
    """
    Validate a dict and turn it into an Intent, or raise.

    This is the gate an LLM response goes through before anything downstream
    sees it. Use Intent.from_dict() directly only for data you produced
    yourself and already trust.
    """
    errors = validate(data, known_actions)
    if errors:
        raise IntentValidationError("; ".join(errors))
    return Intent.from_dict(data)


def try_parse(
    data: dict[str, Any], known_actions: set[str] | None = None
) -> tuple[Intent | None, list[str]]:
    """Validate and parse, returning (intent, errors) instead of raising."""
    errors = validate(data, known_actions)
    if errors:
        return None, errors
    return Intent.from_dict(data), []


@dataclass
class ExecutionResult:
    """What came back from execute(). Never raises - failures are data."""

    success: bool
    message: str
    intent: Intent | None = None
    data: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "intent": self.intent.to_dict() if self.intent else None,
            "data": self.data,
        }

    @classmethod
    def ok(cls, message: str, intent: Intent | None = None, data: Any = None):
        return cls(success=True, message=message, intent=intent, data=data)

    @classmethod
    def fail(cls, message: str, intent: Intent | None = None):
        return cls(success=False, message=message, intent=intent)


@dataclass
class AuthResult:
    """Outcome of authenticate(). Speaker verification fills this in later."""

    allowed: bool
    message: str = ""
    speaker: str | None = None
    similarity: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

"""
Speaker verification.

NOT IMPLEMENTED YET - this is the Sprint 2 deliverable. Everything is allowed
through for now, which is the correct default while the feature is absent:
failing open keeps the assistant usable, and the flag below makes the
behaviour explicit rather than accidental.

The job: confirm the person speaking is the enrolled user before running
anything consequential. Note the design decision baked into the signature -
verification needs the *audio*, not the transcript, because it works on
voiceprint embeddings. The pipeline therefore has to hold on to the recording
past transcription instead of discarding it.

Only sensitive intents are checked (Intent.sensitive, set from
intent.SENSITIVE_ACTIONS). Verifying every "scroll down" would be slow and
hostile; verifying "shutdown" and "send email" is the point.

Planned implementation:

1. Enrolment: record several phrases, compute embeddings with Resemblyzer or
   SpeechBrain, average them into a voiceprint, store it (MongoDB).
2. Verification: embed the incoming audio, cosine-similarity it against the
   stored voiceprint, accept above config.SPEAKER_SIMILARITY_THRESHOLD.
3. On rejection the assistant says "Sorry, I could not recognise your voice"
   and the intent is dropped.
"""

from __future__ import annotations

from typing import Any

import config
from intent import AuthResult, Intent


def is_enrolled() -> bool:
    """Whether a voiceprint exists to compare against. Always False for now."""
    return False


def enroll(audio_samples: list[Any], speaker: str = "default") -> AuthResult:
    """Record a voiceprint for a speaker. Not implemented."""
    return AuthResult(
        allowed=False,
        message="Speaker enrolment is not implemented yet.",
    )


def authenticate(intent: Intent, audio: Any = None) -> AuthResult:
    """
    Decide whether this intent is allowed to run.

    `audio` is the raw recording the intent came from, needed for voiceprint
    comparison. It is None for typed commands, which cannot be voice-verified
    by definition.

    Returns an AuthResult rather than raising or returning a bare bool, so the
    caller can tell the user *why* something was refused.
    """
    # Harmless intents are never challenged.
    if not intent.sensitive:
        return AuthResult(allowed=True, message="Not a sensitive action.")

    # Feature switched off, or nobody enrolled: allow, but say so plainly.
    if not config.REQUIRE_SPEAKER_VERIFICATION or not is_enrolled():
        return AuthResult(
            allowed=True,
            message="Speaker verification is disabled; allowing sensitive action.",
        )

    # --- Sprint 2 lands here ---
    # embedding = embed(audio)
    # similarity = cosine(embedding, stored_voiceprint)
    # allowed = similarity >= config.SPEAKER_SIMILARITY_THRESHOLD
    return AuthResult(
        allowed=False,
        message="Speaker verification is required but not implemented.",
    )

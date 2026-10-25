"""
Speaker verification.

Confirms the person speaking is the enrolled user before anything
consequential runs. Only *sensitive* intents are checked - verifying every
"scroll down" would be slow and hostile, while verifying "shutdown" and
"send email" is the entire point.

Note what authenticate() takes: the raw audio, not the transcript. Voiceprints
are a property of the waveform, which is why core.listen() hands back both and
the pipeline keeps the recording alive past transcription.

The policy here deliberately fails *closed* for sensitive actions once
enrolment exists, and *open* before it. An assistant nobody has enrolled on
must still work; an assistant someone has enrolled on must not let a stranger
shut the machine down.
"""

from __future__ import annotations

from typing import Any

import config
import voiceprint
from intent import AuthResult, Intent


def is_available() -> bool:
    """Whether speaker verification can run at all on this machine."""
    return voiceprint.is_available()


def is_enrolled(speaker: str = "default") -> bool:
    """Whether a voiceprint exists to compare against."""
    return voiceprint.load(speaker) is not None


def enrolled_speakers() -> list[str]:
    return voiceprint.enrolled_speakers()


def enroll(audio_samples: list[Any], speaker: str = "default") -> AuthResult:
    """
    Record a voiceprint from several samples.

    Returns an AuthResult rather than a bool so the caller can tell the user
    *why* enrolment failed - too quiet, too short, library missing.
    """
    if not voiceprint.is_available():
        return AuthResult(
            allowed=False,
            message="Speaker verification needs Resemblyzer. Run: pip install resemblyzer",
        )

    if not audio_samples:
        return AuthResult(allowed=False, message="No recordings were captured.")

    print(f"Building a voiceprint from {len(audio_samples)} samples...")
    embedding = voiceprint.enrol_from_audio(audio_samples)
    if embedding is None:
        return AuthResult(
            allowed=False,
            message="I could not hear enough speech to recognise your voice. "
                    "Try again, a little closer to the microphone.",
        )

    if not voiceprint.save(embedding, speaker):
        return AuthResult(allowed=False, message="I could not save the voiceprint.")

    return AuthResult(
        allowed=True,
        speaker=speaker,
        message=f"Voice enrolled for {speaker}. Sensitive commands will now be checked.",
    )


def unenroll(speaker: str = "default") -> AuthResult:
    """Forget a voiceprint. Biometric data should be easy to delete."""
    if voiceprint.delete(speaker):
        return AuthResult(allowed=True, message=f"Removed the voiceprint for {speaker}.")
    return AuthResult(allowed=False, message=f"No voiceprint stored for {speaker}.")


def verify_audio(audio: Any, speaker: str = "default") -> AuthResult:
    """
    Check one recording against the stored voiceprint.

    Separate from authenticate() so the wake-word check can reuse it without
    needing an Intent - which is what Hitesh's sprint item needs.
    """
    stored = voiceprint.load(speaker)
    if stored is None:
        return AuthResult(allowed=False, message="Nobody is enrolled.")
    if audio is None:
        return AuthResult(allowed=False, message="There is no recording to check.")

    matched, score = voiceprint.verify(audio, stored)
    return AuthResult(
        allowed=matched,
        speaker=speaker if matched else None,
        similarity=round(score, 3),
        message=(
            f"Voice recognised ({score:.0%} match)."
            if matched
            else f"Sorry, I could not recognise your voice ({score:.0%} match)."
        ),
    )


def authenticate(intent: Intent, audio: Any = None) -> AuthResult:
    """
    Decide whether this intent is allowed to run.

    `audio` is the recording the intent came from. It is None for typed
    commands, which cannot be voice-verified by definition.
    """
    # Harmless intents are never challenged. Checking "scroll down" would add
    # a second of latency to the commands used most often.
    if not intent.sensitive:
        return AuthResult(allowed=True, message="Not a sensitive action.")

    if not config.REQUIRE_SPEAKER_VERIFICATION:
        return AuthResult(
            allowed=True,
            message="Speaker verification is switched off.",
        )

    if not voiceprint.is_available():
        # Failing closed here would brick every sensitive command on a
        # machine where the library simply is not installed.
        return AuthResult(
            allowed=True,
            message="Speaker verification is unavailable; allowing.",
        )

    if not is_enrolled():
        return AuthResult(
            allowed=True,
            message="Nobody is enrolled yet, so sensitive commands are allowed. "
                    "Say 'enrol my voice' to set this up.",
        )

    # Enrolment exists, so from here on a sensitive action must be proven.
    if audio is None:
        return AuthResult(
            allowed=False,
            message="That is a sensitive command, so I need to hear you say it.",
        )

    result = verify_audio(audio)
    if not result.allowed and result.similarity is not None:
        result.message = (
            f"Sorry, I could not recognise your voice "
            f"({result.similarity:.0%} match), so I did not run that."
        )
    return result

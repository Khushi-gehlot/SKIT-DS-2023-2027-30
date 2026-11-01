"""
Wake-word detection with a dedicated model.

Until now the wake word was found by transcribing everything and looking for
the name in the text. That asks a general speech recogniser - built to turn
arbitrary sentences into words - to reliably produce four specific letters
from about 400ms of audio with no surrounding context. It does not. In
testing "nova" came back as "google", "I know" and "okinawa": the sounds
were heard correctly and the wrong words were chosen.

openWakeWord solves a much narrower problem. It is a small neural network
trained on one phrase; it takes raw audio in 80ms frames and returns the
probability that the phrase just occurred. It never transcribes anything.

Three consequences, in order of how much they matter:

  accuracy  one question instead of an open-ended one
  privacy   audio no longer leaves the machine until the wake word fires,
            so the speech service only ever receives actual commands
  cost      no network round trip per utterance, and it works offline

This module holds the model and scores frames. It deliberately does not
touch the microphone - core owns that, and reads frames into score().

    is_available()      can detection run at all
    score(frame)        probability this 80ms frame completed the phrase
    detected(frame)     score(frame) >= the configured threshold
    reset()             clear the model's history after a detection
"""

from __future__ import annotations

import threading
import time

import numpy as np

import config

try:
    from openwakeword.model import Model
    OPENWAKEWORD_AVAILABLE = True
except ImportError:
    Model = None
    OPENWAKEWORD_AVAILABLE = False


_model: "Model | None" = None
_lock = threading.Lock()
_load_error: str | None = None

# When the phrase was last detected. The model reports a high score for
# several consecutive frames as the phrase finishes, so without a refractory
# period one "hey jarvis" fires the assistant three or four times.
_last_detection = 0.0


def is_available() -> bool:
    """Whether a wake-word model can be used on this machine."""
    return OPENWAKEWORD_AVAILABLE and config.WAKE_ENGINE == "openwakeword"


def load_error() -> str | None:
    """Why loading failed, for the UI to show instead of silently degrading."""
    return _load_error


def get_model():
    """
    Load the model once, on first use.

    Lazy on purpose: the app must start instantly, and a user who only ever
    clicks the button should not pay for a model they never trigger. Loading
    takes about half a second.
    """
    global _model, _load_error
    if _model is not None:
        return _model

    with _lock:
        if _model is not None:          # another thread won the race
            return _model
        if not OPENWAKEWORD_AVAILABLE:
            _load_error = "openwakeword is not installed (pip install openwakeword)"
            return None
        try:
            print(f"Loading wake-word model '{config.WAKE_MODEL}'...")
            _model = Model(
                wakeword_models=[config.WAKE_MODEL],
                inference_framework=config.WAKE_INFERENCE,
            )
            print("Wake-word model ready.")
        except Exception as e:
            # Most likely the pretrained models were never downloaded.
            _load_error = f"{type(e).__name__}: {e}"
            print(f"Could not load the wake-word model: {_load_error}")
            print("Try: python -c \"from openwakeword.utils import "
                  "download_models; download_models()\"")
            return None
    return _model


def score(frame: bytes | np.ndarray) -> float:
    """
    Probability that the wake phrase just completed, 0.0 to 1.0.

    `frame` is WAKE_FRAME_SAMPLES of 16 kHz mono 16-bit audio, as raw bytes
    from the microphone or as an int16 array. Returns 0.0 if the model is
    unavailable, so a caller can treat "cannot detect" as "did not hear it".
    """
    model = get_model()
    if model is None:
        return 0.0

    if isinstance(frame, (bytes, bytearray)):
        samples = np.frombuffer(frame, dtype=np.int16)
    else:
        samples = np.asarray(frame, dtype=np.int16)

    try:
        predictions = model.predict(samples)
    except Exception as e:
        print(f"Wake-word inference failed: {type(e).__name__}: {e}")
        return 0.0

    # One model is loaded, but predict() always returns a dict keyed by name.
    return float(max(predictions.values())) if predictions else 0.0


def accept(value: float) -> bool:
    """
    Decide whether a score counts as a detection.

    Split from score() so a caller that already has the number - the live
    meter in tools/wake_test.py, for instance - can make the decision
    without running inference on the same frame twice.

    Enforces a refractory period: the score stays high for several frames
    after the phrase ends, which would otherwise trigger the assistant
    repeatedly on a single "hey jarvis".
    """
    global _last_detection

    if value < config.WAKE_THRESHOLD:
        return False

    now = time.monotonic()
    if now - _last_detection < config.WAKE_COOLDOWN_SECONDS:
        return False

    _last_detection = now
    reset()
    return True


def detected(frame: bytes | np.ndarray) -> bool:
    """True when this frame completes the wake phrase."""
    return accept(score(frame))


def reset():
    """
    Clear the model's internal audio history.

    openWakeWord keeps a rolling buffer of recent audio. After a detection
    that buffer still contains the phrase, so without clearing it the next
    few frames would score high again on audio already acted upon.
    """
    # Deliberately does not call get_model(): resetting a model nobody has
    # loaded would make the first speak() pay for loading one that may
    # never be used, e.g. when only the tap-to-speak button is used.
    if _model is None:
        return
    try:
        _model.reset()
    except Exception:
        # Not fatal - the cooldown already guards against double-triggering.
        pass


def describe() -> str:
    """One line for the UI and the logs."""
    if not OPENWAKEWORD_AVAILABLE:
        return "keyword matching (openwakeword not installed)"
    if config.WAKE_ENGINE != "openwakeword":
        return f"keyword matching (engine set to '{config.WAKE_ENGINE}')"
    return f"{config.WAKE_MODEL} model, threshold {config.WAKE_THRESHOLD}"

"""
Voiceprints: turning a recording into a number, and comparing two of them.

Resemblyzer runs a speaker-encoder model that maps any utterance to a
256-dimension vector capturing *who* is speaking rather than *what* they
said. Two recordings of the same person land close together in that space;
two different people do not. Closeness is measured with cosine similarity.

This module is deliberately storage-agnostic: it produces and compares
embeddings and knows nothing about where they live. A JSON file is used by
default, and the same `save`/`load` seam is where MongoDB will plug in.

    enrol_from_audio([a, b, c])  -> averaged voiceprint
    verify(audio, voiceprint)    -> (is_match, similarity)
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np

import config

try:
    from resemblyzer import VoiceEncoder, preprocess_wav
    RESEMBLYZER_AVAILABLE = True
except ImportError:
    VoiceEncoder = preprocess_wav = None
    RESEMBLYZER_AVAILABLE = False


# Where voiceprints live until MongoDB takes over. Beside the code, not in
# the repo - a voiceprint is biometric data and must never be committed.
STORE = Path(__file__).parent / "voiceprints.json"

# Loading the model takes a few seconds, so do it once, lazily: the app must
# start instantly even if nobody ever enrols.
_encoder: "VoiceEncoder | None" = None


def is_available() -> bool:
    return RESEMBLYZER_AVAILABLE


def _get_encoder():
    global _encoder
    if _encoder is not None:
        return _encoder
    if not RESEMBLYZER_AVAILABLE:
        raise RuntimeError(
            "Resemblyzer is not installed. Run: pip install resemblyzer"
        )
    print("Loading speaker encoder... (first run only)")
    _encoder = VoiceEncoder()
    print("Speaker encoder ready.")
    return _encoder


# =============== EMBEDDING ===============

def embed(audio) -> np.ndarray | None:
    """
    Turn a SpeechRecognition AudioData into a 256-dim voiceprint.

    Returns None rather than raising: a failure to embed should mean "cannot
    verify", not a crash in the middle of a command.
    """
    try:
        encoder = _get_encoder()
    except RuntimeError as e:
        print(e)
        return None

    try:
        # Resemblyzer wants 16 kHz mono float32, which SpeechRecognition can
        # produce directly - no temporary WAV file needed.
        pcm = audio.get_raw_data(convert_rate=16000, convert_width=2)
        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0

        # Trims silence and normalises volume, so a quiet enrolment and a
        # loud verification still compare fairly.
        wav = preprocess_wav(samples, source_sr=16000)
        if len(wav) < 16000 * config.MIN_VOICE_SECONDS:
            print(
                f"Recording too short to identify a voice "
                f"(need about {config.MIN_VOICE_SECONDS}s of speech)."
            )
            return None

        return encoder.embed_utterance(wav)
    except Exception as e:
        print(f"Could not create a voiceprint: {type(e).__name__}: {e}")
        return None


def enrol_from_audio(samples: list) -> np.ndarray | None:
    """
    Average several recordings into one voiceprint.

    Averaging matters: a single sample captures one tone of voice on one
    day. Three or four phrases give a centroid that still matches when the
    user is tired, quiet, or slightly further from the microphone.
    """
    embeddings = [e for e in (embed(a) for a in samples) if e is not None]
    if not embeddings:
        return None

    mean = np.mean(embeddings, axis=0)
    # Re-normalise so cosine similarity stays comparable to single embeddings.
    norm = np.linalg.norm(mean)
    return mean / norm if norm else mean


def similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity, 0.0 to 1.0 for normalised voiceprints."""
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denominator == 0:
        return 0.0
    return float(np.dot(a, b) / denominator)


def verify(audio, voiceprint: np.ndarray) -> tuple[bool, float]:
    """
    Is this the enrolled speaker? Returns (matched, score).

    A failure to embed returns (False, 0.0) - "I could not tell" has to mean
    "no" for anything gated by this, not "yes".
    """
    candidate = embed(audio)
    if candidate is None:
        return False, 0.0
    score = similarity(candidate, voiceprint)
    return score >= config.SPEAKER_SIMILARITY_THRESHOLD, score


# =============== STORAGE ===============
#
# A JSON file for now. Keshav's MongoDB work replaces the two functions
# below and nothing else - that is why they are the only place that knows
# how a voiceprint is persisted.

def save(voiceprint: np.ndarray, speaker: str = "default") -> bool:
    try:
        data = _read_all()
        data[speaker] = voiceprint.tolist()
        STORE.write_text(json.dumps(data), encoding="utf-8")
        return True
    except Exception as e:
        print(f"Could not save the voiceprint: {type(e).__name__}: {e}")
        return False


def load(speaker: str = "default") -> np.ndarray | None:
    data = _read_all()
    stored = data.get(speaker)
    return np.array(stored, dtype=np.float32) if stored else None


def delete(speaker: str = "default") -> bool:
    data = _read_all()
    if speaker not in data:
        return False
    del data[speaker]
    try:
        STORE.write_text(json.dumps(data), encoding="utf-8")
        return True
    except Exception:
        return False


def enrolled_speakers() -> list[str]:
    return sorted(_read_all())


def _read_all() -> dict:
    if not STORE.is_file():
        return {}
    try:
        return json.loads(STORE.read_text(encoding="utf-8"))
    except Exception:
        # A corrupt store should not stop the assistant working; it just
        # means nobody is enrolled.
        return {}

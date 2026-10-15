"""
Speech input and output.

The only module that touches the microphone or the speakers. Everything above
it works in text, so the recognition engine can be replaced - Google today,
Whisper next - without anything downstream noticing. That is the whole reason
this layer exists as its own interface.

Public interface:

    transcribe()        record from the microphone, return text or None
    listen()            record and return (text, audio) when the raw audio is
                        needed too, e.g. for speaker verification
    speak(text)         say something out loud
    is_wake_word(text)  did the user address the assistant
    is_sleep_word(text) did the user dismiss it
"""

from __future__ import annotations

import difflib
import io
import random
import re
import time
import threading

import pyttsx3
import speech_recognition as sr

import config

try:
    # SAPI5 talks to COM, which must be initialised on every thread that uses it.
    import pythoncom
except ImportError:
    pythoncom = None


# =============== TEXT TO SPEECH ===============

def speak(text: str):
    """Speak text out loud and also print it (safe for multi-threaded use)."""
    print("Assistant:", text)

    # Streamlit runs scripts in a worker thread and the always-on loop has its
    # own; without this pyttsx3 fails with 'CoInitialize has not been called'.
    if pythoncom is not None:
        try:
            pythoncom.CoInitialize()
        except Exception:
            pass

    try:
        # A new engine per call avoids pyttsx3's 'run loop already started'.
        engine = pyttsx3.init()
        engine.say(text)
        engine.runAndWait()
        engine.stop()
    except Exception as e:
        # If TTS fails, log it and carry on. Losing the voice is not fatal.
        print("TTS error:", e)

    # Let the speakers fall silent before anyone opens the microphone,
    # otherwise the tail of this sentence lands in the next recording.
    time.sleep(config.SPEAK_SETTLE_SECONDS)


# =============== WAKE WORD ===============

def is_wake_word(text: str | None) -> bool:
    """
    True if the recognised text contains any accepted wake phrase.

    A bare wake word is the hardest thing in the whole system to recognise:
    "nova" is under half a second of audio with no surrounding context, where
    a command gives the engine several seconds to work with. So short
    utterances also get a fuzzy pass - if the whole thing is one or two words
    and closely resembles the name, treat it as the wake word.
    """
    if not text:
        return False

    lowered = text.lower().strip()
    if any(w in lowered for w in config.WAKE_WORDS):
        return True

    # Fuzzy pass, short utterances only. Applying this to a long sentence
    # would make almost anything wake the assistant.
    words = re.sub(r"[^a-z0-9 ]", "", lowered).split()
    if not words or len(words) > 2:
        return False

    candidate = words[-1]           # "hey nova" -> "nova"
    return bool(
        difflib.get_close_matches(
            candidate, config.NAME_VARIANTS, n=1, cutoff=config.WAKE_FUZZY_CUTOFF
        )
    )


def strip_wake_word(text: str) -> str:
    """
    Remove the wake phrase, leaving whatever command followed it.

    This is what lets "nova open notepad" work as one breath. Saying both
    together is not just convenient - it is markedly more reliable, because
    the engine gets a full phrase of audio instead of one short word.
    """
    remainder = text.lower().strip()
    for phrase in sorted(config.WAKE_WORDS, key=len, reverse=True):
        if phrase in remainder:
            remainder = remainder.replace(phrase, " ", 1)
            break
    else:
        words = remainder.split()
        if words and difflib.get_close_matches(
            re.sub(r"[^a-z0-9]", "", words[0]),
            config.NAME_VARIANTS, n=1, cutoff=config.WAKE_FUZZY_CUTOFF,
        ):
            remainder = " ".join(words[1:])

    # Drop a leading filler so "nova, please open notepad" resolves cleanly.
    remainder = re.sub(r"^[\s,.]*(please|can you|could you|now)\b", "", remainder)
    return remainder.strip(" ,.")


def is_sleep_word(text: str | None) -> bool:
    """True if the user asked the assistant to stop listening."""
    if not text:
        return False
    lowered = text.lower()
    return any(w in lowered for w in config.SLEEP_WORDS)


# =============== CONVERSATION ===============

def _contains_word(text: str, phrases: list[str]) -> bool:
    """
    Whole-word match.

    Substring matching would be dangerous here: "no" appears inside "notepad"
    and "now", so a plain `in` check could turn a yes into a no.
    """
    lowered = f" {re.sub(r'[^a-z0-9 ]', ' ', text.lower())} "
    return any(f" {p} " in lowered for p in phrases)


def is_yes(text: str | None) -> bool:
    """Did the user agree?"""
    return bool(text) and _contains_word(text, config.YES_WORDS)


def is_no(text: str | None) -> bool:
    """Did the user decline?"""
    return bool(text) and _contains_word(text, config.NO_WORDS)


def greeting() -> str:
    """A spoken greeting, varied so it does not sound like a recording."""
    return random.choice(config.GREETINGS_SPOKEN).format(user=config.USER_TITLE)


def acknowledgement() -> str:
    return random.choice(config.ACKNOWLEDGEMENTS)


def not_understood() -> str:
    return random.choice(config.NOT_UNDERSTOOD)


def farewell() -> str:
    return random.choice(config.FAREWELLS)


# =============== SPEECH TO TEXT ===============

# One Recognizer for the whole process, so the noise calibration it learns is
# not thrown away on every call.
_recognizer = sr.Recognizer()
# Deliberately off. Left on, the threshold drifts with every listen - down to
# single digits in a quiet room, which makes the recogniser fire on silence
# and send noise to the engine ("could not understand the audio"), and upward
# in a noisy one until a normal voice cannot clear it. A value measured by
# calibration and held steady is far more predictable; changing conditions are
# handled by recalibrating periodically instead.
_recognizer.dynamic_energy_threshold = False
_recognizer.pause_threshold = config.PAUSE_THRESHOLD
_calibrated = False
_listens_since_calibration = 0


def list_microphones():
    """Print available input devices and their index."""
    for i, name in enumerate(sr.Microphone.list_microphone_names()):
        print(f"  [{i}] {name}")


def calibrate(duration: float = config.CALIBRATION_SECONDS):
    """Learn the room's noise floor. Called automatically on first listen."""
    global _calibrated, _listens_since_calibration
    try:
        with sr.Microphone(device_index=config.MIC_INDEX) as source:
            _recognizer.adjust_for_ambient_noise(source, duration=duration)
        # A silent or dead device calibrates to ~0, which would make the
        # recogniser trigger on nothing at all. Keep a sane floor.
        if _recognizer.energy_threshold < config.MIN_ENERGY_THRESHOLD:
            _recognizer.energy_threshold = config.MIN_ENERGY_THRESHOLD
        print(f"Mic calibrated, energy threshold = {_recognizer.energy_threshold:.0f}")
        _calibrated = True
        _listens_since_calibration = 0
    except Exception as e:
        print("Calibration failed:", e)


def listen(
    timeout: int = config.LISTEN_TIMEOUT,
    phrase_time_limit: int = config.PHRASE_TIME_LIMIT,
) -> tuple[str | None, sr.AudioData | None]:
    """
    Record one utterance and transcribe it.

    Returns (text, audio). The raw audio comes back too because speaker
    verification needs the waveform, not the transcript - discarding it here
    would make authenticate() impossible to implement.

    Never raises. Silence, a missing microphone or a failed recognition all
    return (None, ...) so callers can treat them uniformly.
    """
    global _calibrated, _listens_since_calibration
    if not _calibrated:
        calibrate()

    # One Recognizer lives for the whole session, so recalibrate occasionally:
    # the room gets noisier or quieter, and a value measured once at startup
    # stops reflecting it.
    if _listens_since_calibration >= config.RECALIBRATE_EVERY:
        _calibrated = False
        _listens_since_calibration = 0
        calibrate()

    # Keep the threshold inside a sane band whatever happened to it. Too low
    # and it records silence; too high and it ignores speech.
    if _recognizer.energy_threshold < config.MIN_ENERGY_THRESHOLD:
        _recognizer.energy_threshold = config.MIN_ENERGY_THRESHOLD
    elif _recognizer.energy_threshold > config.MAX_ENERGY_THRESHOLD:
        _recognizer.energy_threshold = config.MAX_ENERGY_THRESHOLD

    _listens_since_calibration += 1

    try:
        with sr.Microphone(device_index=config.MIC_INDEX) as source:
            print(f"Listening... (threshold {_recognizer.energy_threshold:.0f})")
            audio = _recognizer.listen(
                source, timeout=timeout, phrase_time_limit=phrase_time_limit
            )
    except sr.WaitTimeoutError:
        # Nobody spoke in time. Normal, not an error.
        print("No speech detected (timeout).")
        return None, None
    except Exception as e:
        # Microphone missing, device busy, driver fault.
        print(f"Microphone error: {type(e).__name__}: {e}")
        return None, None

    text = transcribe_audio(audio)
    return text, audio


def transcribe_audio(audio: sr.AudioData) -> str | None:
    """
    Turn recorded audio into text with whichever engine is configured.

    Split out from listen() so the same audio can be re-transcribed - useful
    for comparing engines, and for the diagnostics in tools/.
    """
    if config.STT_ENGINE == "google":
        return _transcribe_google(audio)
    return _transcribe_whisper(audio)


# =============== WHISPER (local, default) ===============
#
# Runs entirely on this machine: no internet, no API key, no per-request
# latency to a server. It is also markedly better than Google at proper nouns
# and Indian-accented English, which is what the wake word depends on -
# Google returned "hello guys" for "hello vyas" every single time.

_whisper_model = None
_whisper_lock = threading.Lock()


def _load_whisper():
    """
    Load the model once, on first use.

    Loading takes a few seconds and the model is a few hundred megabytes, so
    it is deliberately not loaded at import time - the app should start
    instantly even if speech is never used. The lock matters because the
    always-on loop and the UI thread can both reach this.
    """
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model

    with _whisper_lock:
        if _whisper_model is not None:      # another thread won the race
            return _whisper_model
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            raise RuntimeError(
                "faster-whisper is not installed. Run: pip install faster-whisper"
            ) from None

        print(
            f"Loading Whisper '{config.WHISPER_MODEL}' "
            f"({config.WHISPER_DEVICE}/{config.WHISPER_COMPUTE_TYPE})... "
            "first run downloads the model."
        )
        _whisper_model = WhisperModel(
            config.WHISPER_MODEL,
            device=config.WHISPER_DEVICE,
            compute_type=config.WHISPER_COMPUTE_TYPE,
        )
        print("Whisper ready.")
    return _whisper_model


def _is_hallucination(text: str) -> bool:
    """
    Whisper invents speech when it hears none.

    Fed silence it confidently returns "Thank you." or "Thanks for watching!"
    - artefacts of its training data. An always-on assistant listens to a lot
    of silence, so these have to be filtered or it acts on imaginary commands.
    """
    return text.strip().lower().strip(".!?,") in {
        h.strip(".!?,") for h in config.WHISPER_HALLUCINATIONS
    }


def _transcribe_whisper(audio: sr.AudioData) -> str | None:
    """Transcribe locally with faster-whisper."""
    try:
        model = _load_whisper()
    except RuntimeError as e:
        print(e)
        return None

    try:
        # Hand Whisper a raw float32 array rather than a WAV file.
        #
        # faster-whisper decodes files through PyAV, and current PyAV
        # versions have dropped an argument it still passes, which fails with
        # "open() got an unexpected keyword argument 'metadata_errors'".
        # Converting here skips the decoder entirely: it is immune to that
        # version clash, saves a decode step, and guarantees Whisper gets the
        # 16 kHz mono it wants regardless of what the microphone recorded at.
        import numpy as np

        pcm = audio.get_raw_data(convert_rate=16000, convert_width=2)
        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0

        segments, info = model.transcribe(
            samples,
            language=config.WHISPER_LANGUAGE,
            beam_size=5,
            vad_filter=True,            # drop non-speech before decoding
            vad_parameters={"min_silence_duration_ms": 500},
        )
        text = " ".join(segment.text for segment in segments).strip()
    except Exception as e:
        print(f"Whisper error: {type(e).__name__}: {e}")
        return None

    if not text:
        print("Could not understand the audio (nothing recognised).")
        return None

    if _is_hallucination(text):
        print(f"Ignoring likely hallucination on silence: {text!r}")
        return None

    print("You said:", text)
    return text.lower()


# =============== GOOGLE WEB SPEECH (disabled) ===============
#
# The original cloud engine, kept for comparison in the report. It needs
# internet, adds a network round trip to every utterance, and misheard proper
# nouns badly - "vyas" came back as "guys" without fail, which is why the
# wake word never matched.
#
# Re-enable with:  VYAS_STT=google  in .env

def _transcribe_google(audio: sr.AudioData) -> str | None:
    """Transcribe via Google Web Speech. Superseded by Whisper."""
    try:
        text = _recognizer.recognize_google(audio, language=config.STT_LANGUAGE)
        print("You said:", text)
        return text.lower()
    except sr.UnknownValueError:
        # Audio captured but unintelligible: too quiet, too noisy, or silence.
        print("Could not understand the audio (speak louder / closer to the mic).")
        return None
    except sr.RequestError as e:
        # The speech service is unreachable - no internet, DNS, or refused.
        print("Speech service unreachable:", e)
        return None
    except Exception as e:
        print(f"Recognition error: {type(e).__name__}: {e}")
        return None


def transcribe(
    timeout: int = config.LISTEN_TIMEOUT,
    phrase_time_limit: int = config.PHRASE_TIME_LIMIT,
) -> str | None:
    """
    Record from the microphone and return what was said, or None.

    The plain interface, for callers that do not need the raw audio.
    """
    text, _audio = listen(timeout=timeout, phrase_time_limit=phrase_time_limit)
    return text


# Kept so existing callers keep working; transcribe() is the name to use.
recognize_speech = transcribe

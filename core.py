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

import io
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


# =============== WAKE WORD ===============

def is_wake_word(text: str | None) -> bool:
    """True if the recognised text contains any accepted wake phrase."""
    if not text:
        return False
    lowered = text.lower()
    return any(w in lowered for w in config.WAKE_WORDS)


def is_sleep_word(text: str | None) -> bool:
    """True if the user asked the assistant to stop listening."""
    if not text:
        return False
    lowered = text.lower()
    return any(w in lowered for w in config.SLEEP_WORDS)


# =============== SPEECH TO TEXT ===============

# One Recognizer for the whole process, so the noise calibration it learns is
# not thrown away on every call.
_recognizer = sr.Recognizer()
_recognizer.dynamic_energy_threshold = True
_recognizer.pause_threshold = config.PAUSE_THRESHOLD
_calibrated = False


def list_microphones():
    """Print available input devices and their index."""
    for i, name in enumerate(sr.Microphone.list_microphone_names()):
        print(f"  [{i}] {name}")


def calibrate(duration: float = config.CALIBRATION_SECONDS):
    """Learn the room's noise floor. Called automatically on first listen."""
    global _calibrated
    try:
        with sr.Microphone(device_index=config.MIC_INDEX) as source:
            _recognizer.adjust_for_ambient_noise(source, duration=duration)
        # A silent or dead device calibrates to ~0, which would make the
        # recogniser trigger on nothing at all. Keep a sane floor.
        if _recognizer.energy_threshold < config.MIN_ENERGY_THRESHOLD:
            _recognizer.energy_threshold = config.MIN_ENERGY_THRESHOLD
        print(f"Mic calibrated, energy threshold = {_recognizer.energy_threshold:.0f}")
        _calibrated = True
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
    global _calibrated
    if not _calibrated:
        calibrate()

    try:
        with sr.Microphone(device_index=config.MIC_INDEX) as source:
            print("Listening...")
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

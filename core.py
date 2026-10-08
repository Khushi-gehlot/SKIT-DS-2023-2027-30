# core.py
import os

import pyttsx3
import speech_recognition as sr

try:
    # SAPI5 talks to COM, which must be initialised on every thread that uses it.
    import pythoncom
except ImportError:
    pythoncom = None


def speak(text: str):
    """Speak text out loud and also print it (safe for multi-threaded use)."""
    print("Assistant:", text)

    # FastAPI runs handlers in a worker thread and the always-on loop has its own
    # thread; without this pyttsx3 fails with 'CoInitialize has not been called'.
    if pythoncom is not None:
        try:
            pythoncom.CoInitialize()
        except Exception:
            pass

    try:
        # New engine per call avoids 'run loop already started'
        engine = pyttsx3.init()
        engine.say(text)
        engine.runAndWait()
        engine.stop()
    except Exception as e:
        # If TTS fails, just log it and DO NOT crash the app
        print("TTS error:", e)


# Set VYAS_MIC_INDEX to pin a specific input device (see list_microphones()).
# Left unset, PyAudio's default input device is used.
MIC_INDEX = os.environ.get("VYAS_MIC_INDEX")
MIC_INDEX = int(MIC_INDEX) if MIC_INDEX and MIC_INDEX.isdigit() else None

# One Recognizer for the whole process, so the noise calibration it learns is
# not thrown away on every call.
_recognizer = sr.Recognizer()
_recognizer.dynamic_energy_threshold = True   # keep adapting to the room
_recognizer.pause_threshold = 0.8             # silence that ends a phrase
_calibrated = False


# =============== WAKE WORD ===============
#
# Speech-to-text rarely returns "vyas" verbatim. Google transcribes it as
# "guys", "wise", "bias" and similar depending on accent and mic. Matching only
# the literal spelling meant the wake word almost never fired, so we accept a
# greeting followed by any plausible rendering of the name.

_GREETINGS = ["hello", "hey", "hi", "ok", "okay", "yo"]

_NAME_VARIANTS = [
    "vyas", "vyaas", "vias", "viyas", "byas", "wyas",
    "guys", "gas", "grass",          # what Google usually hears
    "wise", "vice", "voice", "bias", "boys", "views",
    "bhai", "bai", "by", "buy", "bye",
]

# Every greeting + name pair, e.g. "hello guys", "hey vyas", "ok bhai".
WAKE_WORDS = [f"{g} {n}" for g in _GREETINGS for n in _NAME_VARIANTS]

SLEEP_WORDS = [
    "sleep", "go to sleep", "stop listening", "goodbye", "good night",
]


def is_wake_word(text: str | None) -> bool:
    """True if the recognised text contains any accepted wake phrase."""
    if not text:
        return False
    return any(w in text.lower() for w in WAKE_WORDS)


def is_sleep_word(text: str | None) -> bool:
    """True if the user asked the assistant to stop listening."""
    if not text:
        return False
    return any(w in text.lower() for w in SLEEP_WORDS)


def list_microphones():
    """Print available input devices and their index."""
    for i, name in enumerate(sr.Microphone.list_microphone_names()):
        print(f"  [{i}] {name}")


def calibrate(duration: float = 1.0):
    """Learn the room's noise floor. Called automatically on first listen."""
    global _calibrated
    try:
        with sr.Microphone(device_index=MIC_INDEX) as source:
            _recognizer.adjust_for_ambient_noise(source, duration=duration)
        # A silent/dead device calibrates to ~0, which would make the recognizer
        # trigger on nothing. Keep a sane floor.
        if _recognizer.energy_threshold < 100:
            _recognizer.energy_threshold = 100
        print(f"Mic calibrated, energy threshold = {_recognizer.energy_threshold:.0f}")
        _calibrated = True
    except Exception as e:
        print("Calibration failed:", e)


def recognize_speech(timeout=8, phrase_time_limit=8) -> str | None:
    """Listen from microphone and return recognized text, or None."""
    global _calibrated
    if not _calibrated:
        calibrate()

    r = _recognizer
    try:
        with sr.Microphone(device_index=MIC_INDEX) as source:
            print("Listening...")
            audio = r.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
    except sr.WaitTimeoutError:
        # Nobody spoke in time. Normal, not an error.
        print("No speech detected (timeout).")
        return None
    except Exception as e:
        # Mic missing, device busy, etc. Never let this reach the caller.
        print("Microphone error:", e)
        return None

    try:
        text = r.recognize_google(audio, language="en-IN")
        print("You said:", text)
        return text.lower()
    except sr.UnknownValueError:
        # Audio captured but not intelligible: too quiet, too noisy, or silence.
        print("Could not understand the audio (speak louder / closer to the mic).")
        return None
    except sr.RequestError as e:
        # Google unreachable - no internet, DNS, or API refused the request.
        print("Speech service unreachable:", e)
        return None
    except Exception as e:
        print(f"Recognition error: {type(e).__name__}: {e}")
        return None

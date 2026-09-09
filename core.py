# core.py
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


def recognize_speech(timeout=5, phrase_time_limit=5) -> str | None:
    """Listen from microphone and return recognized text, or None."""
    r = sr.Recognizer()
    try:
        with sr.Microphone() as source:
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
    except Exception as e:
        print("Recognition error:", e)
        return None

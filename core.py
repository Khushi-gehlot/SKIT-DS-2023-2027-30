# core.py
import pyttsx3
import speech_recognition as sr

def speak(text: str):
    """Speak text out loud and also print it (safe for multi-threaded use)."""
    print("Assistant:", text)
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
    """Listen from microphone and return recognized text."""
    r = sr.Recognizer()
    with sr.Microphone() as source:
        print("Listening...")
        audio = r.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)

    try:
        text = r.recognize_google(audio, language="en-IN")
        print("You said:", text)
        return text.lower()
    except Exception as e:
        print("Recognition error:", e)
        return None

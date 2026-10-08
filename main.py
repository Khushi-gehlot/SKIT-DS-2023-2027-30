"""
Command-line entry point, and the backwards-compatible process_command().

The routing logic that used to live here now lives in nlu/ (what the user
means) and executor.py (how it gets done). What remains is a thin wrapper so
existing callers keep working, plus a CLI for testing without the UI.

    python main.py              voice loop, wake word required
    python main.py --text       type commands instead of speaking
"""

from __future__ import annotations

import sys

import pipeline
from core import is_sleep_word, is_wake_word, speak, transcribe


def process_command(command_text: str) -> bool:
    """
    Run a command and report whether it was understood and executed.

    Kept for compatibility with code written against the old router. New code
    should call pipeline.handle_text(), which returns an ExecutionResult with
    the intent and a message instead of a bare boolean.
    """
    result = pipeline.handle_text(command_text)
    print(result.message)
    return result.success


# =============== CLI ===============

def _text_loop():
    """Type commands. Useful for testing without a microphone."""
    print("Type a command, or 'quit' to exit.")
    while True:
        try:
            text = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if text.lower() in ("quit", "exit"):
            break
        if not text:
            continue
        result = pipeline.handle_text(text)
        print(f"  {'ok' if result.success else 'fail'}: {result.message}")
        if result.intent:
            print(f"  intent: {result.intent}")


def _voice_loop():
    """Wake word, then commands until a sleep word."""
    speak("Voice assistant ready. Say the wake word.")
    while True:
        text = transcribe()
        if not text:
            continue

        if not is_wake_word(text):
            print("(ignored, no wake word):", text)
            continue

        speak("I'm listening.")
        while True:
            command = transcribe()
            if not command:
                continue
            if is_sleep_word(command):
                speak("Going back to sleep.")
                break
            result, _ = pipeline.handle_text(command), None
            speak("Done." if result.success else "I did not recognise that.")


if __name__ == "__main__":
    if "--text" in sys.argv:
        _text_loop()
    else:
        _voice_loop()

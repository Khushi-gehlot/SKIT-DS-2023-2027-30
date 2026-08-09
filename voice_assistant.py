# voice_assistant.py

from core import speak, recognize_speech
from command_map import COMMANDS


WAKE_WORDS = ["hello vyas", "hello bhai", "hey vyas"]  # you can customize


def is_wake_word(text: str) -> bool:
    """Check if the recognized text contains any wake word."""
    if not text:
        return False
    text = text.lower()
    return any(wake in text for wake in WAKE_WORDS)


def process_command(command_text: str) -> bool:
    """
    Match the spoken command to known commands and execute them.
    Returns True if something ran, else False.
    """
    if not command_text:
        return False

    command_text = command_text.lower().strip()
    print("Processing command:", command_text)

    # Exact match
    if command_text in COMMANDS:
        COMMANDS[command_text]()
        return True

    # Fuzzy match: if key phrase is contained in full sentence
    for key, func in COMMANDS.items():
        if key in command_text:
            func()
            return True

    speak("I do not recognize that command.")
    return False


def listen_for_wake_word():
    """Continuously listen until a wake word is detected."""
    speak("Voice assistant is sleeping. Say 'hello bhai' to wake me up.")
    while True:
        text = recognize_speech()
        if is_wake_word(text):
            speak("Yes, I'm listening. What do you want me to do?")
            return  # exit when woke up


def command_session():
    """
    After wake word, listen for commands in a loop until user says
    'sleep', 'stop', 'exit', or there's too much silence.
    """
    while True:
        speak("Please say a command, or say 'sleep' to stop.")
        cmd = recognize_speech()

        if not cmd:
            speak("I didn't catch that.")
            continue

        print("You said:", cmd)

        if any(word in cmd for word in ["sleep", "stop", "exit", "goodbye"]):
            speak("Okay, going back to sleep.")
            break

        # Run the command
        ran = process_command(cmd)
        if not ran:
            # we already spoke in process_command
            pass


def main():
    speak("VyasaOS voice assistant started.")
    while True:
        # 1) Wait until user says wake word
        listen_for_wake_word()
        # 2) Once awake, listen for one or more commands
        command_session()
        # loop back: sleeps again, waits for wake word


if __name__ == "__main__":
    main()

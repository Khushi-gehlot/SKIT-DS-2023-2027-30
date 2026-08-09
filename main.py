from core import speak, recognize_speech
from command_map import COMMANDS
from actions import search_google_voice, search_youtube_voice

import webbrowser
import urllib.parse


# Dynamic Voice Search Functions

def search_google(query: str):
    """Search a query on Google."""
    url = "https://www.google.com/search?q=" + urllib.parse.quote(query)
    speak(f"Searching Google for {query}")
    webbrowser.open(url)


def search_youtube(query: str):
    """Search a query on YouTube."""
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query)
    speak(f"Searching YouTube for {query}")
    webbrowser.open(url)


def open_website(site: str):
    """Open a specific website."""
    if not site.startswith("http"):
        site = "https://" + site

    speak(f"Opening {site}")
    webbrowser.open(site)


# Command Processing

def process_command(command_text: str) -> bool:
    """
    Try to match the user command text to known commands,
    and execute the corresponding function.
    Returns True if a command was found and executed, else False.
    """

    command_text = command_text.lower().strip()
    print("Processing command:", command_text)


    # Dynamic Search Commands


    if "search google for" in command_text:
        search_google_voice(command_text)
        return True

    # ===== YOUTUBE SEARCH =====

    if "search youtube for" in command_text:
        search_youtube_voice(command_text)
        return True

    if "open website" in command_text:
        site = command_text.replace("open website", "").strip()
        if site:
            open_website(site)
            return True


    # Existing Command System

    if command_text in COMMANDS:
        COMMANDS[command_text]()
        return True

    for key, func in COMMANDS.items():
        if key in command_text:
            func()
            return True

    speak("I do not recognize that command.")
    return False


# Voice Assistant Loop

if __name__ == "__main__":

    speak("Voice mode active. Say your command.")

    while True:

        text = recognize_speech()

        if text:
            process_command(text)
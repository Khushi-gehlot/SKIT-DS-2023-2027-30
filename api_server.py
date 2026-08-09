import traceback
import threading
from typing import List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from main import process_command
from command_map import COMMANDS
from core import speak, recognize_speech

# ----------------- Wake words & global flags -----------------

WAKE_WORDS = ["hello vyas", "hello bhai", "hey vyas"]

# Words that will end the active listening session (no need to say wake word again)
SLEEP_WORDS = ["sleep", "go to sleep", "stop listening", "goodbye", "good night"]

# Controls the background "always-on" listening loop
always_on_flag = False
always_on_thread: threading.Thread | None = None


# ----------------- Pydantic models -----------------

class CommandRequest(BaseModel):
    command: str


class CommandResponse(BaseModel):
    success: bool
    message: str


class ListenResponse(BaseModel):
    success: bool
    recognized: str | None
    message: str


class ToggleResponse(BaseModel):
    running: bool
    message: str


# ----------------- FastAPI app setup -----------------

app = FastAPI(title="VyasOS Automation API", version="1.0.0")

# Allow the React dev server to talk to this API
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------- Helper: always-on background loop -----------------

def always_on_loop():
    """
    Background loop (Jarvis-style):

    - First waits for wake word like "hello vyas".
    - Once heard, enters an "awake" session where it listens for commands
      continuously (no need to repeat wake word).
    - Session ends only when user says a sleep word like "sleep" / "stop listening".
    - Then it goes back to waiting for the wake word again.
    """
    global always_on_flag

    speak("Always-on wake word listening started.")

    while always_on_flag:
        # 1) Wait for wake word
        speak("Listening for wake word.")
        wake_text = recognize_speech()

        if not always_on_flag:
            break

        if not wake_text:
            # Nothing heard, keep waiting
            continue

        wake_lower = wake_text.lower()
        if not any(wake in wake_lower for wake in WAKE_WORDS):
            # Not a wake word, ignore
            print("Heard (ignored, no wake word):", wake_text)
            continue

        # 2) Wake word detected → enter ACTIVE SESSION
        speak(
            "I'm awake now. You can give me commands. "
            "Say 'sleep' when you want me to stop listening."
        )

        # Inner loop: keep listening for commands until sleep word
        while always_on_flag:
            cmd_text = recognize_speech()

            if not always_on_flag:
                break

            if not cmd_text:
                speak("I didn't catch that. Please repeat your command.")
                continue

            cmd_lower = cmd_text.lower()
            print("Heard command:", cmd_text)

            # 3) Check for sleep/end-session words
            if any(word in cmd_lower for word in SLEEP_WORDS):
                speak("Okay, going back to sleep. Say the wake word when you need me again.")
                break  # break inner loop → back to wake word listening

            # 4) Otherwise, treat it as a normal command
            try:
                ok = process_command(cmd_text)
                if ok:
                    speak("Command executed.")
                else:
                    speak("I did not recognize that command.")
            except Exception as e:
                traceback.print_exc()
                speak(f"Error while executing your command: {e}")

    speak("Always-on wake word listening stopped.")


# ----------------- Routes -----------------

@app.get("/api/commands", response_model=List[str])
def list_commands():
    """Return list of available command keywords."""
    return sorted(COMMANDS.keys())


@app.post("/api/command", response_model=CommandResponse)
def run_command(req: CommandRequest):
    """Run a text command (used by manual UI mode)."""
    cmd = req.command.strip()
    if not cmd:
        return CommandResponse(success=False, message="No command provided.")

    try:
        success = process_command(cmd)
    except Exception as e:
        traceback.print_exc()
        return CommandResponse(
            success=False,
            message=f"Error while executing '{cmd}': {e}"
        )

    if success:
        speak("Command executed.")
        return CommandResponse(success=True, message=f"Executed: {cmd}")
    else:
        speak("Unknown command.")
        return CommandResponse(success=False, message=f"Unknown command: {cmd}")


@app.post("/api/listen", response_model=ListenResponse)
def listen_and_execute():
    """
    Single-shot voice mode from the UI (mic button), but with session:

      1) Listen once for a wake word like 'hello vyas'.
      2) If detected, enter a loop:
         - Listen for commands continuously.
         - Execute each command.
         - Stop only when a sleep word is heard, then return.
    """
    # STEP 1: Listen for wake word
    speak("Say the wake word to start.")
    wake_text = recognize_speech()

    if not wake_text:
        return ListenResponse(
            success=False,
            recognized=None,
            message="I did not hear the wake word. Please try again."
        )

    wake_text_lower = wake_text.lower()
    if not any(wake in wake_text_lower for wake in WAKE_WORDS):
        # No wake word found
        return ListenResponse(
            success=False,
            recognized=wake_text,
            message=f"No wake word detected in: '{wake_text}'. Say 'hello vyas' first."
        )

    # STEP 2: Wake word detected → enter ACTIVE SESSION
    speak(
        "I'm awake now. You can give me commands. "
        "Say 'sleep' when you want me to stop listening."
    )

    # We will store last command text
    last_cmd_text: str | None = None
    last_msg: str = "Session ended."

    # Inner loop: keep listening for commands until sleep word
    while True:
        cmd_text = recognize_speech()

        if not cmd_text:
            speak("I didn't catch that. Please repeat your command.")
            continue

        cmd_lower = cmd_text.lower()
        print("Heard command (listen endpoint):", cmd_text)

        # Check for sleep/end-session words
        if any(word in cmd_lower for word in SLEEP_WORDS):
            speak("Okay, going back to sleep for this session.")
            last_cmd_text = cmd_text
            last_msg = "Session ended by sleep word."
            break

        # Otherwise, treat as normal command
        try:
            ok = process_command(cmd_text)
            last_cmd_text = cmd_text
            if ok:
                msg = f"Executed: {cmd_text}"
                last_msg = msg
                speak("Command executed.")
            else:
                msg = f"Unknown command: {cmd_text}"
                last_msg = msg
                speak("I did not recognize that command.")
        except Exception as e:
            traceback.print_exc()
            last_cmd_text = cmd_text
            last_msg = f"Error while executing '{cmd_text}': {e}"
            speak(f"Error while executing your command: {e}")

    # When session ends, return info about the last command / reason
    recognized_summary = f"Wake: {wake_text}"
    if last_cmd_text:
        recognized_summary += f" | Last command: {last_cmd_text}"

    return ListenResponse(
        success=True,
        recognized=recognized_summary,
        message=last_msg,
    )


@app.post("/api/always_on/start", response_model=ToggleResponse)
def start_always_on():
    """
    Start the background always-on wake-word loop.
    """
    global always_on_flag, always_on_thread

    if always_on_flag:
        return ToggleResponse(
            running=True,
            message="Always-on listening is already running."
        )

    always_on_flag = True
    always_on_thread = threading.Thread(target=always_on_loop, daemon=True)
    always_on_thread.start()

    return ToggleResponse(
        running=True,
        message="Always-on listening started."
    )


@app.post("/api/always_on/stop", response_model=ToggleResponse)
def stop_always_on():
    """
    Signal the background always-on loop to stop.
    It will exit after the current listen finishes.
    """
    global always_on_flag

    if not always_on_flag:
        return ToggleResponse(
            running=False,
            message="Always-on listening is already stopped."
        )

    always_on_flag = False
    return ToggleResponse(
        running=False,
        message="Always-on listening will stop shortly."
    )

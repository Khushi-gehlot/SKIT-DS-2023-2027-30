# streamlit_app.py
"""
VyasOS Voice Assistant — single-process Streamlit app.

There is no web server and no HTTP layer. This app imports the command router
directly and calls the automation functions in-process, so the whole assistant
is one Python program:

    streamlit run streamlit_app.py

Speech recognition, text-to-speech and OS automation all run inside this
process. api_server.py (FastAPI) is kept in the repo for reference but is not
used by this UI.
"""

import datetime
import threading

import streamlit as st

from core import is_sleep_word, is_wake_word, recognize_speech, speak
from command_map import COMMANDS
from main import process_command


# ----------------- Always-on wake word controller -----------------

class AlwaysOnController:
    """
    Owns the background wake-word thread.

    Streamlit re-executes this script on every interaction, so this object is
    held in st.cache_resource to survive reruns. Without that, each rerun would
    create a new controller and leak threads that all fight over the mic.
    """

    def __init__(self):
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.events: list[dict] = []

    # --- state ---

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def log(self, heard: str, message: str, success: bool):
        with self._lock:
            self.events.insert(0, {
                "heard": heard,
                "message": message,
                "success": success,
                "time": datetime.datetime.now().strftime("%H:%M:%S"),
            })
            del self.events[50:]

    def drain(self) -> list[dict]:
        with self._lock:
            items = list(self.events)
            self.events.clear()
        return items

    # --- control ---

    def start(self) -> str:
        if self.is_running():
            return "Always-on is already running."
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return "Always-on listening started."

    def stop(self) -> str:
        if not self.is_running():
            return "Always-on is already stopped."
        self._stop.set()
        return "Stopping — will finish the current listen first."

    # --- the loop ---

    def _loop(self):
        """Wait for a wake word, then take commands until a sleep word."""
        try:
            while not self._stop.is_set():
                text = recognize_speech()
                if self._stop.is_set():
                    break
                if not text:
                    continue

                if not is_wake_word(text):
                    self.log(text, "Ignored — no wake word.", False)
                    continue

                speak("I'm awake. Give me a command, or say sleep.")
                self.log(text, "Wake word detected.", True)

                while not self._stop.is_set():
                    cmd = recognize_speech()
                    if self._stop.is_set() or not cmd:
                        continue

                    if is_sleep_word(cmd):
                        speak("Going back to sleep.")
                        self.log(cmd, "Session ended.", True)
                        break

                    try:
                        ok = process_command(cmd)
                        self.log(cmd, "Executed." if ok else "Not recognised.", ok)
                    except Exception as e:
                        self.log(cmd, f"Error: {e}", False)
        except Exception as e:
            self.log("(loop crashed)", str(e), False)
        finally:
            self._stop.set()


@st.cache_resource
def get_controller() -> AlwaysOnController:
    return AlwaysOnController()


# ----------------- Command execution -----------------

def run_command(text: str) -> tuple[bool, str]:
    """Run a command in-process. Returns (success, message)."""
    text = text.strip()
    if not text:
        return False, "No command given."
    try:
        ok = process_command(text)
    except Exception as e:
        return False, f"Error while executing '{text}': {type(e).__name__}: {e}"
    return (True, f"Executed: {text}") if ok else (False, f"Unknown command: {text}")


def log(heard: str, message: str, success: bool):
    st.session_state.history.insert(0, {
        "heard": heard,
        "message": message,
        "success": success,
        "time": datetime.datetime.now().strftime("%H:%M:%S"),
    })


def listen_once() -> tuple[bool, str, str]:
    """Wake word, then one command session. Returns (success, heard, message)."""
    speak("Say the wake word to start.")
    wake = recognize_speech()
    if not wake:
        return False, "(nothing heard)", "I did not hear the wake word."
    if not is_wake_word(wake):
        return False, wake, f"No wake word in '{wake}'. Say 'hello vyas' first."

    speak("I'm awake. Give me a command, or say sleep.")
    last = "Session ended."
    heard = f"Wake: {wake}"

    while True:
        cmd = recognize_speech()
        if not cmd:
            speak("I didn't catch that.")
            continue
        if is_sleep_word(cmd):
            speak("Going back to sleep.")
            heard += f" | last: {cmd}"
            return True, heard, "Session ended by sleep word."
        ok, msg = run_command(cmd)
        speak("Done." if ok else "I did not recognise that.")
        heard += f" | {cmd}"
        last = msg


# ----------------- Page -----------------

st.set_page_config(page_title="VyasOS Voice Assistant", page_icon="🎙️", layout="wide")

if "history" not in st.session_state:
    st.session_state.history = []
if "status" not in st.session_state:
    st.session_state.status = "Idle."
if "last_heard" not in st.session_state:
    st.session_state.last_heard = "—"

controller = get_controller()

# Pull anything the background thread logged since the last rerun.
for ev in reversed(controller.drain()):
    st.session_state.history.insert(0, ev)


with st.sidebar:
    st.subheader("VyasOS")
    st.success(f"{len(COMMANDS)} commands loaded")
    st.caption("Running in-process — no backend server.")

    st.divider()
    st.subheader("Always-on wake word")
    st.caption('Listens continuously for "hello vyas" / "hey vyas" / "hello bhai".')

    running = controller.is_running()
    c1, c2 = st.columns(2)
    if c1.button("Start", use_container_width=True, disabled=running):
        st.session_state.status = controller.start()
        st.rerun()
    if c2.button("Stop", use_container_width=True, disabled=not running):
        st.session_state.status = controller.stop()
        st.rerun()

    if running:
        st.info("Listening in background.")
        st.caption("Refresh the page to see what it heard.")
    else:
        st.caption("Stopped.")

    st.divider()
    with st.expander(f"All {len(COMMANDS)} keywords"):
        st.write(", ".join(sorted(COMMANDS)))


st.title("🎙️ VyasOS Voice Assistant")
st.caption(
    "Say the wake word, then a command. Or type one — typed commands skip "
    "speech recognition and are the reliable way to demo."
)

left, right = st.columns([3, 2])

with left:
    st.subheader("Voice")
    st.caption(
        "Listens for a wake word, then keeps taking commands until you say "
        "\"sleep\". The page is blocked while the session runs."
    )

    if st.button("🎤 Start listening session", type="primary", use_container_width=True):
        with st.spinner("Listening… say your wake word, then commands. Say 'sleep' to end."):
            ok, heard, msg = listen_once()
        st.session_state.last_heard = heard
        st.session_state.status = msg
        log(heard, msg, ok)
        st.rerun()

    st.divider()
    st.subheader("Type a command")

    with st.form("manual", clear_on_submit=True):
        typed = st.text_input(
            "Command",
            placeholder="e.g. open notepad, display settings, battery",
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button("Run", use_container_width=True)

    if submitted and typed.strip():
        ok, msg = run_command(typed)
        st.session_state.status = msg
        log(typed.strip(), msg, ok)
        st.rerun()

    st.divider()
    st.markdown("**Last heard**")
    st.code(st.session_state.last_heard, language=None)
    st.markdown("**Status**")
    st.info(st.session_state.status)

with right:
    st.subheader("Quick commands")
    st.caption("Run as text — no microphone needed.")

    quick = [
        "open notepad", "open calculator", "battery",
        "display settings", "wifi settings", "bluetooth",
        "open downloads", "take screenshot", "scroll down",
        "volume up", "volume down", "open youtube",
    ]
    cols = st.columns(2)
    for i, cmd in enumerate(quick):
        if cols[i % 2].button(cmd, key=f"q_{cmd}", use_container_width=True):
            ok, msg = run_command(cmd)
            st.session_state.status = msg
            log(cmd, msg, ok)
            st.rerun()

    st.divider()
    st.subheader("Conversation log")

    if not st.session_state.history:
        st.caption("Nothing yet.")
    else:
        if st.button("Clear log"):
            st.session_state.history = []
            st.rerun()
        for item in st.session_state.history[:25]:
            icon = "✅" if item["success"] else "⚠️"
            with st.container(border=True):
                st.markdown(f"{icon} **{item['heard']}**  \n`{item['time']}` — {item['message']}")

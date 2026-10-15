# streamlit_app.py
"""
Nova Voice Assistant — single-process Streamlit app.

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

import config

import pipeline
import core
from core import is_sleep_word, is_wake_word, speak, transcribe
from command_map import COMMANDS


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
                text = transcribe()
                if self._stop.is_set():
                    break
                if not text:
                    continue

                if not is_wake_word(text):
                    self.log(text, "Ignored — no wake word.", False)
                    continue

                # "nova open notepad" said as one breath: run it straight
                # away. Saying both together is also markedly more reliable,
                # since the engine gets a full phrase instead of one short
                # word to work with.
                trailing = core.strip_wake_word(text)
                if trailing:
                    self.log(text, "Wake word + command.", True)
                    ok, message = speak_and_run(trailing, source="voice")
                    self.log(trailing, message, ok)
                    continue

                speak(core.greeting())
                self.log(text, "Wake word detected.", True)

                while not self._stop.is_set():
                    cmd = transcribe()
                    if self._stop.is_set() or not cmd:
                        continue

                    if is_sleep_word(cmd):
                        speak(core.farewell())
                        self.log(cmd, "Session ended.", True)
                        break

                    ok, message = speak_and_run(cmd, source="voice")
                    self.log(cmd, message, ok)
        except Exception as e:
            self.log("(loop crashed)", str(e), False)
        finally:
            self._stop.set()


@st.cache_resource
def get_controller() -> AlwaysOnController:
    return AlwaysOnController()


# ----------------- Command execution -----------------

def speak_and_run(text: str, source: str = "voice") -> tuple[bool, str]:
    """
    Run one spoken command, asking for confirmation when unsure.

    This is what makes it feel like a conversation rather than a parser: an
    uncertain guess becomes a question, and a "yes" carries it out. Only used
    on the voice path, where there is a microphone available to answer with.
    """
    result = pipeline.handle_text(text, source=source)

    if result.needs_confirmation and result.intent is not None:
        speak(result.message)
        answer = transcribe(timeout=config.CONFIRM_TIMEOUT)

        if core.is_yes(answer):
            confirmed = pipeline.confirm_and_execute(result.intent)
            speak(core.acknowledgement() if confirmed.success else confirmed.message)
            return confirmed.success, f"{result.message} -> yes -> {confirmed.message}"

        if core.is_no(answer):
            speak("Okay, cancelled.")
            return False, f"{result.message} -> no -> cancelled"

        # Silence, or something that is neither. Treat an unclear answer to a
        # question about a risky action as a no.
        speak("I did not catch that, so I have not done it.")
        return False, f"{result.message} -> unclear -> cancelled"

    speak(core.acknowledgement() if result.success else result.message)
    return result.success, result.message


def run_command(text: str, source: str = "text") -> tuple[bool, str]:
    """Run a command through the full pipeline. Returns (success, message)."""
    if not text or not text.strip():
        return False, "No command given."
    result = pipeline.handle_text(text.strip(), source=source)
    message = result.message
    # Show which engine understood it - the whole point of the LLM layer is
    # handling phrasings the keyword matcher cannot, and that should be visible.
    if result.intent and result.intent.is_understood():
        message += f"  ·  {result.intent.action}/{result.intent.target} via {result.intent.engine}"
    return result.success, message


def log(heard: str, message: str, success: bool):
    st.session_state.history.insert(0, {
        "heard": heard,
        "message": message,
        "success": success,
        "time": datetime.datetime.now().strftime("%H:%M:%S"),
    })


def listen_once() -> tuple[bool, str, str]:
    """
    A continuous command session, started by the button.
    Returns (success, heard, message).

    No wake word required, deliberately. Pressing the microphone button is
    already an explicit "I want to give a command" - demanding a wake word on
    top of it is friction, and in practice it was the part that failed: a bare
    "nova" is under half a second of audio and was routinely dropped, while
    the command that followed transcribed perfectly. Saying "nova" is still
    accepted and simply stripped, so either style works.

    The session stays open after each command, so several can be given
    without tapping again. It ends on a sleep word, or after a few silences -
    the page is blocked while this runs, so it cannot wait forever.

    Always-on mode is different and still needs the wake word, because there
    the assistant has no other way to know it is being addressed.
    """
    speak(core.greeting())

    heard: list[str] = []
    last_message = "Session ended."
    success = False
    silences = 0

    while True:
        spoken = transcribe()

        if not spoken:
            silences += 1
            if silences >= config.SESSION_SILENCE_LIMIT:
                speak(core.farewell())
                return success, " | ".join(heard) or "(nothing heard)", (
                    last_message if heard else "I did not catch anything."
                )
            speak(core.not_understood())
            continue

        silences = 0
        heard.append(spoken)

        if is_sleep_word(spoken):
            speak(core.farewell())
            return success, " | ".join(heard), "Session ended."

        # Tolerate a wake word if one was spoken, but do not require it.
        command = core.strip_wake_word(spoken) if is_wake_word(spoken) else spoken
        if not command:
            # Only the wake word: they are getting our attention, nothing more.
            speak(core.greeting())
            continue

        success, last_message = speak_and_run(command, source="voice")


# ----------------- Page -----------------

st.set_page_config(page_title="Nova Voice Assistant", page_icon="🎙️", layout="wide")

if "history" not in st.session_state:
    st.session_state.history = []
if "status" not in st.session_state:
    st.session_state.status = "Idle."
if "pending" not in st.session_state:
    st.session_state.pending = None
if "last_heard" not in st.session_state:
    st.session_state.last_heard = "—"

controller = get_controller()

# Pull anything the background thread logged since the last rerun.
for ev in reversed(controller.drain()):
    st.session_state.history.insert(0, ev)


with st.sidebar:
    st.subheader("Nova")
    st.success(f"{len(COMMANDS)} commands loaded")
    st.caption("Running in-process — no backend server.")

    _info = pipeline.describe()
    if _info["llm_ready"]:
        st.info(
            f"Understanding: {_info['llm_provider']} / {_info['llm_model']} "
            "+ keyword fallback"
        )
    else:
        st.warning(
            "Understanding: keyword only — set GROQ_API_KEY in .env to "
            "enable free-speech commands."
        )

    st.divider()
    st.subheader("Always-on wake word")
    st.caption('Listens continuously for "nova", "hello nova" or "hey nova".')

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
    _stats = pipeline.describe()["stats"]
    if _stats["total"]:
        st.caption(
            f"**{_stats['total']}** commands this session · "
            f"**{_stats['understood_rate']}%** understood"
        )
        with st.expander("How they were resolved"):
            st.markdown(
                f"- keyword, exact: **{_stats['keyword_exact']}**\n"
                f"- LLM, confident: **{_stats['llm_confident']}**\n"
                f"- LLM, too unsure to run: **{_stats['llm_low_confidence']}**\n"
                f"- keyword fallback: **{_stats['keyword_fallback']}**\n"
                f"- not understood: **{_stats['unknown']}**\n"
                f"- LLM errors: **{_stats['llm_errors']}**\n\n"
                f"The LLM rescued **{_stats['llm_rescue_rate']}%** of commands "
                "the keyword matcher could not place."
            )

    st.divider()
    with st.expander(f"All {len(COMMANDS)} keywords"):
        st.write(", ".join(sorted(COMMANDS)))


st.title("🎙️ Nova Voice Assistant")
st.caption(
    "Tap the mic and just say the command — no wake word needed. Or type one; "
    "speech recognition and are the reliable way to demo."
)

left, right = st.columns([3, 2])

with left:
    st.subheader("Voice")
    st.caption(
        "Tap, then speak your command straight away. Keeps listening until you say "
        "\"sleep\". The page is blocked while the session runs."
    )

    if st.button("🎤 Start listening session", type="primary", use_container_width=True):
        with st.spinner("Listening… say your command. Say 'sleep' to end."):
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
        result = pipeline.handle_text(typed.strip(), source="text")
        if result.needs_confirmation and result.intent is not None:
            # No microphone on the typed path, so ask with buttons instead.
            st.session_state.pending = result.intent
            st.session_state.status = result.message
        else:
            message = result.message
            if result.intent and result.intent.is_understood():
                message += (
                    f"  ·  {result.intent.action}/{result.intent.target}"
                    f" via {result.intent.engine}"
                )
            st.session_state.status = message
            log(typed.strip(), message, result.success)
        st.rerun()

    # Pending confirmation, asked as buttons.
    pending = st.session_state.get("pending")
    if pending is not None:
        st.warning(f"Did you mean **{pipeline.describe_intent(pending)}**?")
        yes_col, no_col = st.columns(2)
        if yes_col.button("Yes, do it", type="primary", use_container_width=True):
            confirmed = pipeline.confirm_and_execute(pending)
            st.session_state.pending = None
            st.session_state.status = confirmed.message
            log(pending.raw_text, confirmed.message, confirmed.success)
            st.rerun()
        if no_col.button("No, cancel", use_container_width=True):
            st.session_state.pending = None
            st.session_state.status = "Cancelled."
            log(pending.raw_text, "Cancelled by user.", False)
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

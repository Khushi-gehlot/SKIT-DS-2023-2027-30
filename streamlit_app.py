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

import hud

st.set_page_config(
    page_title="NOVA — Voice Assistant HUD",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;700;900&family=Share+Tech+Mono&family=Inter:wght@400;500;600&display=swap');

      .stApp { background: radial-gradient(1400px 800px at 50% 20%, #0A2232 0%, #050B14 55%, #03070D 100%); }
      .block-container { padding: 1.1rem 2rem 2rem 2rem; max-width: 1700px; }
      header[data-testid="stHeader"] { background: transparent; }
      html, body, [class*="css"] { font-family: Inter, sans-serif; color: #CFE4F2; }

      /* ---------- header bar ---------- */
      .hud-top { display:flex; align-items:center; justify-content:space-between;
                 border-bottom:1px solid rgba(127,234,255,.18); padding-bottom:1rem; margin-bottom:1.4rem; }
      .hud-brand { display:flex; align-items:center; gap:1rem; }
      .hud-mark { width:56px; height:56px; border:2px solid #7FEAFF; border-radius:12px;
                  display:flex; align-items:center; justify-content:center;
                  box-shadow:0 0 22px rgba(127,234,255,.35); }
      .hud-mark i { width:16px; height:16px; border-radius:50%; background:#7FEAFF;
                    box-shadow:0 0 14px #7FEAFF; display:block; }
      .hud-name { font-family:Orbitron,sans-serif; font-size:2.3rem; font-weight:900;
                  letter-spacing:.34em; color:#EAF6FF; line-height:1; }
      .hud-tag  { font-family:'Share Tech Mono',monospace; font-size:.74rem;
                  letter-spacing:.26em; color:#5E7C92; margin-top:.4rem; }
      .hud-meta { display:flex; align-items:center; gap:2rem;
                  font-family:'Share Tech Mono',monospace; letter-spacing:.14em; }
      .hud-online { color:#3DDC84; font-size:.82rem; letter-spacing:.2em; }
      .hud-online b { display:inline-block; width:9px; height:9px; border-radius:50%;
                      background:#3DDC84; box-shadow:0 0 10px #3DDC84; margin-right:.5rem; }
      .hud-date { color:#7FEAFF; font-size:.84rem; }
      .hud-time { color:#EAF6FF; font-size:1.9rem; font-weight:500; letter-spacing:.06em; }
      .hud-user { display:flex; align-items:center; gap:.65rem; border:1px solid rgba(127,234,255,.25);
                  border-radius:999px; padding:.35rem .9rem .35rem .4rem; }
      .hud-avatar { width:32px; height:32px; border-radius:50%; background:rgba(127,234,255,.16);
                    color:#7FEAFF; display:flex; align-items:center; justify-content:center;
                    font-size:.74rem; font-family:Orbitron,sans-serif; letter-spacing:.06em; }

      /* ---------- panels ---------- */
      .hud-panel { border:1px solid rgba(127,234,255,.2); background:rgba(8,22,36,.6);
                   border-radius:14px; padding:1.3rem 1.4rem; margin-bottom:1.2rem; }
      .hud-h2 { font-family:Orbitron,sans-serif; font-size:1.05rem; font-weight:700;
                letter-spacing:.22em; color:#EAF6FF; margin:0 0 1.1rem 0; }
      .hud-row { display:flex; justify-content:space-between; align-items:baseline;
                 font-family:'Share Tech Mono',monospace; font-size:.86rem;
                 letter-spacing:.1em; color:#8FA9BD; margin-bottom:.45rem; }
      .hud-row b { color:#EAF6FF; font-weight:400; }
      .hud-bar { height:6px; border-radius:3px; background:rgba(127,234,255,.12);
                 overflow:hidden; margin-bottom:1.1rem; }
      .hud-bar > span { display:block; height:100%; border-radius:3px;
                        background:linear-gradient(90deg,#3FBFE0,#7FEAFF);
                        box-shadow:0 0 12px rgba(127,234,255,.6); }

      /* ---------- today ---------- */
      .hud-item { display:flex; gap:1.1rem; padding:.75rem 0;
                  border-bottom:1px solid rgba(127,234,255,.1); }
      .hud-item:last-child { border-bottom:none; }
      .hud-when { font-family:'Share Tech Mono',monospace; color:#7FEAFF;
                  font-size:.84rem; min-width:62px; }
      .hud-what { font-size:.95rem; color:#EAF6FF; font-weight:500; }
      .hud-why  { font-size:.8rem; color:#6E8899; margin-top:.15rem; }

      /* ---------- reactor ---------- */
      .reactor-wrap { display:flex; justify-content:center; padding:.5rem 0 1rem 0; }
      .reactor { position:relative; width:430px; height:430px; }
      .reactor .ring { position:absolute; border-radius:50%; top:50%; left:50%;
                       transform:translate(-50%,-50%); }
      .r1 { width:430px; height:430px; border:1px solid rgba(127,234,255,.18);
            border-top-color:rgba(127,234,255,.75); border-right-color:rgba(127,234,255,.4);
            animation:spin 18s linear infinite; }
      .r2 { width:352px; height:352px;
            background:repeating-conic-gradient(rgba(127,234,255,.5) 0 1deg, transparent 1deg 5deg);
            -webkit-mask:radial-gradient(circle, transparent 0 166px, #000 166px 176px, transparent 176px);
                    mask:radial-gradient(circle, transparent 0 166px, #000 166px 176px, transparent 176px);
            animation:spin 44s linear infinite reverse; }
      .r3 { width:288px; height:288px; border:1px dashed rgba(127,234,255,.26);
            animation:spin 30s linear infinite; }
      .r4 { width:232px; height:232px; border:2px solid rgba(127,234,255,.3);
            border-bottom-color:#7FEAFF; animation:spin 11s linear infinite reverse; }
      .core { width:178px; height:178px; border-radius:50%;
              background:radial-gradient(circle,#BFF4FF 0%,#3FBFE0 38%,rgba(20,70,100,.5) 72%,transparent 100%);
              box-shadow:0 0 90px rgba(127,234,255,.55);
              display:flex; flex-direction:column; align-items:center; justify-content:center;
              animation:pulse 3.4s ease-in-out infinite; }
      .core-name { font-family:Orbitron,sans-serif; font-weight:900; font-size:1.5rem;
                   letter-spacing:.2em; color:#04131C; }
      .core-state { margin-top:.5rem; font-family:'Share Tech Mono',monospace; font-size:.68rem;
                    letter-spacing:.24em; color:#04131C; border:1px solid rgba(4,19,28,.45);
                    border-radius:4px; padding:.2rem .7rem; background:rgba(255,255,255,.45); }
      @keyframes spin  { to { transform:translate(-50%,-50%) rotate(360deg); } }
      @keyframes pulse { 0%,100%{ transform:translate(-50%,-50%) scale(1); opacity:.95 }
                         50%    { transform:translate(-50%,-50%) scale(1.045); opacity:1 } }

      /* ---------- waveform ---------- */
      .wave { display:flex; align-items:flex-end; justify-content:center; gap:3px; height:66px; margin-top:.4rem; }
      .wave i { width:4px; background:linear-gradient(180deg,#7FEAFF,#2C7E9B);
                border-radius:2px; animation:bounce 1.25s ease-in-out infinite; }
      @keyframes bounce { 0%,100%{ height:8% } 50%{ height:100% } }

      /* ---------- controls ---------- */
      div[data-testid="stButton"] > button[kind="primary"] {
          height:3.6rem; font-family:Orbitron,sans-serif; font-size:1rem; font-weight:700;
          letter-spacing:.2em; border-radius:8px; background:#7FEAFF; color:#04070D; border:none;
          box-shadow:0 0 28px rgba(127,234,255,.4);
      }
      div[data-testid="stButton"] > button[kind="primary"]:hover { background:#A6F2FF; color:#04070D; }
      div[data-testid="stButton"] > button {
          min-height:2.7rem; border-radius:7px; border:1px solid rgba(127,234,255,.26);
          background:rgba(10,24,38,.75); color:#CFE4F2;
          font-family:'Share Tech Mono',monospace; letter-spacing:.08em; font-size:.82rem;
      }
      div[data-testid="stButton"] > button:hover { border-color:#7FEAFF; color:#EAF6FF; }
      div[data-testid="stForm"] { border:1px solid rgba(127,234,255,.2); border-radius:12px; }
    </style>
    """,
    unsafe_allow_html=True,
)

for key, default in (
    ("history", []), ("status", "Standing by."), ("pending", None), ("last_heard", "—"),
):
    if key not in st.session_state:
        st.session_state[key] = default

controller = get_controller()
for ev in reversed(controller.drain()):
    st.session_state.history.insert(0, ev)

info = pipeline.describe()
stats = info["stats"]
always_on = controller.is_running()
date_str, time_str = hud.clock()
user = getattr(config, "USER_NAME", "User")
initials = "".join(part[0] for part in user.split()[:2]).upper() or "U"


# ================= HEADER =================

st.markdown(
    f"""
    <div class="hud-top">
      <div class="hud-brand">
        <div class="hud-mark"><i></i></div>
        <div>
          <div class="hud-name">NOVA</div>
          <div class="hud-tag">NEURAL OPERATIONS &amp; VOICE ASSISTANT</div>
        </div>
      </div>
      <div class="hud-meta">
        <div class="hud-online"><b></b>ALL SYSTEMS ONLINE</div>
        <div class="hud-date">{date_str}</div>
        <div class="hud-time">{time_str}</div>
        <div class="hud-user"><div class="hud-avatar">{initials}</div><span>{user}</span></div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)


left, centre, right = st.columns([3, 6, 3], gap="large")

# ---------- LEFT ----------
with left:
    st.markdown('<div class="hud-h2">CONTROLS</div>', unsafe_allow_html=True)
    st.caption("Background listening")
    on_col, off_col = st.columns(2)
    if on_col.button("START", use_container_width=True, disabled=always_on):
        st.session_state.status = controller.start()
        st.rerun()
    if off_col.button("STOP", use_container_width=True, disabled=not always_on):
        st.session_state.status = controller.stop()
        st.rerun()

    engine = (f'{info["llm_provider"]} · {info["llm_model"]}'
              if info["llm_ready"] else "keyword only")
    st.markdown(
        f'<div class="hud-panel" style="margin-top:1rem">'
        f'<div class="hud-h2">PIPELINE</div>'
        f'<div class="hud-row"><span>SPEECH</span><b>{info["stt"]}</b></div>'
        f'<div class="hud-row"><span>UNDERSTANDING</span><b>{engine}</b></div>'
        f'<div class="hud-row"><span>COMMANDS</span><b>{len(COMMANDS)}</b></div>'
        f'<div class="hud-row"><span>UNDERSTOOD</span>'
        f'<b>{stats["understood_rate"] if stats["total"] else 0}%</b></div>'
        f"</div>",
        unsafe_allow_html=True,
    )

    items = hud.today(st.session_state.history)
    if items:
        rows = "".join(
            f'<div class="hud-item"><div class="hud-when">{i["time"]}</div>'
            f'<div><div class="hud-what">{i["title"]}</div>'
            f'<div class="hud-why">{"✓" if i["ok"] else "⚠"} {i["detail"]}</div></div></div>'
            for i in items
        )
    else:
        rows = '<div class="hud-why">No activity yet. Tap the mic to begin.</div>'
    st.markdown(
        f'<div class="hud-panel"><div class="hud-h2">TODAY</div>{rows}</div>',
        unsafe_allow_html=True,
    )

    if st.session_state.history and st.button("CLEAR TRANSCRIPT", use_container_width=True):
        st.session_state.history = []
        st.rerun()

# ---------- CENTRE ----------
with centre:
    state_text = "LISTENING" if always_on else "READY"
    st.markdown(
        f"""
        <div class="reactor-wrap"><div class="reactor">
          <div class="ring r1"></div><div class="ring r2"></div>
          <div class="ring r3"></div><div class="ring r4"></div>
          <div class="ring core">
            <div class="core-name">NOVA</div>
            <div class="core-state">{state_text}</div>
          </div>
        </div></div>
        """,
        unsafe_allow_html=True,
    )

    bars = "".join(
        f'<i style="animation-delay:{(n % 17) * 0.07:.2f}s;'
        f'height:{8 + (n * 37) % 80}%"></i>' for n in range(56)
    )
    st.markdown(f'<div class="wave">{bars}</div>', unsafe_allow_html=True)

    if st.button("◉  TAP AND SPEAK", type="primary", use_container_width=True):
        with st.spinner("Listening… speak now. Say “sleep” when you're done."):
            ok, heard, msg = listen_once()
        st.session_state.last_heard = heard
        st.session_state.status = msg
        log(heard, msg, ok)
        st.rerun()

    with st.form("typed", clear_on_submit=True):
        typed = st.text_input("Command", placeholder="or type a command…",
                              label_visibility="collapsed")
        submitted = st.form_submit_button("EXECUTE", use_container_width=True)

    if submitted and typed.strip():
        result = pipeline.handle_text(typed.strip(), source="text")
        if result.needs_confirmation and result.intent is not None:
            st.session_state.pending = result.intent
            st.session_state.status = result.message
        else:
            message = result.message
            if result.intent and result.intent.is_understood():
                message += (f"  ·  {result.intent.action}/{result.intent.target}"
                            f" via {result.intent.engine}")
            st.session_state.status = message
            log(typed.strip(), message, result.success)
        st.rerun()

    pending = st.session_state.get("pending")
    if pending is not None:
        st.warning(f"Did you mean **{pipeline.describe_intent(pending)}**?", icon="❓")
        yes_col, no_col = st.columns(2)
        if yes_col.button("YES, DO IT", type="primary", use_container_width=True):
            confirmed = pipeline.confirm_and_execute(pending)
            st.session_state.pending = None
            st.session_state.status = confirmed.message
            log(pending.raw_text, confirmed.message, confirmed.success)
            st.rerun()
        if no_col.button("CANCEL", use_container_width=True):
            st.session_state.pending = None
            st.session_state.status = "Cancelled."
            log(pending.raw_text, "Cancelled by user.", False)
            st.rerun()

    st.info(st.session_state.status, icon="💬")

# ---------- RIGHT ----------
with right:
    # Quick commands stack vertically here rather than spanning the page, so
    # each stays a full-width target - easier to hit, and the grouping reads
    # top to bottom like a menu.
    st.markdown('<div class="hud-h2">QUICK COMMANDS</div>', unsafe_allow_html=True)

    GROUPS: dict[str, list[str]] = {
        # Voice first: these are the hardest to remember and the ones that
        # need running in a particular order to set the feature up at all.
        "VOICE ID": ["enrol my voice", "check my voice", "voice status",
                     "forget my voice"],
        "APPS": ["open chrome", "open notepad", "open calculator", "open whatsapp"],
        "WEB": ["open youtube", "search google for news", "list links", "go back"],
        "SYSTEM": ["battery", "take screenshot", "volume up", "volume down"],
        "PLACES": ["open downloads", "open documents", "display settings", "wifi settings"],
    }

    for title, commands in GROUPS.items():
        st.markdown(
            f"<div style=\"font-family:'Share Tech Mono',monospace;font-size:.7rem;"
            f"letter-spacing:.2em;color:#5E7C92;margin:.8rem 0 .35rem\">{title}</div>",
            unsafe_allow_html=True,
        )
        for cmd in commands:
            if st.button(cmd, key=f"q_{cmd}", use_container_width=True):
                ok, msg = run_command(cmd)
                st.session_state.status = msg
                log(cmd, msg, ok)
                st.rerun()

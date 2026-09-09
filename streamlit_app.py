# streamlit_app.py
"""
VyasOS Voice Assistant - Streamlit front end.

This replaces the old React/Vite UI. It is a thin client: every action goes
through the FastAPI backend (api_server.py) over HTTP, so the speech
recognition, TTS and OS automation all still happen server-side.

Run the backend first, then:
    streamlit run streamlit_app.py
"""

import datetime

import requests
import streamlit as st

API_BASE = "http://127.0.0.1:8000"

# /api/listen blocks until the user says a sleep word, so it needs a long
# timeout. The quick endpoints get a short one so a dead backend fails fast.
QUICK_TIMEOUT = 5
LISTEN_TIMEOUT = 600


# ----------------- Backend helpers -----------------

def api_get(path: str, timeout: int = QUICK_TIMEOUT):
    """GET from the backend. Returns (ok, payload_or_error_string)."""
    try:
        res = requests.get(f"{API_BASE}{path}", timeout=timeout)
        res.raise_for_status()
        return True, res.json()
    except requests.exceptions.ConnectionError:
        return False, "Could not reach the backend. Is uvicorn running on port 8000?"
    except requests.exceptions.Timeout:
        return False, f"Backend timed out after {timeout}s."
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def api_post(path: str, timeout: int = QUICK_TIMEOUT):
    """POST to the backend. Returns (ok, payload_or_error_string)."""
    try:
        res = requests.post(f"{API_BASE}{path}", timeout=timeout)
        res.raise_for_status()
        return True, res.json()
    except requests.exceptions.ConnectionError:
        return False, "Could not reach the backend. Is uvicorn running on port 8000?"
    except requests.exceptions.Timeout:
        return False, f"Backend timed out after {timeout}s."
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def api_post_json(path: str, payload: dict, timeout: int = QUICK_TIMEOUT):
    try:
        res = requests.post(f"{API_BASE}{path}", json=payload, timeout=timeout)
        res.raise_for_status()
        return True, res.json()
    except requests.exceptions.ConnectionError:
        return False, "Could not reach the backend. Is uvicorn running on port 8000?"
    except requests.exceptions.Timeout:
        return False, f"Backend timed out after {timeout}s."
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def log(heard: str, message: str, success: bool):
    """Prepend an entry to the conversation log."""
    st.session_state.history.insert(0, {
        "heard": heard,
        "message": message,
        "success": success,
        "time": datetime.datetime.now().strftime("%H:%M:%S"),
    })


# ----------------- Page setup -----------------

st.set_page_config(page_title="VyasOS Voice Assistant", page_icon="🎙️", layout="wide")

# Unlike the React version, always-on mode is NOT auto-started on load.
# Streamlit re-runs this script on every interaction, which would have
# hammered the start endpoint.
if "history" not in st.session_state:
    st.session_state.history = []
if "always_on" not in st.session_state:
    st.session_state.always_on = False
if "status" not in st.session_state:
    st.session_state.status = "Idle."
if "last_heard" not in st.session_state:
    st.session_state.last_heard = "—"


# ----------------- Sidebar: connection + commands -----------------

with st.sidebar:
    st.subheader("Backend")
    st.caption(API_BASE)

    ok, payload = api_get("/api/commands")
    if ok:
        st.success(f"Connected · {len(payload)} commands")
        commands = payload
    else:
        st.error("Offline")
        st.caption(payload)
        commands = []

    st.divider()
    st.subheader("Always-on wake word")
    st.caption(
        "Listens continuously for a wake word "
        "(\"hello vyas\", \"hello bhai\", \"hey vyas\") in a background thread."
    )

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Start", use_container_width=True):
            ok, payload = api_post("/api/always_on/start")
            if ok:
                st.session_state.always_on = payload.get("running", False)
                st.session_state.status = payload.get("message", "")
            else:
                st.session_state.status = payload
            st.rerun()
    with col_b:
        if st.button("Stop", use_container_width=True):
            ok, payload = api_post("/api/always_on/stop")
            if ok:
                st.session_state.always_on = payload.get("running", True)
                st.session_state.status = payload.get("message", "")
            else:
                st.session_state.status = payload
            st.rerun()

    if st.session_state.always_on:
        st.info("Always-on is running.")
    else:
        st.caption("Always-on is stopped.")

    if commands:
        st.divider()
        with st.expander(f"All {len(commands)} supported keywords"):
            st.write(", ".join(commands))


# ----------------- Main area -----------------

st.title("🎙️ VyasOS Voice Assistant")
st.caption(
    "Say the wake word, then a command. Or type one below — typed commands "
    "skip speech recognition entirely, which is the reliable way to demo."
)

left, right = st.columns([3, 2])

with left:
    st.subheader("Voice")
    st.caption(
        "Listens once for a wake word, then keeps taking commands until you "
        "say \"sleep\". The page will be blocked while the session is active."
    )

    if st.button("🎤 Start listening session", type="primary", use_container_width=True):
        with st.spinner("Listening… say your wake word, then commands. Say 'sleep' to end."):
            ok, payload = api_post("/api/listen", timeout=LISTEN_TIMEOUT)
        if ok:
            st.session_state.last_heard = payload.get("recognized") or "(no speech)"
            st.session_state.status = payload.get("message", "")
            log(st.session_state.last_heard, payload.get("message", ""), payload.get("success", False))
        else:
            st.session_state.status = payload
            log("(error)", payload, False)
        st.rerun()

    st.divider()
    st.subheader("Type a command")

    with st.form("manual_command", clear_on_submit=True):
        typed = st.text_input(
            "Command",
            placeholder="e.g. open notepad, display settings, battery",
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button("Run", use_container_width=True)

    if submitted and typed.strip():
        ok, payload = api_post_json("/api/command", {"command": typed.strip()}, timeout=60)
        if ok:
            st.session_state.status = payload.get("message", "")
            log(typed.strip(), payload.get("message", ""), payload.get("success", False))
        else:
            st.session_state.status = payload
            log(typed.strip(), payload, False)
        st.rerun()

    st.divider()
    st.markdown("**Last heard**")
    st.code(st.session_state.last_heard, language=None)
    st.markdown("**Status**")
    st.info(st.session_state.status)

with right:
    st.subheader("Quick commands")
    st.caption("Sent as text — no microphone needed.")

    quick = [
        "open notepad", "open calculator", "battery",
        "display settings", "wifi settings", "bluetooth",
        "open downloads", "take screenshot", "scroll down",
        "volume up", "volume down", "open youtube",
    ]
    qcols = st.columns(2)
    for i, cmd in enumerate(quick):
        if qcols[i % 2].button(cmd, key=f"quick_{cmd}", use_container_width=True):
            ok, payload = api_post_json("/api/command", {"command": cmd}, timeout=60)
            if ok:
                st.session_state.status = payload.get("message", "")
                log(cmd, payload.get("message", ""), payload.get("success", False))
            else:
                st.session_state.status = payload
                log(cmd, payload, False)
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

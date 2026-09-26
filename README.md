# VyasOS — Voice Assistant for Task Automation

A hands-free desktop assistant for Windows. Speak a wake word, give a command, and
the machine does it — opens apps, changes system settings, controls the cursor,
manages volume and media, takes screenshots, searches the web, or sends an email.

Built as a FastAPI backend that owns speech and OS automation, with a Streamlit
front end as a thin client over its REST API.

---

## Features

- **Wake-word activation** — say "hello vyas" / "hello bhai" / "hey vyas", then
  keep issuing commands until you say "sleep". No need to repeat the wake word.
- **159 voice commands** across apps, folders, Windows Settings pages, window
  management, cursor control, media keys, power actions and web search.
- **Typed-command fallback** — every command is also reachable as text, which
  makes the system demonstrable without a microphone.
- **Always-on mode** — a background thread listens for the wake word continuously.
- **Spoken feedback** — offline text-to-speech confirms each action.
- **Confirmation prompts** on destructive actions (shutdown and restart ask for a
  spoken "yes").

---

## Architecture

```
┌─────────────────────────┐
│  Streamlit UI  :8501    │   thin client, HTTP only
└───────────┬─────────────┘
            │  REST (JSON)
┌───────────▼─────────────┐
│  FastAPI      :8000     │   api_server.py
│  routes + wake-word     │   validation, CORS, background thread
│  thread                 │
└───────────┬─────────────┘
            │
┌───────────▼─────────────┐
│  Command router         │   main.py
│  prefix → exact →       │   resolves free-form speech to a function
│  longest-first substring│
└───────────┬─────────────┘
            │
┌───────────▼─────────────┐
│  Dispatch table         │   command_map.py
│  159 phrases → funcs    │   pure data, no logic
└───────────┬─────────────┘
            │
┌───────────▼─────────────┐
│  Action layer           │   actions.py
│  pyautogui / subprocess │   ~90 zero-argument functions
│  ctypes / smtplib       │
└───────────┬─────────────┘
            │
┌───────────▼─────────────┐
│  Speech I/O             │   core.py
│  STT (Google) + TTS     │   the only file touching mic/speakers
└─────────────────────────┘
```

The layering is strict: `core` knows nothing about commands, `actions` knows
nothing about matching, `command_map` holds no logic, and `api_server` knows
nothing about how a command executes. The UI can be replaced without touching
any of it — as it was, when the original React front end was swapped for
Streamlit.

---

## Tech stack

| Layer | Technology |
|---|---|
| Web framework | FastAPI + Pydantic |
| ASGI server | Uvicorn |
| Front end | Streamlit |
| Speech-to-text | SpeechRecognition → Google Web Speech API (`en-IN`) |
| Audio capture | PyAudio (PortAudio) |
| Text-to-speech | pyttsx3 → Windows SAPI5 (offline) |
| GUI automation | PyAutoGUI |
| Media keys | `keyboard` |
| System info | psutil |
| OS integration | ctypes (`user32.dll`, `PowrProf.dll`), subprocess, `ms-settings:` URIs |
| Email | smtplib over Gmail SMTP SSL |
| Concurrency | threading (daemon wake-word loop) |

Speech recognition is the only cloud dependency. Every automation action runs
locally and offline.

---

## Project structure

```
Voice-Assisstant-Task-Automation/
├── core.py              Speech I/O — recognize_speech() and speak()
├── actions.py           ~90 automation functions (the capability layer)
├── command_map.py       COMMANDS dict: 159 spoken phrases → functions
├── main.py              Command router; also runs standalone as a CLI
├── api_server.py        FastAPI app — 5 REST endpoints + wake-word thread
├── streamlit_app.py     Streamlit UI (thin HTTP client)
├── voice_assistant.py   Legacy standalone CLI (superseded; see Known issues)
├── requirements.txt
└── frontend-react/      Previous React + Vite UI, kept for reference
```

---

## Setup

**Requirements:** Windows 10/11, Python 3.11+, a working microphone, and an
internet connection (for speech recognition).

```bash
git clone https://github.com/Khushi-gehlot/SKIT-DS-2023-2027-30.git
cd SKIT-DS-2023-2027-30
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

If `PyAudio` fails to build, install a prebuilt wheel instead:
`pip install pipwin && pipwin install pyaudio`

### Environment variables

Email support needs a Gmail account with 2-Step Verification enabled and an
[App Password](https://myaccount.google.com/apppasswords). Create a `.env` file
in the project root:

```
SENDER_EMAIL=your-address@gmail.com
SENDER_APP_PASSWORD=your-16-character-app-password
```

Never commit `.env`. Every other feature works without it.

---

## Running

Two processes, in two terminals.

**Backend:**

```bash
python -m uvicorn api_server:app --reload --port 8000
```

**Front end:**

```bash
python -m streamlit run streamlit_app.py
```

| Service | URL |
|---|---|
| Streamlit UI | http://localhost:8501 |
| REST API | http://localhost:8000 |
| Interactive API docs | http://localhost:8000/docs |

Some commands need elevation: media and volume keys are sent as low-level
scancodes, which Windows blocks for non-elevated processes in certain contexts.
Run the backend as administrator if those do nothing.

---

## Usage

**Voice.** Click *Start listening session*, say a wake word, then give commands
one after another. Say "sleep" to end the session.

**Always-on.** Start it from the sidebar and the assistant listens for the wake
word continuously in the background.

**Typed.** Use the command box or the quick-command buttons — these bypass
speech recognition entirely and are the reliable way to demonstrate the system.

### Example commands

| Category | Examples |
|---|---|
| Apps | `open notepad`, `calculator`, `task manager`, `command prompt` |
| Folders | `open downloads`, `documents`, `this pc`, `pictures` |
| Settings | `display settings`, `wifi settings`, `bluetooth`, `windows update` |
| Windows | `show desktop`, `minimise`, `close window`, `switch window` |
| Cursor | `move up`, `click`, `double click`, `scroll down` |
| Media | `volume up`, `mute`, `play music`, `next song` |
| Web | `open youtube`, `search google for python tutorials` |
| System | `battery`, `take screenshot`, `lock`, `shutdown` |
| Email | `send email` (then dictate recipient, subject and body) |

Commands are matched inside a sentence, so "please open notepad now" works.

---

## API reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/commands` | List all supported command keywords |
| `POST` | `/api/command` | Execute a typed command — body: `{"command": "open notepad"}` |
| `POST` | `/api/listen` | Listen for a wake word, then run a command session |
| `POST` | `/api/always_on/start` | Start the background wake-word thread |
| `POST` | `/api/always_on/stop` | Stop it |

CORS is restricted to the local front-end origins.

---

## How command matching works

`process_command()` resolves free-form speech in three stages:

1. **Prefix commands with an argument** — `search google for cats`,
   `open website github.com` — parsed by splitting on the prefix.
2. **Exact dictionary lookup** — O(1), handles clean input.
3. **Substring scan, longest key first** — so "please open notepad now" matches,
   and specific phrases beat the generic ones that contain them.

Stage 3's ordering matters more than it looks. Scanning in dictionary insertion
order meant `"settings"` matched before all 30 specific settings commands, and
`"click"` before `"double click"` — 60 of 159 commands were unreachable. Sorting
candidate keys by descending length fixes all of them.

Adding a command takes two steps: write a zero-argument function in `actions.py`,
then add one or more phrases to `COMMANDS` in `command_map.py`.

---

## Known issues and limitations

- **No authentication on the API.** Anything that can reach port 8000 can drive
  the machine, including shutting it down. CORS is the only restriction. Not
  safe to expose beyond localhost.
- **`mute` and `unmute` send the same keypress** — it is a toggle, so "unmute"
  mutes an already-unmuted system. Reading real volume state needs `pycaw`.
- **Matching has no fuzzy fallback.** "turn up the volume" fails where
  "volume up" works.
- **Streamlit blocks during a listening session** until a sleep word is heard;
  this follows from Streamlit's synchronous rerun model.
- **`voice_assistant.py` is superseded** and contains a stale duplicate of the
  router. Nothing imports it.
- **Speech recognition requires internet** and is accuracy-limited by the
  5-second capture window and ambient noise.

## Possible future work

Fuzzy matching (RapidFuzz) for natural phrasing; API key authentication;
offline speech recognition (Vosk or Whisper) to remove the cloud dependency;
per-user configurable wake words; a command usage log.

---

## Security note

Credentials belong in `.env`, never in source. If a credential is ever committed,
removing it from the file is not enough — it stays in Git history and must be
revoked at the provider.

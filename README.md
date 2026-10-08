# VyasOS — Voice Assistant for Task Automation

A hands-free desktop assistant for Windows, built as an **accessibility tool**.
The goal is that someone who cannot comfortably use a mouse and keyboard can
still operate the whole machine by voice — open apps, change system settings,
move and click the cursor, manage volume and media, browse the web, and send
email, without touching the hardware.

Speak a wake word, give a command, and the machine does it.

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
- **Browser control** — a Playwright-driven browser that can act *inside* a web
  page, not just open it (see below).

### Two levels of web control

The project deliberately keeps both, because they solve different problems.

**`webbrowser` (standard library)** — hands a URL to the default browser and
forgets about it. Instant, no dependencies. Right for "open youtube",
"search google for X". It cannot see or touch the page afterwards.

**Playwright (`browser_actions.py`)** — drives a real Chromium window the
assistant stays in control of. This is what makes genuinely hands-free browsing
possible, because the hard part of using the web without a mouse is not opening
a page, it is everything after: clicking the right link, scrolling to the right
place, choosing an option, reading content back.

Currently implemented:

| Command | What it does |
|---|---|
| `browser_open(url)` | Navigate the controlled browser |
| `browser_search_google(query)` | Search without leaving the session |
| `browser_search_youtube(query)` | Search YouTube |
| `browser_play_first_youtube_result(query)` | Search, wait for results, **click the first video** |
| `browser_page_title()` | Read the current page title aloud |
| `browser_close()` | Close the browser |

A single Chromium window is launched on first use and reused, so the user keeps
one continuous session rather than a new window per command. The browser runs
visibly (`headless=False`) so the user can see what the assistant is doing.

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
│
│   # the contract everything shares
├── intent.py            Intent, ExecutionResult, AuthResult dataclasses
├── config.py            wake words, timeouts, thresholds — no logic
│
│   # the four interfaces
├── core.py              transcribe(), listen(), speak()      — speech I/O
├── nlu/                 get_intent()                         — text → Intent
│   ├── keyword.py         deterministic phrase matching (offline fallback)
│   └── llm.py             free-speech understanding (Sprint 1, empty)
├── auth.py              authenticate()                       — speaker verification (Sprint 2, stub)
├── executor.py          execute()                            — Intent → action, registry dispatch
│
│   # orchestration and capabilities
├── pipeline.py          wires the four together
├── actions.py           ~90 OS automation functions
├── browser_actions.py   Playwright browser control
├── command_map.py       159 phrases → (action, target). Pure data.
│
│   # entry points
├── streamlit_app.py     Streamlit UI (single process)
├── main.py              CLI; also keeps process_command() for compatibility
├── api_server.py        FastAPI adapter over the same pipeline
│
├── tools/               mic diagnostics, not part of the app
├── requirements.txt
└── frontend-react/      previous React + Vite UI, kept for reference
```

### The interfaces

Each stage is replaceable because they share only the `Intent` contract —
no stage imports another's implementation.

```
audio ──transcribe()──> text ──get_intent()──> Intent ──authenticate()──> Intent ──execute()──> Result
       core.py                nlu/                     auth.py                    executor.py
```

An `Intent` is a plain description of what the user wants, created *before*
anything happens, so it can be logged, confirmed or rejected first:

```json
{
  "action": "open_app",
  "target": "notepad",
  "params": {},
  "confidence": 1.0,
  "raw_text": "please open notepad",
  "source": "voice",
  "engine": "keyword",
  "sensitive": false
}
```

The field names match what the LLM intent engine is specified to emit, so the
keyword matcher and the LLM are drop-in replacements for one another.
`sensitive` is what lets speaker verification challenge "shutdown" without
challenging "scroll down".

New capabilities register themselves rather than editing a dispatcher:

```python
@handler("open_app")
def _open_app(intent): ...
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

### Browser automation (Playwright)

`pip install -r requirements.txt` installs the `playwright` Python package, but
that package is only a client. The browser engine it drives is a separate
download and **must be installed with a second command**:

```bash
python -m playwright install chromium
```

Roughly 120 MB, one time. Without it, every browser command fails with
"Playwright is not set up yet" — the rest of the assistant is unaffected.

**Dependencies pulled in by `playwright`:**

| Package | Role |
|---|---|
| `playwright` | Python client library (the API used in `browser_actions.py`) |
| `greenlet` | Lets the synchronous API block on async operations |
| `pyee` | Event emitter used for browser events |
| Node.js driver | Bundled inside the `playwright` wheel; no separate install |
| Chromium | The actual browser — the 120 MB download above |

Notes:

- If the install reports a failure for **Chrome Headless Shell**, ignore it.
  The assistant launches a visible browser (`headless=False`), so the headless
  component is not used.
- Browsers are cached in `%LOCALAPPDATA%\ms-playwright`, outside the project,
  so they survive deleting and recreating the virtual environment.
- Only Chromium is needed. `python -m playwright install` with no argument
  would also fetch Firefox and WebKit, roughly 400 MB for no benefit here.

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

## Roadmap

### In-page browsing by voice

The accessibility goal is that a user never needs the mouse. Opening a page is
solved; acting within it is the remaining work. Planned commands, all of which
Playwright supports and `webbrowser` cannot:

| Spoken command | Playwright mechanism |
|---|---|
| "open the first link" | `page.locator("a").first.click()` |
| "scroll down" / "scroll up" | `page.mouse.wheel()` — scrolls the page, not the OS |
| "click sign in" | `page.get_by_role("button", name="sign in").click()` |
| "select the second option" | `page.locator("option").nth(1).select_option()` |
| "type my email" | `page.get_by_label("Email").fill(...)` |
| "read this page to me" | `page.inner_text("main")` piped through `speak()` |
| "go back" / "go forward" | `page.go_back()` / `page.go_forward()` |
| "show me the links" | enumerate links and number them, then "click number three" |

The numbered-links idea matters most: naming a link out loud is unreliable, so
listing visible links with numbers and letting the user pick one by number is
far more robust for someone who cannot point at the screen.

Note that today's "scroll down" command uses PyAutoGUI, which scrolls whatever
window has OS focus. The Playwright version would scroll a specific page
deterministically — more reliable, and it works even if focus moves.

### Other

Fuzzy matching (RapidFuzz) for natural phrasing; offline speech recognition
(Vosk or Whisper) to remove the cloud dependency and improve proper-noun
accuracy; a screen-reader-friendly UI mode; per-user configurable wake words;
dwell-free confirmation for destructive actions; a command usage log.

---

## Security note

Credentials belong in `.env`, never in source. If a credential is ever committed,
removing it from the file is not enough — it stays in Git history and must be
revoked at the provider.

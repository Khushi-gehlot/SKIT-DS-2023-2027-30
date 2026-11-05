"""
Tunable constants, in one place.

Anything a developer might reasonably want to change without reading code
belongs here: wake words, timeouts, thresholds, device selection. Modules
import from here rather than hard-coding values, so there is one obvious place
to look when behaviour needs adjusting.
"""

import os
from pathlib import Path

# Load .env if python-dotenv is available. The file sits at the project root,
# one level above this module, so look there as well as in the usual places.
try:
    from dotenv import load_dotenv

    for _candidate in (
        Path(__file__).parent / ".env",
        Path(__file__).parent.parent / ".env",
    ):
        if _candidate.is_file():
            load_dotenv(_candidate)
            break
except ImportError:
    pass


# =============== MICROPHONE / SPEECH ===============

# Pin a specific input device by index (see core.list_microphones()).
# Unset means PyAudio's default device.
_mic = os.environ.get("VYAS_MIC_INDEX")
MIC_INDEX: int | None = int(_mic) if _mic and _mic.isdigit() else None

LISTEN_TIMEOUT = 8          # seconds to wait for speech to start
PHRASE_TIME_LIMIT = 8       # maximum length of a single utterance
PAUSE_THRESHOLD = 1.2
# Audio kept from before the trigger fires. Speech ramps up, so without a
# generous pre-roll the opening syllable is lost. Must stay below
# PAUSE_THRESHOLD.
PRE_SPEECH_BUFFER = 0.9       # silence that marks the end of a phrase
# 0.8 was too eager: a natural beat between "hello" and the name ended the
# utterance, so the recogniser only ever heard "hello".
CALIBRATION_SECONDS = 1.0   # ambient-noise sampling on first listen

# A dead or muted device calibrates to ~0, which would make the recogniser
# trigger on nothing at all. Never go below this.
MIN_ENERGY_THRESHOLD = 100

# The recogniser adapts its threshold as it listens, which is useful, but it
# only ever drifts upward in a room with background noise or an assistant that
# talks through speakers. These two settings stop it going permanently deaf:
# recalibrate from scratch every so often, and never let the threshold exceed
# a level a normal speaking voice can clear.
RECALIBRATE_EVERY = 15      # listens between full recalibrations
MAX_ENERGY_THRESHOLD = 1200

STT_LANGUAGE = "en-IN"


# =============== SPEECH TO TEXT ENGINE ===============
#
# "whisper" runs locally - no internet, no API key, and markedly better with
# proper nouns and Indian-accented English. Google transcribed "vyas" as
# "guys" every single time, which is what broke the wake word.
#
# "google" is the old cloud engine, kept commented in core.py so the two can
# be compared for the report.
STT_ENGINE = os.environ.get("VYAS_STT", "whisper").lower()

# tiny / base / small / medium / large-v3.
#   tiny  ~75 MB   fastest, noticeably worse with names
#   base  ~145 MB  the sweet spot for a voice assistant
#   small ~480 MB  better, around 2-3x slower on CPU
WHISPER_MODEL = os.environ.get("VYAS_WHISPER_MODEL", "base")

# int8 keeps CPU inference fast with very little accuracy cost. Use "float16"
# with device="cuda" if a GPU is available.
WHISPER_DEVICE = os.environ.get("VYAS_WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.environ.get("VYAS_WHISPER_COMPUTE", "int8")

# Forcing the language stops Whisper guessing wrong on short utterances -
# "volume up" is sometimes detected as Welsh otherwise.
WHISPER_LANGUAGE = os.environ.get("VYAS_WHISPER_LANG", "en")

# Whisper hallucinates on silence, confidently returning things like "Thank
# you." or "Thanks for watching!" when it hears nothing. These are discarded.
WHISPER_HALLUCINATIONS = {
    "thank you", "thanks for watching", "thank you.", "thanks for watching!",
    "you", ".", "bye", "bye.", "thanks", "thank you for watching",
    "subtitles by the amara.org community", "please subscribe",
}


# =============== WAKE WORD ===============
#
# The wake name is "nova": two syllables, open vowels, no consonant clusters,
# and a common English word that recognisers already have a strong prior for.
# It also shares no sounds with any command in command_map, so it cannot be
# confused with "scroll", "close" or "go".
#
# This matters more than it sounds. "vyas" was transcribed as "guys" by both
# Google and Whisper essentially every time, so the wake word almost never
# matched and the assistant appeared deaf.
#
# Speech-to-text still rarely returns a name verbatim, so a greeting followed
# by any plausible rendering of the name is accepted.

GREETINGS = ["hello", "hey", "hi", "ok", "okay", "yo"]

NAME_VARIANTS = [
    # the name and its spelling variants
    "nova", "novah", "nowva", "noval",
    # what recognisers actually returned in testing. These are not guesses:
    # "nova" came back as "nover" and "nowa", and "okay nova" merged into
    # "okinawa". Google hears the sounds correctly and picks the wrong words,
    # so the variants have to cover its choices rather than our spelling.
    "nover", "nowa", "noba", "nava", "nobo", "knowva", "novo", "nouveau",
    "okinawa", "kinawa", "innova", "nirvana",
    # kept so the earlier wake words still work for anyone used to them
    "coco", "cocoa", "vyas", "vias", "bhai",
]

WAKE_WORDS = [f"{g} {n}" for g in GREETINGS for n in NAME_VARIANTS]

# "nova" on its own wakes it, no greeting needed - one word beats two for a
# user who finds speaking effortful.
WAKE_WORDS += ["nova", "novah", "nover", "no va", "nowa", "coco"]

SLEEP_WORDS = [
    "sleep", "go to sleep", "stop listening", "goodbye", "good night",
]


# =============== WAKE-WORD ENGINE ===============
#
# "openwakeword" uses a neural network trained on one phrase, scoring raw
# audio directly. "keyword" is the old route - transcribe everything, then
# look for the name in the text - kept as the fallback and for comparison
# in the report.
#
# The dedicated model is not a tuning improvement over keyword matching, it
# is a different approach. Transcription asks "what words were said?" and
# then hopes the name survived; the model asks only "did this phrase
# occur?". It also means audio stops being streamed to a speech service
# while nobody is talking to the assistant.

WAKE_ENGINE = os.environ.get("VYAS_WAKE_ENGINE", "openwakeword").lower()

# Pretrained models that ship with openWakeWord: alexa, hey_mycroft,
# hey_jarvis, hey_rhasspy, timer, weather.
#
# "hey_jarvis" is used because there is no pretrained model for "nova" -
# that one has to be trained, which is the next step. Swapping to a custom
# model is a change to this line and nothing else.
WAKE_MODEL = os.environ.get("VYAS_WAKE_MODEL", "hey_jarvis")

# onnx runs everywhere; tflite is marginally faster where it is available.
WAKE_INFERENCE = os.environ.get("VYAS_WAKE_INFERENCE", "onnx")

# Score above which the phrase counts as heard, 0.0 to 1.0.
#
# 0.25, not openWakeWord's default of 0.5. That is a measurement, not a
# preference: across a test session the phrase peaked at 0.50, 0.43, 0.41,
# 0.34, 0.23 and 0.16, while seventeen seconds of room noise and ordinary
# speech never exceeded 0.002. The gap between signal and noise is about a
# hundredfold, so the sensible place to cut is low in that gap rather than
# in the middle of the detections.
#
# The model scores lower than its default assumes because it was trained
# largely on synthetic English speech; accents outside that range clear the
# bar by less. Lowering the threshold costs nothing here - there is simply
# nothing between 0.002 and 0.16 to be confused by.
#
# tools/wake_test.py prints live scores. Re-run it after changing the
# microphone or the room and choose from your own numbers.
WAKE_THRESHOLD = float(os.environ.get("VYAS_WAKE_THRESHOLD", "0.25"))

# The model expects 80ms of 16 kHz mono audio per frame.
WAKE_FRAME_SAMPLES = 1280
WAKE_SAMPLE_RATE = 16000

# The score stays high for several frames as the phrase finishes, so one
# "hey jarvis" would otherwise trigger three or four times.
WAKE_COOLDOWN_SECONDS = 2.0

# What to call the wake phrase in messages shown to the user. Derived from
# the model name so the two cannot drift apart.
WAKE_PHRASE = WAKE_MODEL.replace("_", " ")


# =============== CONVERSATION ===============
#
# What the assistant says, and what it accepts as an answer. Kept here so the
# personality can be adjusted without touching logic.

USER_TITLE = "admin"        # what the assistant calls the user

GREETINGS_SPOKEN = [
    "Hey {user}, how can I help you?",
    "Yes {user}, what would you like me to do?",
    "I'm listening, {user}.",
]

ACKNOWLEDGEMENTS = ["Done.", "Got it.", "Okay.", "Sure."]

NOT_UNDERSTOOD = [
    "Sorry, I did not catch that.",
    "I did not understand that one.",
]

FAREWELLS = ["Going back to sleep.", "Okay, let me know if you need me."]

# Answers to "did you mean X?". Matched as whole words so "no" inside another
# word cannot flip a yes into a no.
YES_WORDS = [
    "yes", "yeah", "yep", "yup", "correct", "right", "sure", "ok", "okay",
    "do it", "go ahead", "confirm", "haan", "ha",
]

NO_WORDS = [
    "no", "nope", "nah", "wrong", "cancel", "stop", "never mind",
    "nevermind", "forget it", "nahi",
]

# How long to wait for a yes/no before giving up on the question.
CONFIRM_TIMEOUT = 6

# Start listening for the wake word as soon as the app opens, so the first
# thing a user can do is speak. For someone who cannot comfortably reach a
# mouse, needing to click a button before they can talk defeats the point.
AUTO_START_LISTENING = True

# Consecutive silences before a button-started session gives up. The page is
# blocked while it runs, so it cannot listen indefinitely.
SESSION_SILENCE_LIMIT = 3

# The same, for the always-on conversation. Higher than the button session
# because nothing is blocked while it waits: the cost of staying awake a
# little longer is nil, and a user who is slow to speak - which is the whole
# audience for this - should not have to say the wake word again.
CONVERSATION_SILENCE_LIMIT = 5

# Pause before retrying when waiting for the wake word returned instantly,
# which means it is not actually waiting - a model that failed to load, or
# a microphone that has disappeared. Stops the loop spinning a core.
WAKE_RETRY_SECONDS = 1.0

# Most steps a single sentence may be split into. A sentence that appears
# to contain six commands has almost certainly been mis-split rather than
# genuinely asked for, and running six wrong things is far worse than
# running one.
MAX_CHAINED_COMMANDS = 4

# Pause between the steps of a chained command, so each one has landed
# before the next starts. A browser launched by step one is not ready to
# be typed into the instant the launch call returns.
STEP_SETTLE_SECONDS = 1.2

# How close a short utterance must be to the name to count as the wake word.
# 1.0 is exact; lower accepts more mishearings but risks waking on nothing.
WAKE_FUZZY_CUTOFF = 0.7

# How many words from the start of an utterance are checked for the name.
# People say it first - "nova, open notepad" - so looking only at the
# opening catches a mangled name without letting a chance resemblance
# later in a sentence wake the assistant.
WAKE_SEARCH_WORDS = 3

# "nova" is frequently transcribed as "google". The word therefore has to be
# accepted as the name - but only when the surrounding words show it is not
# being used as the search engine, or every "search google for X" would wake
# the assistant.
GOOGLE_AS_ENGINE_BEFORE = {
    "search", "open", "on", "in", "to", "via", "using", "ask", "from",
    "launch", "start", "goto", "visit",
}
GOOGLE_AS_ENGINE_AFTER = {
    "search", "for", "dot", "com", "maps", "images", "drive", "docs",
    "translate", "photos", "news", "calendar", "meet", "chrome",
}

# Pause after the assistant finishes speaking before opening the microphone.
# Without it the tail of its own voice bleeds into the recording and the
# recogniser hears the assistant instead of the user.
SPEAK_SETTLE_SECONDS = 0.4


# =============== NLU ===============

# Below this the assistant asks "did you mean X?" instead of acting.
#
# Deliberately above CONFIDENCE_PARTIAL, so a phrase merely *contained* in a
# longer sentence gets confirmed rather than executed. "please open the
# notepad thing" is probably right - but probably is not good enough when the
# user may not be able to undo a wrong action quickly.
MIN_CONFIDENCE = 0.85

# Confidence reported by the keyword matcher for each match type.
CONFIDENCE_EXACT = 1.0      # the whole utterance is a known phrase
CONFIDENCE_PARTIAL = 0.8    # a known phrase appears inside a longer sentence

# Use the LLM engine for anything the keyword matcher cannot place exactly.
# Defaults to on; it switches itself off automatically when no API key is set,
# so this only needs changing to force the keyword engine during testing.
USE_LLM_INTENT = os.environ.get("VYAS_USE_LLM", "1").lower() in ("1", "true", "yes")

# Try the keyword matcher first and skip the LLM when it finds an exact phrase.
#
# Off. The fast path saves a round trip on phrases that are already written
# down, but it only fires on an *exact* match, so every natural variation -
# "just type hello", "jarvis, open the second one" - fell through to regex
# rules that had to anticipate the wording. Adding a rule per phrasing does
# not scale, and each one is a new way to be wrong.
#
# Sending everything to the model costs latency on commands that would have
# been instant, and that is a real cost. It buys understanding of phrasings
# nobody wrote down, which is the whole reason the model is here. The
# keyword matcher remains the fallback, so losing the network narrows the
# vocabulary rather than stopping the assistant.
KEYWORD_FAST_PATH = os.environ.get("VYAS_KEYWORD_FAST_PATH", "0").lower() in (
    "1", "true", "yes"
)


# =============== LLM INTENT ENGINE ===============
#
# Mistral's free tier is enough for this: small models, generous limits, and no
# card required. Get a key at https://console.mistral.ai and put it in .env as
#     MISTRAL_API_KEY=...

# Several providers are supported; the first with a key is used, in the
# order listed in nlu/llm.py. They all speak the OpenAI-compatible
# /chat/completions shape, so supporting more than one costs almost nothing.

# Groq: free, no card, no phone verification, and fast enough that the user
# does not notice the round trip. Preferred.
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
# Model availability varies by account. List yours with:
#     GET https://api.groq.com/openai/v1/models
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")

# Hugging Face: free, but idle models cold-start, which can mean a 20-30
# second wait on the first request.
HF_API_KEY = os.environ.get("HF_API_KEY", "").strip()
# The Inference Providers router. Override with your own endpoint URL in
# .env if you deploy a dedicated Inference Endpoint instead.
HF_API_URL = os.environ.get(
    "HF_API_URL", "https://router.huggingface.co/v1/chat/completions"
)

# DeepSeek-R1 reasons out loud before answering. The client strips the
# <think> block and allows a larger token budget for it - see
# LLM_REASONING_MAX_TOKENS. Expect it to be slower than a plain instruct
# model, because most of what it generates is deliberation rather than
# answer.
HF_MODEL = os.environ.get("HF_MODEL", "deepseek-ai/DeepSeek-R1")

# Google Gemini: free, no card, and exposed through an OpenAI-compatible
# endpoint so it needs no special client. Daily and per-minute quotas apply
# and Google no longer publishes exact free-tier figures - check the quota
# page in AI Studio for this project's own limits.
#     https://aistudio.google.com/apikey
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_API_URL = os.environ.get(
    "GEMINI_API_URL",
    "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
)
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# Ollama: a model running on this machine. No key, no quota, no network, and
# nothing to expire - which is why it sits last in the chain as the provider
# that is still there when every hosted free tier has run out. It is also
# the only option that keeps command text on the user's own computer.
#     https://ollama.com/download  then:  ollama pull llama3.2:3b
OLLAMA_ENABLED = os.environ.get("VYAS_OLLAMA", "0").lower() in ("1", "true", "yes")
OLLAMA_API_URL = os.environ.get(
    "OLLAMA_API_URL", "http://localhost:11434/v1/chat/completions"
)
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")

# When a command cannot be placed from its words alone and a browser is
# open, show the model the page's links and fields and ask again.
#
# "open the one about pricing" carries no information about which link that
# is - the answer is on the screen. Only reached after the ordinary engine
# has given up, so it costs nothing on commands that already work.
PAGE_AWARE_INTENT = os.environ.get("VYAS_PAGE_AWARE", "1").lower() in (
    "1", "true", "yes"
)

MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "").strip()
MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"

# mistral-small is fast and cheap and this is a classification task, not a
# reasoning one. Upgrading the model is a one-line change.
MISTRAL_MODEL = os.environ.get("MISTRAL_MODEL", "mistral-small-latest")

# Keep this tight. A voice assistant that pauses for several seconds is worse
# than one that quietly falls back to keyword matching.
LLM_TIMEOUT = float(os.environ.get("VYAS_LLM_TIMEOUT", "8"))

# Deterministic output. This is classification, so creativity is a defect.
LLM_TEMPERATURE = 0.0
LLM_MAX_TOKENS = 200

# Reasoning models (DeepSeek-R1 and similar) emit their deliberation before
# the answer, inside a <think> block the client strips. That thinking comes
# out of the same budget, so the ordinary 200 would truncate the reply
# before any JSON appeared.
LLM_REASONING_MAX_TOKENS = int(os.environ.get("VYAS_LLM_REASONING_TOKENS", "1200"))

# And they need longer to answer, for the same reason.
LLM_REASONING_TIMEOUT = float(os.environ.get("VYAS_LLM_REASONING_TIMEOUT", "40"))

# Which provider to try first, by name: groq, gemini, mistral, huggingface
# or ollama. Unset means the order written in nlu/llm.py. Set this to pin a
# particular provider without removing the others, so the rest stay as
# fallbacks when it is rate-limited or down.
LLM_PROVIDER = os.environ.get("VYAS_LLM_PROVIDER", "").strip().lower()

# Below this the LLM's answer is discarded in favour of the keyword matcher.
LLM_MIN_CONFIDENCE = 0.5

# Below this the link resolver's answer is discarded and word matching is
# used instead. Set higher than the intent threshold on purpose: a wrong
# intent usually just opens the wrong window, while a wrong link navigates
# away from whatever the user was reading.
LINK_MIN_CONFIDENCE = 0.6


# =============== AUTHENTICATION ===============

# Speaker verification is not implemented yet; until it is, everything is
# allowed through. Set to True once enrolment exists.
REQUIRE_SPEAKER_VERIFICATION = True

# Cosine similarity above which a voice is accepted as the enrolled speaker.
#
# 0.75 is a deliberate middle: Resemblyzer typically scores the same speaker
# around 0.80-0.95 and different speakers around 0.50-0.70. Raise it to make
# impersonation harder at the cost of rejecting the real user more often;
# lower it to be more forgiving. For an accessibility tool a false rejection
# is an inconvenience, while a false acceptance could mean a stranger
# shutting the machine down - so err high rather than low.
SPEAKER_SIMILARITY_THRESHOLD = float(
    os.environ.get("VYAS_SPEAKER_THRESHOLD", "0.75")
)

# Recordings shorter than this carry too little voice to identify anyone.
MIN_VOICE_SECONDS = 1.2

# How many phrases enrolment collects. Averaging several captures the user
# on more than one breath, so verification still works when they are tired
# or sitting further from the microphone.
ENROLMENT_SAMPLES = 4

# What the user is asked to say while enrolling. Varied on purpose: phrases
# with different sounds give the encoder more to work with than one repeated
# sentence.
ENROLMENT_PHRASES = [
    "Nova, this is my voice.",
    "Open my downloads folder.",
    "The quick brown fox jumps over the lazy dog.",
    "Lock the computer when I am away.",
]


# =============== VOICEPRINT STORAGE ===============
#
# "mongodb" keeps voiceprints in a database; "json" keeps them in a file
# beside the code. MongoDB is the default, and the store falls back to the
# file by itself when no database is reachable - so the assistant still
# works on a machine where MongoDB was never installed.

VOICEPRINT_BACKEND = os.environ.get("VYAS_VOICEPRINT_BACKEND", "mongodb").lower()

# A local server by default. Deliberately local rather than hosted: a
# voiceprint is biometric data, and keeping it on the user's own machine is
# a far easier promise to keep than keeping it on someone else's.
#
# An Atlas cluster works unchanged - put the full SRV string in .env as
#     MONGO_URI=mongodb+srv://user:password@cluster.mongodb.net/
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.environ.get("MONGO_DB", "vyasa")
MONGO_COLLECTION = os.environ.get("MONGO_COLLECTION", "voiceprints")

# pymongo connects lazily and waits 30 seconds by default before admitting a
# server is down. That is an unacceptable pause in front of a microphone, so
# give up quickly and fall back to the file.
MONGO_TIMEOUT_MS = int(os.environ.get("VYAS_MONGO_TIMEOUT_MS", "2000"))

# Used when MongoDB is unavailable. Beside the code, never in the repo -
# see .gitignore.
VOICEPRINT_FILE = Path(__file__).parent / "voiceprints.json"


# =============== HUD ===============
#
# Location for the weather panel. Open-Meteo needs no API key, only
# coordinates. Override in .env if the assistant is used elsewhere.
WEATHER_LAT = float(os.environ.get("VYAS_LAT", "26.9124"))
WEATHER_LON = float(os.environ.get("VYAS_LON", "75.7873"))
WEATHER_CITY = os.environ.get("VYAS_CITY", "Jaipur")

# Shown in the header bar.
USER_NAME = os.environ.get("VYAS_USER_NAME", "Khushi")

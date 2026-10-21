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
PAUSE_THRESHOLD = 1.2       # silence that marks the end of a phrase
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
    "nova", "novah", "nova.",
    # near-misses recognisers produce for it
    "nover", "nowa", "noba", "nava", "no va", "nova,", "nobo", "knowva",
    # kept so the earlier wake words still work for anyone used to them
    "coco", "cocoa", "vyas", "vias", "guys", "bhai",
]

WAKE_WORDS = [f"{g} {n}" for g in GREETINGS for n in NAME_VARIANTS]

# "nova" on its own wakes it, no greeting needed - one word beats two for a
# user who finds speaking effortful.
WAKE_WORDS += ["nova", "novah", "nover", "no va", "nowa", "coco"]

SLEEP_WORDS = [
    "sleep", "go to sleep", "stop listening", "goodbye", "good night",
]


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

# Consecutive silences before a button-started session gives up. The page is
# blocked while it runs, so it cannot listen indefinitely.
SESSION_SILENCE_LIMIT = 3

# How close a short utterance must be to the name to count as the wake word.
# 1.0 is exact; lower accepts more mishearings but risks waking on nothing.
WAKE_FUZZY_CUTOFF = 0.7

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
# "open notepad" does not need a model, and not paying latency on the common
# case is the difference between the assistant feeling instant and feeling slow.
KEYWORD_FAST_PATH = True


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
HF_API_URL = "https://router.huggingface.co/v1/chat/completions"
HF_MODEL = os.environ.get("HF_MODEL", "meta-llama/Llama-3.3-70B-Instruct")

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

# Below this the LLM's answer is discarded in favour of the keyword matcher.
LLM_MIN_CONFIDENCE = 0.5


# =============== AUTHENTICATION ===============

# Speaker verification is not implemented yet; until it is, everything is
# allowed through. Set to True once enrolment exists.
REQUIRE_SPEAKER_VERIFICATION = False

# Cosine similarity above which a voice is accepted as the enrolled speaker.
SPEAKER_SIMILARITY_THRESHOLD = 0.75


# =============== HUD ===============
#
# Location for the weather panel. Open-Meteo needs no API key, only
# coordinates. Override in .env if the assistant is used elsewhere.
WEATHER_LAT = float(os.environ.get("VYAS_LAT", "26.9124"))
WEATHER_LON = float(os.environ.get("VYAS_LON", "75.7873"))
WEATHER_CITY = os.environ.get("VYAS_CITY", "Jaipur")

# Shown in the header bar.
USER_NAME = os.environ.get("VYAS_USER_NAME", "Khushi")

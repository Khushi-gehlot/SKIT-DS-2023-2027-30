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
PAUSE_THRESHOLD = 0.8       # silence that marks the end of a phrase
CALIBRATION_SECONDS = 1.0   # ambient-noise sampling on first listen

# A dead or muted device calibrates to ~0, which would make the recogniser
# trigger on nothing at all. Never go below this.
MIN_ENERGY_THRESHOLD = 100

STT_LANGUAGE = "en-IN"


# =============== WAKE WORD ===============
#
# Speech-to-text rarely returns "vyas" verbatim - Google transcribes it as
# "guys", "wise", "bias" and so on depending on accent and microphone. Matching
# only the literal spelling meant the wake word almost never fired, so a
# greeting followed by any plausible rendering of the name is accepted.

GREETINGS = ["hello", "hey", "hi", "ok", "okay", "yo"]

NAME_VARIANTS = [
    "vyas", "vyaas", "vias", "viyas", "byas", "wyas",
    "guys", "gas", "grass",          # what the recogniser usually hears
    "wise", "vice", "voice", "bias", "boys", "views",
    "bhai", "bai", "by", "buy", "bye",
]

WAKE_WORDS = [f"{g} {n}" for g in GREETINGS for n in NAME_VARIANTS]

SLEEP_WORDS = [
    "sleep", "go to sleep", "stop listening", "goodbye", "good night",
]


# =============== NLU ===============

# Below this, treat a match as too uncertain to act on and ask again.
MIN_CONFIDENCE = 0.5

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

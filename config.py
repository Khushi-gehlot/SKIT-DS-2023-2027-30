"""
Tunable constants, in one place.

Anything a developer might reasonably want to change without reading code
belongs here: wake words, timeouts, thresholds, device selection. Modules
import from here rather than hard-coding values, so there is one obvious place
to look when behaviour needs adjusting.
"""

import os


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

# Prefer the LLM engine when it is available, falling back to keywords when it
# is unsure or offline. Off until the LLM engine lands.
USE_LLM_INTENT = os.environ.get("VYAS_USE_LLM", "").lower() in ("1", "true", "yes")


# =============== AUTHENTICATION ===============

# Speaker verification is not implemented yet; until it is, everything is
# allowed through. Set to True once enrolment exists.
REQUIRE_SPEAKER_VERIFICATION = False

# Cosine similarity above which a voice is accepted as the enrolled speaker.
SPEAKER_SIMILARITY_THRESHOLD = 0.75

"""
Check which LLM provider is live, how fast it is, and whether it answers.

    python tools/llm_check.py           one request, reports status
    python tools/llm_check.py --full    a set of phrases, with timings

Use the single-request form first. It costs one call, which matters on a
metered account, and tells you whether the key works before you spend any
more of it.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config          # noqa: E402
from nlu import llm    # noqa: E402

# Phrases that are NOT written down in command_map, so the keyword matcher
# cannot resolve them exactly. These are what the model is actually for.
PHRASES = [
    "turn the volume up a bit",
    "I can't hear anything",
    "just type hello how are you",
    "what's my battery like",
    "make this page bigger",
    "shut the browser down",
]


def banner():
    print("=" * 70)
    print("  LLM provider check")
    print("=" * 70)
    providers = llm.configured_providers()
    if not providers:
        print("  No provider has a key. Set one in .env:")
        print("    HF_API_KEY=...   GROQ_API_KEY=...   GEMINI_API_KEY=...")
        return None

    print("  chain (first one is tried first):")
    for position, (name, _key, _url, model) in enumerate(providers, start=1):
        flag = "  <- reasoning model" if llm._is_reasoning_model(model) else ""
        print(f"    {position}. {name:12} {model}{flag}")
    if config.LLM_PROVIDER:
        print(f"  pinned by VYAS_LLM_PROVIDER={config.LLM_PROVIDER}")
    print(f"  keyword fast path: {'on' if config.KEYWORD_FAST_PATH else 'OFF'}")
    if not config.KEYWORD_FAST_PATH:
        print("    every command will reach the model, including ones already")
        print("    in command_map. On a metered account, turn this on:")
        print("    VYAS_KEYWORD_FAST_PATH=1")
    print("-" * 70)
    return providers


def one(text: str) -> bool:
    """Send a single phrase. Returns True if the model answered usefully."""
    start = time.time()
    intent = llm.get_intent(text)
    elapsed = time.time() - start

    ok = intent.is_understood()
    mark = "ok  " if ok else "FAIL"
    print(f"  {mark} {elapsed:6.1f}s  {intent.action:18} "
          f"conf={intent.confidence:.2f} {intent.params}")
    print(f"              {text!r}")
    return ok


def main() -> int:
    if banner() is None:
        return 1

    phrases = PHRASES if "--full" in sys.argv else PHRASES[:1]
    print(f"  sending {len(phrases)} request(s)...")
    print()

    answered = sum(one(text) for text in phrases)

    print()
    print("-" * 70)
    print(f"  {answered}/{len(phrases)} answered")
    if answered == 0:
        print()
        print("  Nothing came back. The message printed above says why:")
        print("    'rejected the API key'   -> wrong or missing token")
        print("    HTTP 402                 -> out of credit; add another")
        print("                                provider or top up")
        print("    'rate limit reached'     -> quota for now, try later")
        print("    'does not offer model'   -> that model is not served;")
        print("                                pick another in HF_MODEL")
    print("=" * 70)
    return 0 if answered else 1


if __name__ == "__main__":
    sys.exit(main())

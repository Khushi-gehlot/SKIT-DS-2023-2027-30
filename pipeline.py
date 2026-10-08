"""
Pipeline orchestration.

Wires the four interfaces into the paths the rest of the app uses, so no UI
has to know the order of the steps:

    text  ->  get_intent()  ->  authenticate()  ->  execute()  ->  result
    audio ->  transcribe()  ->  ... same ...

Each stage is swappable because none of them import each other - they only
share the Intent contract. The LLM engine, Whisper, and speaker verification
all drop in here without this file changing.
"""

from __future__ import annotations

import auth
import core
import executor
import nlu
from intent import ExecutionResult, Intent


def handle_text(text: str, source: str = "text") -> ExecutionResult:
    """
    Run a typed or already-transcribed command through the full pipeline.

    No audio, so speaker verification cannot run - typed commands are trusted
    by definition, which is a deliberate limitation worth remembering when
    sensitive actions are involved.
    """
    intent = nlu.get_intent(text, source=source)
    return _authorise_and_execute(intent, audio=None)


def handle_audio(
    timeout: int | None = None,
    phrase_time_limit: int | None = None,
) -> tuple[ExecutionResult, str | None]:
    """
    Record one utterance and run it through the full pipeline.

    Returns (result, recognised_text) so a UI can show what was heard even
    when nothing could be done with it.
    """
    kwargs = {}
    if timeout is not None:
        kwargs["timeout"] = timeout
    if phrase_time_limit is not None:
        kwargs["phrase_time_limit"] = phrase_time_limit

    text, audio = core.listen(**kwargs)
    if not text:
        return ExecutionResult.fail("I did not catch that."), None

    intent = nlu.get_intent(text, source="voice")
    return _authorise_and_execute(intent, audio=audio), text


def _authorise_and_execute(intent: Intent, audio=None) -> ExecutionResult:
    """Gate the intent, then run it. The only place auth and execution meet."""
    if not intent.is_understood():
        return ExecutionResult.fail(
            f"I do not recognise that command: {intent.raw_text}", intent
        )

    decision = auth.authenticate(intent, audio=audio)
    if not decision.allowed:
        return ExecutionResult.fail(
            decision.message or "Sorry, I could not verify your voice.", intent
        )

    return executor.execute(intent)


def describe() -> dict:
    """What the pipeline is currently made of. Useful for the UI and for docs."""
    import config
    from command_map import ACTIONS

    return {
        "stt": "google",
        "nlu": "llm+keyword" if config.USE_LLM_INTENT else "keyword",
        "auth": "enabled" if config.REQUIRE_SPEAKER_VERIFICATION else "disabled",
        "actions_known": ACTIONS,
        "actions_executable": executor.registered_actions(),
    }

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
    import config

    if not intent.is_understood():
        return ExecutionResult.fail(
            f"I do not recognise that command: {intent.raw_text}", intent
        )

    # Understood, but not firmly enough to act on. Hand it back for the
    # caller to confirm rather than running it.
    #
    # Acting on a weak guess is the wrong trade for this assistant: the user
    # may not be able to undo a wrong action quickly, so asking costs a
    # second and guessing wrong can cost a lot more.
    if intent.confidence < config.MIN_CONFIDENCE:
        return ExecutionResult.confirm(
            f"Sorry, I did not quite catch that. Did you mean {describe_intent(intent)}?",
            intent,
        )

    decision = auth.authenticate(intent, audio=audio)
    if not decision.allowed:
        return ExecutionResult.fail(
            decision.message or "Sorry, I could not verify your voice.", intent
        )

    return executor.execute(intent)


def describe_intent(intent: Intent) -> str:
    """
    Phrase an intent the way a person would say it.

    "open_app/notepad" is not something to read aloud; "open Notepad" is.
    """
    target = (intent.target or "").replace("_", " ").replace("-", " ")
    query = intent.params.get("query") or intent.params.get("text") or ""

    phrasings = {
        "open_app": f"open {target}",
        "open_folder": f"open the {target} folder",
        "open_settings": f"open {target} settings",
        "open_website": f"open {query or target}",
        "search_web": f"search {target} for {query}" if query else f"search {target}",
        "cursor_move": f"move the cursor {target}",
        "cursor_click": f"{target} click",
        "scroll": f"scroll {target}",
        "screenshot": "take a screenshot",
        "window": f"{target} the window".replace("show desktop the window", "show the desktop"),
        "volume": f"turn the volume {target}" if target in ("up", "down") else f"{target} the volume",
        "media": f"{target.replace('play pause', 'play or pause')} the media",
        "power": f"{target} the computer",
        "battery": "check the battery",
        "send_email": "send an email",
    }
    return phrasings.get(intent.action, f"{intent.action} {target}".strip())


def confirm_and_execute(intent: Intent, audio=None) -> ExecutionResult:
    """
    Run an intent the user has just confirmed.

    Skips the confidence check - they have said this is what they meant, so
    the guess is no longer a guess. Authentication still applies.
    """
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

    engines = nlu.active_engines()
    return {
        "stt": "google",
        "nlu": "llm + keyword fallback" if engines["llm"] else "keyword only",
        "llm_provider": engines["llm_provider"],
        "llm_model": engines["llm_model"],
        "llm_ready": engines["llm"],
        "auth": "enabled" if config.REQUIRE_SPEAKER_VERIFICATION else "disabled",
        "actions_known": ACTIONS,
        "actions_executable": executor.registered_actions(),
        "stats": nlu.stats(),
    }

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

import time
from dataclasses import dataclass

import auth
import config
import core
import executor
import nlu
import wakeword
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
        # Nothing in the words placed it. If a browser is open, the answer
        # may be on the screen rather than in the sentence - "open the one
        # about pricing" is meaningless in isolation and obvious to anyone
        # looking at the page. So show the model the page and ask again.
        rescued = _resolve_against_page(intent)
        if rescued is None:
            return ExecutionResult.fail(
                f"I do not recognise that command: {intent.raw_text}", intent
            )
        intent = rescued

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


def _resolve_against_page(intent: Intent) -> Intent | None:
    """
    Second attempt at an unplaceable command, using the live page.

    Imported here rather than at module scope so that nothing in the
    pipeline depends on a browser being installed; if the module or the
    model is missing, this quietly returns None and the caller reports the
    original failure.
    """
    try:
        import page_aware
        return page_aware.resolve(intent.raw_text, source=intent.source)
    except Exception as e:
        print(f"Page-aware resolution unavailable ({type(e).__name__}).")
        return None


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


# =============== THE ALWAYS-ON CONVERSATION ===============
#
# The loop that ties everything together:
#
#     wake word -> greet -> [ transcribe -> intent -> auth -> execute
#                             -> speak ] until a sleep word -> back to sleep
#
# It lives here rather than in the UI because it is not a UI concern. The
# Streamlit page, a CLI, or a test harness all drive the same object; the UI
# only supplies a callback for displaying turns and a flag for stopping.
# That separation is what lets the assistant be tested without a browser,
# and it is the same argument made for swapping STT engines and databases.


@dataclass
class Turn:
    """One exchange, for the caller to display or log."""

    heard: str
    message: str
    success: bool
    kind: str = "command"       # wake | command | confirm | error | sleep


class Conversation:
    """
    An always-on listening session.

    Construction is cheap and has no side effects - nothing opens the
    microphone until run() is called.

    `on_turn`      called after every exchange, for the UI to display
    `should_stop`  polled between steps so a UI can interrupt
    """

    def __init__(self, on_turn=None, should_stop=None):
        self._on_turn = on_turn
        self._should_stop = should_stop or (lambda: False)
        self._silences = 0

    # --- reporting ---

    def _report(self, heard: str, message: str, success: bool, kind="command"):
        if self._on_turn is None:
            return
        try:
            self._on_turn(Turn(heard, message, success, kind))
        except Exception:
            # A broken display callback must not kill the conversation.
            pass

    def _say(self, text: str):
        core.speak(text)

    # --- the loop ---

    def run(self):
        """
        Listen for the wake word, converse, repeat. Returns when stopped.

        Never raises: an exception anywhere inside one turn is reported and
        the loop carries on. An assistant that dies on a single bad command
        is useless to someone who cannot reach the keyboard to restart it.
        """
        while not self._should_stop():
            try:
                started = time.monotonic()
                if not self._await_wake():
                    # _await_wake normally blocks until someone speaks. If
                    # it came back instantly it did not wait for anything -
                    # a wake-word model that failed to load, or a
                    # microphone that has gone away - and without a pause
                    # the loop would spin a core flat out doing nothing.
                    #
                    # Timed rather than counted, so the paths that legitimately
                    # return early (speech that was not the wake word, or a
                    # wake word with its command already handled) are not
                    # slowed down.
                    if (time.monotonic() - started < 0.05
                            and not self._should_stop()):
                        time.sleep(config.WAKE_RETRY_SECONDS)
                    continue
                self._say(core.greeting())
                self._converse()
            except Exception as e:
                self._report("(internal)", f"{type(e).__name__}: {e}",
                             False, kind="error")
                # Pause briefly so a persistent fault cannot spin the CPU.
                time.sleep(1.0)

    def _await_wake(self) -> bool:
        """
        Wait until the user addresses the assistant.

        Two routes, chosen by what is installed. The model route never
        transcribes, so nothing is sent to a speech service while the
        assistant is merely waiting.
        """
        if wakeword.is_available():
            heard = core.wait_for_wake_word(should_stop=self._should_stop)
            if not heard:
                return False
            self._report(f'"{config.WAKE_PHRASE}"', "Wake word detected.",
                         True, kind="wake")
            return True

        text = core.transcribe()
        if self._should_stop() or not text:
            return False

        if not core.is_wake_word(text):
            self._report(text, "Ignored - no wake word.", False, kind="wake")
            return False

        # "nova open notepad" said as one breath. Run it immediately: saying
        # both together is also markedly more reliable, since the recogniser
        # gets a full phrase instead of one short word.
        trailing = core.strip_wake_word(text)
        if trailing:
            self._report(text, "Wake word + command.", True, kind="wake")
            self._run_utterance(trailing, audio=None)
            return False        # already handled; do not greet

        self._report(text, "Wake word detected.", True, kind="wake")
        return True

    def _converse(self):
        """Take commands until the user dismisses the assistant or goes quiet."""
        self._silences = 0

        while not self._should_stop():
            text, audio = core.listen()

            if self._should_stop():
                return

            if not text:
                self._silences += 1
                if self._silences >= config.CONVERSATION_SILENCE_LIMIT:
                    self._report("(silence)", "Going back to sleep.",
                                 True, kind="sleep")
                    return
                continue

            self._silences = 0

            if core.is_sleep_word(text):
                self._say(core.farewell())
                self._report(text, "Session ended.", True, kind="sleep")
                return

            self._run_utterance(text, audio)

    # --- one command, start to finish ---

    def _run_utterance(self, text: str, audio=None):
        """
        Take recognised text all the way to a spoken answer.

        Every branch ends in speech. An assistant for someone who may not be
        watching the screen has to say what happened - silence after a
        command is indistinguishable from the assistant being broken.
        """
        result = handle_recognised(text, audio=audio, source="voice")

        if result.needs_confirmation and result.intent is not None:
            result = self._confirm(result, audio=audio)

        self._say(result.message if result.message else core.acknowledgement())
        self._report(text, result.message, result.success)

    def _confirm(self, result: ExecutionResult, audio=None) -> ExecutionResult:
        """
        Ask "did you mean X?" and act on the answer.

        A timeout or an unclear answer is treated as no. Doing otherwise
        would mean a half-heard reply could run something the user never
        asked for, which is exactly the risk the confirmation exists for.
        """
        self._say(result.message)
        answer = core.transcribe(timeout=config.CONFIRM_TIMEOUT)

        if core.is_yes(answer):
            self._report(answer or "(yes)", "Confirmed.", True, kind="confirm")
            return confirm_and_execute(result.intent, audio=audio)

        if core.is_no(answer):
            return ExecutionResult.fail("Cancelled.", result.intent)

        return ExecutionResult.fail(
            "I did not catch that, so I have not done anything.", result.intent
        )


def handle_recognised(text: str, audio=None, source: str = "voice") -> ExecutionResult:
    """
    Run already-recognised text through intent, auth and execution.

    Separate from handle_text() because this one carries the audio, which is
    what speaker verification needs - discarding it at the transcription
    boundary would make sensitive-action checks impossible.

    Handles multi-step requests: "open chrome and search for python" is two
    intents and runs as two steps.
    """
    intents = nlu.get_intents(text, source=source)
    if len(intents) == 1:
        return _authorise_and_execute(intents[0], audio=audio)
    return run_sequence(intents, audio=audio)


def run_sequence(intents: list[Intent], audio=None) -> ExecutionResult:
    """
    Run several intents in order, stopping at the first failure.

    Stopping matters. The steps in a chained request are usually dependent -
    "open chrome and search for python" cannot search in a browser that did
    not open - so carrying on after a failure produces nonsense, and for an
    accessibility tool nonsense is worse than a clear stop.

    The returned message names what was done and what was not, because the
    user may not be watching the screen to work it out.
    """
    done: list[str] = []

    for position, intent in enumerate(intents, start=1):
        result = _authorise_and_execute(intent, audio=audio)

        # An ambiguous step cannot be confirmed mid-chain without turning
        # one sentence into an interrogation, so the chain stops and the
        # caller is handed the question.
        if result.needs_confirmation:
            if done:
                result.message = (
                    f"{_join(done)}. Then I was not sure: {result.message}"
                )
            return result

        if not result.success:
            if done:
                return ExecutionResult.fail(
                    f"{_join(done)}, but then {result.message[0].lower()}"
                    f"{result.message[1:]}",
                    intent,
                )
            return result

        done.append(describe_intent(intent))

        # Let each step land before the next begins. Without this a browser
        # launched by step one is not ready for step two's click.
        if position < len(intents):
            time.sleep(config.STEP_SETTLE_SECONDS)

    return ExecutionResult.ok(
        f"{_join(done)}.", intents[-1], data={"steps": len(intents)}
    )


def _join(items: list[str]) -> str:
    """"a", "a and b", "a, b and c" - said the way a person would."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0].capitalize()
    joined = ", ".join(items[:-1])
    return f"{joined} and {items[-1]}".capitalize()


def describe() -> dict:
    """What the pipeline is currently made of. Useful for the UI and for docs."""
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

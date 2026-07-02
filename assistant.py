"""Orchestrates the assistant's conversation loop.

This module grows across milestones instead of appearing all at once:
  Milestone 1: text typed in -> streamed text reply out.
  Milestone 2: reply is also spoken, sentence by sentence, as generated.
  Milestone 3: adds run_voice_chat() - push-to-talk voice mode (press
               Enter, then speak) using real microphone capture, VAD,
               and transcription.
  Milestone 4: adds run_assistant() - the flagship hands-free mode. A
               wake word gates listening instead of pressing Enter,
               follow-up questions don't need the wake word again
               (within a timeout), and saying the wake word while the
               assistant is still talking interrupts it (barge-in).
  Milestone 5: every mode now persists a summarized memory across
               launches (ai/memory.py) and run_assistant() recovers from
               the microphone disconnecting instead of crashing
               (audio/recorder.py's MicrophoneError).
  Milestone 6 (current): plain print() status lines are replaced with
               ui.TerminalUI - a colored startup banner, status lines,
               optional sound-effect cues, and a per-turn latency report
               (time to first spoken word, not just total reply time).
main.py stays a thin entry point throughout; this is where the real
control flow lives.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import tempfile
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import tts as tts_factory
from ai.conversation import ConversationHistory, Message
from ai.memory import PersistentMemory, update_summary
from ai.personality import Personality, load_personality
from ai.prompts import build_messages
from ai.providers import LLMProvider, create_provider
from audio.player import AudioPlayer
from audio.recorder import (
    AudioRecorder,
    MicrophoneError,
    drain_for,
    reconnect_microphone,
    record_utterance,
)
from audio.transcriber import create_transcriber
from audio.wakeword import WakeWordDetector, wait_for_wake_word
from config import AppConfig
from constants import DEFAULT_DATA_DIR
from plugins import load_plugins
from tts.base import TTSProvider
from ui import TerminalUI
from utils.helpers import stream_sentences
from utils.logger import get_logger
from utils.timing import Stopwatch

log = get_logger(__name__)

_EXIT_COMMANDS = {"exit", "quit"}


def _load_tools(config: AppConfig) -> tuple[list[dict] | None, dict | None]:
    """Load plugins (if enabled) into the OpenAI tool-calling shapes
    LLMProvider.stream_reply expects: a JSON-schema tool list, and a
    name -> async callable dispatch table. Returns (None, None) when
    plugins are disabled or none are installed, so stream_reply behaves
    exactly as it did before Milestone 7 added tool calling.
    """
    if not config.plugins.enabled:
        return None, None
    registry = load_plugins()
    if not registry:
        return None, None
    tool_schemas = [p.to_tool_schema() for p in registry.values()]
    dispatch = {name: p.execute for name, p in registry.items()}
    return tool_schemas, dispatch


def _load_memory(config: AppConfig) -> tuple[PersistentMemory | None, str]:
    """Create the memory store (if enabled in config) and load its saved summary."""
    if not config.memory.enabled:
        return None, ""
    memory = PersistentMemory(config.memory.path)
    summary = memory.load_summary()
    if summary:
        log.info("Loaded memory summary from previous sessions (%d chars)", len(summary))
    return memory, summary


async def _persist_memory(
    llm: LLMProvider,
    memory: PersistentMemory | None,
    summary: str,
    history: ConversationHistory,
) -> str:
    """Fold this session's conversation into the saved summary and write it out.

    Returns the (possibly updated) summary. Never raises - a failed
    summarization call at shutdown (e.g. the network just dropped)
    shouldn't prevent the assistant from exiting cleanly; on failure the
    unchanged summary is returned so nothing is lost, just not extended.
    """
    if memory is None or not history.recent():
        return summary
    try:
        updated = await update_summary(llm, summary, history)
        memory.save_summary(updated)
        log.info("Saved updated memory summary")
        return updated
    except Exception:
        log.exception("Failed to save memory - continuing without it")
        return summary


async def run_text_chat(config: AppConfig) -> None:
    """Run an interactive chat session: typed input, streamed spoken+text reply."""
    personality = load_personality(
        config.personality_profile, DEFAULT_DATA_DIR / "personalities"
    )
    llm = create_provider(config.ai)
    tts = tts_factory.create_provider(config.tts)
    player = AudioPlayer()
    history = ConversationHistory(max_messages=config.ai.max_history_messages)
    memory, memory_summary = _load_memory(config)
    tools, dispatch = _load_tools(config)
    ui = TerminalUI(config)
    ui.banner(config, personality.name)

    print(f"\n{personality.name} is ready. Type a message and press Enter.")
    print("Type 'exit' to quit.\n")

    try:
        while True:
            try:
                user_input = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye!")
                return

            if not user_input:
                continue
            if user_input.lower() in _EXIT_COMMANDS:
                print("Goodbye!")
                return

            await _converse_turn(
                llm, tts, player, personality, history, user_input, ui, memory_summary,
                tools, dispatch,
            )
    finally:
        await _persist_memory(llm, memory, memory_summary, history)


async def run_voice_chat(config: AppConfig) -> None:
    """Push-to-talk voice mode: press Enter, speak, get a spoken reply back.

    A stand-in for full wake-word activation so the record -> transcribe
    -> think -> speak pipeline can be exercised with real hardware before
    Milestone 4 makes the wake word the trigger instead of the Enter key.
    """
    personality = load_personality(
        config.personality_profile, DEFAULT_DATA_DIR / "personalities"
    )
    llm = create_provider(config.ai)
    tts = tts_factory.create_provider(config.tts)
    transcriber = create_transcriber(config.ai)
    player = AudioPlayer()
    history = ConversationHistory(max_messages=config.ai.max_history_messages)
    memory, memory_summary = _load_memory(config)
    tools, dispatch = _load_tools(config)
    recorder = AudioRecorder(
        sample_rate=config.audio.sample_rate,
        block_size=config.audio.block_size,
        device=config.audio.input_device,
    )
    ui = TerminalUI(config)
    ui.banner(config, personality.name)

    print(f"\n{personality.name} push-to-talk mode.")
    print("Press Enter, then speak. Type 'exit' + Enter instead to quit.\n")

    try:
        with recorder:
            while True:
                try:
                    command = input("[Enter to talk] ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\nGoodbye!")
                    return
                if command.lower() in _EXIT_COMMANDS:
                    print("Goodbye!")
                    return

                # Discard audio that piled up while we were waiting for
                # Enter, so we transcribe what's said now, not a stale
                # backlog.
                recorder.drain()
                ui.listening()
                audio = await record_utterance(recorder, config.audio)
                if audio is None:
                    ui.status("(didn't hear anything - try again)\n", style="dim")
                    continue

                ui.processing("Transcribing...")
                try:
                    text = await transcriber.transcribe(audio, config.audio.sample_rate)
                except Exception:
                    log.exception("Transcription failed")
                    ui.error("Could not transcribe - see logs/chad.log")
                    continue

                if not text:
                    ui.status("(couldn't make out any words - try again)\n", style="dim")
                    continue

                print(f"You said: {text}")
                await _converse_turn(
                    llm, tts, player, personality, history, text, ui, memory_summary,
                    tools, dispatch,
                )
                print()
    finally:
        await _persist_memory(llm, memory, memory_summary, history)


async def run_assistant(config: AppConfig) -> None:
    """The flagship hands-free pipeline: say the wake word, ask a question,
    get a spoken reply, ask a follow-up without repeating the wake word,
    or interrupt the assistant mid-reply by saying the wake word again.

    State machine, per wake trigger:
      1. Idle: listen for the wake word (wait_for_wake_word).
      2. On trigger: drain stale buffered audio, then record + transcribe
         one utterance. A sleep phrase ends the conversation immediately.
      3. Speak the reply while *also* listening for the wake word
         concurrently (_speak_with_barge_in) - if it fires, cut the
         reply off and go straight back to step 2 instead of step 1.
      4. Otherwise, listen for a follow-up without requiring the wake
         word, up to conversation.timeout_seconds. No follow-up -> back
         to step 1.

    If the microphone disconnects at any point, the error propagates up
    to the reconnect loop below instead of crashing the process: the
    stream is torn down, reopening is retried with backoff, and once it
    succeeds the assistant resumes idle wake-word listening.
    """
    personality = load_personality(
        config.personality_profile, DEFAULT_DATA_DIR / "personalities"
    )
    llm = create_provider(config.ai)
    tts = tts_factory.create_provider(config.tts)
    transcriber = create_transcriber(config.ai)
    player = AudioPlayer()
    history = ConversationHistory(max_messages=config.ai.max_history_messages)
    memory, memory_summary = _load_memory(config)
    tools, dispatch = _load_tools(config)
    recorder = AudioRecorder(
        sample_rate=config.audio.sample_rate,
        block_size=config.audio.block_size,
        device=config.audio.input_device,
    )
    detector = WakeWordDetector(config.wake_word)
    ui = TerminalUI(config)
    ui.banner(config, personality.name)

    print(f"\n{personality.name} is listening for the wake word '{config.assistant_name}'.")
    print("Press Ctrl+C to quit.\n")

    try:
        while True:
            try:
                with recorder:
                    while True:
                        await wait_for_wake_word(recorder, detector)
                        ui.wake_detected()
                        recorder.drain()

                        first_turn_in_conversation = True
                        while True:
                            timeout = (
                                None
                                if first_turn_in_conversation
                                else config.conversation.timeout_seconds
                            )
                            ui.listening(
                                "Listening..."
                                if first_turn_in_conversation
                                else "(waiting for a follow-up...)"
                            )
                            first_turn_in_conversation = False

                            audio = await record_utterance(recorder, config.audio, timeout)
                            if audio is None:
                                ui.status(f"{personality.name} is going back to sleep.\n", style="dim")
                                memory_summary = await _persist_memory(
                                    llm, memory, memory_summary, history
                                )
                                history.clear()
                                break

                            ui.processing("Transcribing...")
                            try:
                                text = await transcriber.transcribe(
                                    audio, config.audio.sample_rate
                                )
                            except Exception:
                                log.exception("Transcription failed")
                                ui.error("Could not transcribe - see logs/chad.log")
                                continue
                            if not text:
                                continue

                            print(f"You said: {text}")

                            if _contains_sleep_phrase(text, config.conversation.sleep_phrases):
                                print(f"{personality.name}: {config.conversation.sleep_message}")
                                await _speak_only(tts, player, config.conversation.sleep_message)
                                memory_summary = await _persist_memory(
                                    llm, memory, memory_summary, history
                                )
                                history.clear()
                                await drain_for(recorder, config.audio.wake_buffer_flush_seconds)
                                ui.status(
                                    f"\n{personality.name} is back asleep. "
                                    f"Say the wake word to talk again.\n",
                                    style="dim",
                                )
                                break

                            barged_in = await _speak_with_barge_in(
                                llm,
                                tts,
                                player,
                                personality,
                                history,
                                text,
                                recorder,
                                detector,
                                ui,
                                memory_summary,
                                tools,
                                dispatch,
                            )
                            if barged_in:
                                # The user is already mid-question by the
                                # time the interrupt fires - drain_for
                                # would eat the start of it. Treat this
                                # exactly like a fresh wake trigger.
                                ui.wake_detected()
                                recorder.drain()
                                first_turn_in_conversation = True
                                continue
                            await drain_for(recorder, config.audio.wake_buffer_flush_seconds)
            except MicrophoneError as exc:
                log.error("Microphone problem: %s", exc)
                ui.error(
                    f"\n{personality.name} lost the microphone connection - "
                    f"trying to reconnect..."
                )
                await reconnect_microphone(recorder)
                ui.status(f"{personality.name} is back online.\n", style="green")
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await _persist_memory(llm, memory, memory_summary, history)
        print("\nGoodbye!")


async def _speak_with_barge_in(
    llm: LLMProvider,
    tts: TTSProvider,
    player: AudioPlayer,
    personality: Personality,
    history: ConversationHistory,
    user_text: str,
    recorder: AudioRecorder,
    detector: WakeWordDetector,
    ui: TerminalUI,
    memory_summary: str = "",
    tools: list[dict] | None = None,
    dispatch: dict | None = None,
) -> bool:
    """Run one conversation turn, letting a repeated wake word interrupt it.

    Races the turn (LLM + speech) against a concurrent wake-word scan.
    Whichever finishes first wins: if speech finishes normally, the scan
    is cancelled and discarded. If the wake word fires first, playback is
    stopped immediately and the turn is cancelled mid-flight.

    Returns True if a barge-in occurred (caller should skip the usual
    post-speech echo drain and go straight back to recording, since the
    user is already mid-question), False if the reply finished normally.
    """
    turn_task = asyncio.create_task(
        _converse_turn(
            llm, tts, player, personality, history, user_text, ui, memory_summary,
            tools, dispatch,
        )
    )
    wake_task = asyncio.create_task(wait_for_wake_word(recorder, detector))

    done, _pending = await asyncio.wait(
        {turn_task, wake_task}, return_when=asyncio.FIRST_COMPLETED
    )

    if wake_task in done:
        log.info("Wake word triggered mid-reply - interrupting playback")
        player.stop()
        turn_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await turn_task
        return True

    wake_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await wake_task
    return False


async def _speak_only(tts: TTSProvider, player: AudioPlayer, text: str) -> None:
    """Speak a single fixed string with no LLM round-trip (e.g. the sleep phrase)."""

    async def _one_sentence() -> AsyncIterator[str]:
        yield text

    await _speak_reply(tts, player, _one_sentence())


def _contains_sleep_phrase(text: str, sleep_phrases: list[str]) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in sleep_phrases)


async def _converse_turn(
    llm: LLMProvider,
    tts: TTSProvider,
    player: AudioPlayer,
    personality: Personality,
    history: ConversationHistory,
    user_text: str,
    ui: TerminalUI,
    memory_summary: str = "",
    tools: list[dict] | None = None,
    dispatch: dict | None = None,
) -> None:
    """Send one user message through the LLM, printing and speaking the reply."""
    history.add_user(user_text)
    messages = build_messages(personality, history, memory_summary)

    stopwatch = Stopwatch()
    time_to_first_audio: float | None = None

    def _mark_first_audio() -> None:
        nonlocal time_to_first_audio
        time_to_first_audio = stopwatch.elapsed()
        ui.speaking_started()

    print(f"{personality.name}: ", end="", flush=True)
    reply_parts: list[str] = []
    try:
        deltas = _stream_and_echo(llm, messages, reply_parts, tools, dispatch)
        await _speak_reply(
            tts, player, stream_sentences(deltas), on_start_speaking=_mark_first_audio
        )
    except Exception:
        log.exception("Failed to get or speak a response from the AI provider")
        ui.error("\nSomething went wrong - see logs/chad.log")
        history.remove_last()
        return

    print()
    ui.turn_finished(time_to_first_audio, stopwatch.elapsed())
    history.add_assistant("".join(reply_parts))


async def _stream_and_echo(
    llm: LLMProvider,
    messages: list[Message],
    sink: list[str],
    tools: list[dict] | None = None,
    dispatch: dict | None = None,
) -> AsyncIterator[str]:
    """Stream a reply from the LLM, printing each chunk and recording it in `sink`."""
    async for delta in llm.stream_reply(messages, tools, dispatch):
        print(delta, end="", flush=True)
        sink.append(delta)
        yield delta


async def _speak_reply(
    tts: TTSProvider,
    player: AudioPlayer,
    sentences: AsyncIterator[str],
    on_start_speaking: Callable[[], None] | None = None,
) -> None:
    """Synthesize and play each sentence as it becomes available.

    Synthesis and playback run concurrently: a producer task synthesizes
    each sentence and drops the resulting file onto a queue as soon as
    it's ready, while a consumer task plays clips strictly one at a time,
    fully awaiting each one before starting the next. This is what lets
    speech start on the first sentence before the model has finished
    generating the rest of the reply, without risking a later sentence
    silently overwriting an earlier one that hasn't played yet (pygame's
    music.queue() can only hold one pending clip - see audio/player.py).

    on_start_speaking, if given, fires exactly once, right as the first
    clip starts playing - used to measure time-to-first-audio.
    """
    temp_paths: list[Path] = []
    playback_queue: asyncio.Queue[Path | None] = asyncio.Queue()

    async def synthesize_all() -> None:
        async for sentence in sentences:
            path = _new_temp_audio_path()
            await tts.synthesize_to_file(sentence, path)
            temp_paths.append(path)
            await playback_queue.put(path)
        await playback_queue.put(None)  # sentinel: no more sentences coming

    async def play_all() -> None:
        is_first_clip = True
        while True:
            path = await playback_queue.get()
            if path is None:
                return
            player.play(path)
            if is_first_clip:
                is_first_clip = False
                if on_start_speaking is not None:
                    on_start_speaking()
            await player.wait_until_done()

    try:
        await asyncio.gather(synthesize_all(), play_all())
    finally:
        player.unload()
        for path in temp_paths:
            path.unlink(missing_ok=True)


def _new_temp_audio_path() -> Path:
    handle, raw_path = tempfile.mkstemp(suffix=".mp3")
    os.close(handle)
    return Path(raw_path)

"""Entry point for the CHAD voice assistant.

Loads and validates configuration, sets up logging, then hands off to
assistant.py, which owns the actual conversation loop. By default that's
the full hands-free, wake-word-driven assistant; --text and
--push-to-talk switch to lighter modes useful for development and
testing without needing the wake word tuned or a quiet room.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import assistant
import constants
from config import ConfigurationError, load_config
from utils.logger import get_logger, setup_logging


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"{constants.APP_NAME} voice assistant")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--text",
        action="store_true",
        help="Type messages instead of speaking. No microphone or wake word needed.",
    )
    mode.add_argument(
        "--push-to-talk",
        action="store_true",
        help="Press Enter, then speak, instead of using the wake word.",
    )
    return parser.parse_args()


def _configure_windows_console_utf8() -> None:
    """Make Windows terminals render UTF-8 correctly (curly quotes, etc.).

    Windows consoles default to a legacy codepage (often cp1252), which
    mangles any non-ASCII character the AI generates (smart quotes, em
    dashes, accented names...) into "?" or "�". This forces UTF-8 output
    without requiring the user to run `chcp 65001` themselves.
    """
    if sys.platform != "win32":
        return
    import ctypes

    ctypes.windll.kernel32.SetConsoleOutputCP(65001)
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def main() -> int:
    """Load config, set up logging, and report readiness. Returns an exit code."""
    _configure_windows_console_utf8()
    args = _parse_args()

    try:
        config = load_config()
    except ConfigurationError as exc:
        # Logging isn't set up yet if config failed, so print directly —
        # this is the one place in the whole app where print() is correct.
        print(f"\n[{constants.APP_NAME}] Startup failed.\n\n{exc}\n", file=sys.stderr)
        return 1

    setup_logging(level=config.logging.level, log_dir=config.logging.log_dir)
    log = get_logger(__name__)

    log.info("%s v%s starting up", constants.APP_NAME, constants.APP_VERSION)
    log.info("Assistant name: %s", config.assistant_name)
    log.info("Chat model: %s (provider=%s)", config.ai.chat_model, config.ai.provider)
    log.info("Transcription model: %s", config.ai.transcribe_model)
    log.info("TTS provider: %s (voice=%s)", config.tts.provider, config.tts.edge_voice)
    log.info("Wake word model: %s", config.wake_word.model_path)
    log.info(
        "Wake word sensitivity=%.2f, VAD threshold=%.2f",
        config.wake_word.sensitivity,
        config.wake_word.vad_threshold,
    )
    log.info("Sample rate: %d Hz, block size: %d samples", config.audio.sample_rate, config.audio.block_size)
    log.info("Logs are being written to: %s", config.logging.log_dir)

    try:
        if args.text:
            asyncio.run(assistant.run_text_chat(config))
        elif args.push_to_talk:
            asyncio.run(assistant.run_voice_chat(config))
        else:
            asyncio.run(assistant.run_assistant(config))
    except Exception:
        log.exception("Assistant crashed unexpectedly")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

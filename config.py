"""Centralized configuration loading and validation.

Design:
    data/config.json  -> shareable, non-secret tuning knobs (voice,
                          thresholds, model names...). Safe to commit.
    .env               -> secrets (API keys) and machine-specific
                          overrides. Never committed (see .gitignore).

Precedence when both define the same setting: environment variables
(.env) win, because they represent "this specific machine wants it
different," which should always be able to override the shared default.

Call ``load_config()`` once at startup. It returns a fully populated,
validated ``AppConfig``. If anything required is missing, it raises
``ConfigurationError`` with a message that says exactly what to fix —
no stack-trace archaeology required.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

import constants


class ConfigurationError(Exception):
    """Raised when configuration is missing or invalid.

    Always carries a human-readable, actionable message — this is the
    exception a beginner will see first, so it has to explain the fix,
    not just the symptom.
    """


@dataclass
class WakeWordConfig:
    model_path: Path
    sensitivity: float = 0.35
    vad_threshold: float = 0.45
    confirm_window: int = 5
    hits_required: int = 2
    refractory_seconds: float = 1.5
    debug_logging: bool = False
    debug_threshold: float = 0.20


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    frame_duration_ms: int = 80
    input_device: int | str | None = None
    speech_start_threshold: float = 0.018
    speech_end_threshold: float = 0.012
    silence_duration_seconds: float = 0.35
    listen_start_timeout_seconds: float = 6.0
    max_utterance_seconds: float = 12.0
    wake_buffer_flush_seconds: float = 0.4

    @property
    def block_size(self) -> int:
        """Samples per audio frame, derived from sample rate + frame duration."""
        return int(self.sample_rate * self.frame_duration_ms / 1000)


@dataclass
class AIConfig:
    provider: str = "openai"
    chat_model: str = "gpt-4o-mini"
    transcribe_model: str = "gpt-4o-mini-transcribe"
    transcribe_language: str = "en"
    temperature: float = 0.8
    max_tokens: int = 120
    max_history_messages: int = 12
    api_key: str | None = None


@dataclass
class TTSConfig:
    provider: str = "edge"
    edge_voice: str = "en-US-BrianNeural"
    elevenlabs_api_key: str | None = None


@dataclass
class ConversationConfig:
    timeout_seconds: float = 10.0
    sleep_message: str = "Goodbye!"
    sleep_phrases: list[str] = field(default_factory=list)


@dataclass
class LoggingConfig:
    level: str = "INFO"
    log_dir: Path = constants.DEFAULT_LOG_DIR


@dataclass
class MemoryConfig:
    enabled: bool = True
    path: Path = constants.DEFAULT_MEMORY_PATH


@dataclass
class UIConfig:
    color: bool = True
    sound_effects: bool = True


@dataclass
class PluginsConfig:
    enabled: bool = True


@dataclass
class AppConfig:
    assistant_name: str
    personality_profile: str
    wake_word: WakeWordConfig
    audio: AudioConfig
    ai: AIConfig
    tts: TTSConfig
    conversation: ConversationConfig
    logging: LoggingConfig
    memory: MemoryConfig
    ui: UIConfig
    plugins: PluginsConfig


def _read_config_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigurationError(
            f"Config file not found: {path}\n"
            f"  Fix: make sure 'data/config.json' exists in the project folder. "
            f"If you deleted it, restore it from git or copy it from the project "
            f"README."
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigurationError(
            f"Config file at {path} is not valid JSON: {exc}\n"
            f"  Fix: open the file and check for a missing comma, quote, or brace "
            f"near line {exc.lineno}."
        ) from exc


def _resolve_path(raw: str, project_root: Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (project_root / path)


def load_config(
    config_path: Path | None = None,
    env_path: Path | None = None,
    project_root: Path | None = None,
) -> AppConfig:
    """Load, merge, and validate configuration from config.json + .env.

    Args:
        config_path: Override for the config.json location (defaults to
            data/config.json, or the CONFIG_PATH env var if set).
        env_path: Override for the .env location (defaults to project root).
        project_root: Override for path resolution base (defaults to the
            folder this file lives in).

    Returns:
        A fully populated, validated AppConfig.

    Raises:
        ConfigurationError: if required values are missing or invalid.
    """
    root = project_root or constants.PROJECT_ROOT
    load_dotenv(dotenv_path=env_path or constants.DEFAULT_ENV_PATH)

    resolved_config_path = config_path or Path(
        os.getenv(constants.ENV_CONFIG_PATH, str(constants.DEFAULT_CONFIG_PATH))
    )
    raw = _read_config_json(resolved_config_path)

    errors: list[str] = []

    # --- Secrets: environment only, never from config.json ---
    openai_api_key = os.getenv(constants.ENV_OPENAI_API_KEY, "").strip()
    if not openai_api_key:
        errors.append(
            f"  - Missing {constants.ENV_OPENAI_API_KEY}.\n"
            f"      Fix: open '.env' in the project root (create it by copying "
            f".env.example if it doesn't exist yet) and set:\n"
            f"        {constants.ENV_OPENAI_API_KEY}=sk-...your-key-here...\n"
            f"      Get a key at https://platform.openai.com/api-keys"
        )

    # --- Wake word model file must actually exist on disk ---
    wake_raw = raw.get("wake_word", {})
    model_path_str = os.getenv(
        constants.ENV_WAKE_WORD_MODEL_PATH,
        wake_raw.get("model_path", ""),
    )
    model_path = _resolve_path(model_path_str, root) if model_path_str else None
    if model_path is None or not model_path.exists():
        errors.append(
            f"  - Wake word model not found at '{model_path}'.\n"
            f"      Fix: place your trained .onnx wake-word model in the "
            f"'models/' folder and update 'wake_word.model_path' in "
            f"data/config.json (or set WAKE_WORD_MODEL_PATH in .env)."
        )

    if errors:
        raise ConfigurationError(
            "Configuration is incomplete - the assistant can't start yet:\n\n"
            + "\n".join(errors)
            + "\n\nSee README.md 'Configuration' section for the full guide."
        )

    audio_raw = raw.get("audio", {})
    ai_raw = raw.get("ai", {})
    tts_raw = raw.get("tts", {})
    conversation_raw = raw.get("conversation", {})
    logging_raw = raw.get("logging", {})
    memory_raw = raw.get("memory", {})
    ui_raw = raw.get("ui", {})
    plugins_raw = raw.get("plugins", {})

    return AppConfig(
        assistant_name=raw.get("assistant_name", "Assistant"),
        personality_profile=raw.get("personality", "jerry"),
        wake_word=WakeWordConfig(
            model_path=model_path,
            sensitivity=wake_raw.get("sensitivity", 0.35),
            vad_threshold=wake_raw.get("vad_threshold", 0.45),
            confirm_window=wake_raw.get("confirm_window", 5),
            hits_required=wake_raw.get("hits_required", 2),
            refractory_seconds=wake_raw.get("refractory_seconds", 1.5),
            debug_logging=wake_raw.get("debug_logging", False),
            debug_threshold=wake_raw.get("debug_threshold", 0.20),
        ),
        audio=AudioConfig(
            sample_rate=audio_raw.get("sample_rate", 16000),
            frame_duration_ms=audio_raw.get("frame_duration_ms", 80),
            input_device=audio_raw.get("input_device"),
            speech_start_threshold=audio_raw.get("speech_start_threshold", 0.018),
            speech_end_threshold=audio_raw.get("speech_end_threshold", 0.012),
            silence_duration_seconds=audio_raw.get("silence_duration_seconds", 0.35),
            listen_start_timeout_seconds=audio_raw.get(
                "listen_start_timeout_seconds", 6.0
            ),
            max_utterance_seconds=audio_raw.get("max_utterance_seconds", 12.0),
            wake_buffer_flush_seconds=audio_raw.get(
                "wake_buffer_flush_seconds", 0.4
            ),
        ),
        ai=AIConfig(
            provider=ai_raw.get("provider", "openai"),
            chat_model=ai_raw.get("chat_model", "gpt-4o-mini"),
            transcribe_model=ai_raw.get("transcribe_model", "gpt-4o-mini-transcribe"),
            transcribe_language=ai_raw.get("transcribe_language", "en"),
            temperature=ai_raw.get("temperature", 0.8),
            max_tokens=ai_raw.get("max_tokens", 120),
            max_history_messages=ai_raw.get("max_history_messages", 12),
            api_key=openai_api_key,
        ),
        tts=TTSConfig(
            provider=tts_raw.get("provider", "edge"),
            edge_voice=tts_raw.get("edge_voice", "en-US-BrianNeural"),
            elevenlabs_api_key=os.getenv(constants.ENV_ELEVENLABS_API_KEY) or None,
        ),
        conversation=ConversationConfig(
            timeout_seconds=conversation_raw.get("timeout_seconds", 10.0),
            sleep_message=conversation_raw.get("sleep_message", "Goodbye!"),
            sleep_phrases=conversation_raw.get("sleep_phrases", []),
        ),
        logging=LoggingConfig(
            level=os.getenv(
                constants.ENV_LOG_LEVEL, logging_raw.get("level", "INFO")
            ).upper(),
            log_dir=constants.DEFAULT_LOG_DIR,
        ),
        memory=MemoryConfig(
            enabled=memory_raw.get("enabled", True),
            path=constants.DEFAULT_MEMORY_PATH,
        ),
        ui=UIConfig(
            color=ui_raw.get("color", True),
            sound_effects=ui_raw.get("sound_effects", True),
        ),
        plugins=PluginsConfig(
            enabled=plugins_raw.get("enabled", True),
        ),
    )

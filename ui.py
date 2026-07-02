"""Terminal presentation: a neon HUD-style status console, startup banner,
and sound effects.

Centralizing this here keeps assistant.py focused on conversation-loop
logic - it calls ui.listening()/ui.processing()/ui.turn_finished() without
knowing anything about rich markup, color palettes, or pygame sound
channels.

Status glyphs are drawn from the Unicode box-drawing / geometric shapes
block rather than emoji: they render as plain monochrome-capable glyphs in
every terminal font, so recoloring them (cyan, magenta, purple...) actually
works, whereas emoji ship with their own fixed color glyph and ignore
terminal styling entirely.
"""

from __future__ import annotations

import psutil
import sounddevice as sd
from rich import box
from rich.console import Console
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from audio.sounds import SoundEffects
from config import AppConfig
from constants import APP_NAME, APP_VERSION, DEFAULT_DATA_DIR

# --- Neon HUD palette ---------------------------------------------------
CYAN = "#00e5ff"
MAGENTA = "#ff2bd6"
PURPLE = "#8a5cff"
GREEN = "#00ffa3"
RED = "#ff3860"
DIM = "#5c6370"

_GLYPH_WAKE = "◆"
_GLYPH_LISTEN = "▸"
_GLYPH_THINK = "◇"
_GLYPH_TIME = "△"
_GLYPH_ERROR = "✗"


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


def _gradient(text: str, start: str, end: str) -> Text:
    """Render `text` with each character's color interpolated start -> end."""
    r1, g1, b1 = _hex_to_rgb(start)
    r2, g2, b2 = _hex_to_rgb(end)
    steps = max(len(text) - 1, 1)
    out = Text()
    for i, char in enumerate(text):
        t = i / steps
        r = round(r1 + (r2 - r1) * t)
        g = round(g1 + (g2 - g1) * t)
        b = round(b1 + (b2 - b1) * t)
        out.append(char, style=f"bold #{r:02x}{g:02x}{b:02x}")
    return out


def _bar(percent: float, width: int = 10) -> Text:
    """A small filled/empty block meter, e.g. '████░░░░░░  42%'."""
    filled = max(0, min(width, round(width * percent / 100)))
    out = Text()
    out.append("█" * filled, style=CYAN)
    out.append("░" * (width - filled), style=DIM)
    out.append(f" {percent:>3.0f}%", style=DIM)
    return out


class TerminalUI:
    """Bundles a neon HUD-style console with optional sound-effect cues."""

    def __init__(self, config: AppConfig) -> None:
        self.console = Console(no_color=not config.ui.color, highlight=False)
        self._sounds = SoundEffects(
            sounds_dir=DEFAULT_DATA_DIR / "sounds",
            enabled=config.ui.sound_effects,
        )
        # cpu_percent() reports usage *since the last call on this same
        # Process object* - a fresh Process() would always report 0%. Prime
        # it once here so the first real reading later is meaningful.
        self._process = psutil.Process()
        self._process.cpu_percent(interval=None)

    def banner(self, config: AppConfig, personality_name: str) -> None:
        """Print a one-time HUD-style summary of how the assistant is configured."""
        title = _gradient(f" {APP_NAME} ", CYAN, MAGENTA)
        title.append(f"v{APP_VERSION}", style=f"bold {DIM}")

        table = Table.grid(padding=(0, 2))
        table.add_column(style=f"bold {PURPLE}", justify="right")
        table.add_column()
        table.add_row("ASSISTANT", personality_name)
        table.add_row("CHAT MODEL", f"{config.ai.chat_model} · {config.ai.provider}")
        table.add_row("TRANSCRIBE", config.ai.transcribe_model)
        table.add_row("VOICE", f"{config.tts.provider} · {config.tts.edge_voice}")
        table.add_row("WAKE WORD", config.wake_word.model_path.name)
        table.add_row("MICROPHONE", _resolve_input_device_name(config.audio.input_device))
        table.add_row("MEMORY", "online" if config.memory.enabled else "offline")
        table.add_row("LOG LEVEL", config.logging.level)
        table.add_row("SYSTEM", self.system_stats())

        self.console.print(
            Panel(
                Padding(table, (1, 1)),
                title=title,
                title_align="left",
                subtitle=_gradient("VOICE ASSISTANT", PURPLE, CYAN),
                subtitle_align="left",
                border_style=CYAN,
                box=box.HEAVY,
                expand=False,
            )
        )

    def status(self, text: str, style: str = CYAN) -> None:
        self.console.print(text, style=style)

    def wake_detected(self) -> None:
        self._sounds.play("wake")
        self.status(f"\n{_GLYPH_WAKE} WAKE WORD DETECTED", style=f"bold {MAGENTA}")

    def listening(self, label: str = "Listening...") -> None:
        self._sounds.play("listening")
        self.status(f"{_GLYPH_LISTEN} {label}", style=f"bold {CYAN}")

    def processing(self, label: str) -> None:
        """A 'please wait' cue - used for transcribing, and before the LLM call."""
        self._sounds.play("thinking")
        self.status(f"{_GLYPH_THINK} {label}", style=f"bold {PURPLE}")

    def speaking_started(self) -> None:
        self._sounds.play("speaking")

    def turn_finished(self, time_to_first_audio: float | None, total_time: float) -> None:
        self._sounds.play("done")
        if time_to_first_audio is None:
            return
        line = Text()
        line.append(f"{_GLYPH_TIME} ", style=DIM)
        line.append(f"first word {time_to_first_audio:.2f}s", style=DIM)
        line.append("  ·  ", style=DIM)
        line.append(f"reply {total_time:.2f}s", style=DIM)
        line.append("  ·  ", style=DIM)
        line.append_text(self.system_stats())
        self.console.print(line)

    def error(self, text: str) -> None:
        self.console.print(f"{_GLYPH_ERROR} {text}", style=f"bold {RED}")

    def system_stats(self) -> Text:
        cpu = self._process.cpu_percent(interval=None)
        mem_mb = self._process.memory_info().rss / (1024 * 1024)
        out = Text()
        out.append("CPU ", style=DIM)
        out.append_text(_bar(cpu))
        out.append("  RAM ", style=DIM)
        out.append(f"{mem_mb:.0f} MB", style=DIM)
        return out


def _resolve_input_device_name(device: int | str | None) -> str:
    """Best-effort human-readable name for the configured (or default) mic."""
    try:
        info = sd.query_devices(device, kind="input") if device is not None else sd.query_devices(kind="input")
        return str(info["name"])
    except Exception:
        return "default (could not query device)"

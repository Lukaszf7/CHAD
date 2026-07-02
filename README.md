# CHAD

**A fully async, provider-agnostic voice assistant framework** — wake word
detection, streaming speech-to-text, LLM reasoning augmented with
real-world tool calling, and streaming text-to-speech, all pipelined
together with sub-second perceived latency and mid-sentence
interruptibility.

Say a wake word. Ask it anything. It streams a spoken answer back before
it's even finished thinking — and if you talk over it, it stops and
listens instead of talking through you.

## Why this isn't just another wake-word demo

Most hobbyist voice assistant projects are a `while True` loop that
records, transcribes, prompts, and plays back audio sequentially — dead
air while each stage runs. CHAD is architected as a genuine concurrent
pipeline instead:

- **Streaming end-to-end.** LLM tokens are grouped into sentences on the
  fly and handed to a synthesis pipeline sentence-by-sentence, so speech
  starts on the *first* sentence while the model is still generating the
  rest of the reply — not after the full response completes.
- **Barge-in via structured concurrency.** While the assistant is
  speaking, a wake-word listener races against the active reply using
  `asyncio.wait(..., FIRST_COMPLETED)`. Interrupt it mid-sentence and
  playback stops and a new turn begins immediately — no polling, no
  manual thread coordination.
- **Tool-augmented reasoning.** The LLM doesn't just chat — it can call
  real functions (exact arithmetic, live weather, system telemetry,
  the current time) mid-conversation via OpenAI-style function calling,
  deciding for itself when a question needs a tool rather than matching
  hardcoded trigger phrases. New capabilities are single drop-in Python
  files, auto-discovered at startup — zero registry edits, zero changes
  to the orchestration layer.
- **Provider-agnostic by construction.** LLM, text-to-speech, and
  transcription are each behind an abstract interface with a name-keyed
  factory registry (a Strategy pattern applied consistently across the
  whole I/O boundary). Swapping OpenAI for a different backend is a
  subclass and a dictionary entry — nothing downstream changes.
- **Resilient by default, not by accident.** Every network call is
  wrapped in exponential-backoff-with-jitter retry logic. A microphone
  that gets unplugged mid-session doesn't crash the process — it's
  detected, surfaced as a typed error, and the assistant automatically
  reconnects with backoff once the device comes back.
- **Bounded, durable memory.** Rather than replaying raw transcripts
  forever, conversations are folded into a single rolling LLM-generated
  summary (~150 words) after each session and re-injected into the
  system prompt on the next launch — memory that survives restarts
  without growing unbounded cost or context-window pressure.
- **Security-conscious where it's easy to be lazy.** The `calculate` tool
  evaluates user-influenced arithmetic expressions via a hand-rolled,
  whitelisted AST walker — not `eval()` — so it's structurally incapable
  of executing injected code, not just "probably fine in practice."

## Origin story

This started life as a two-file weekend hack — `Chad_speaking.py`, no
error handling, no config, three different OpenAI API keys hardcoded
directly in source, and a truncated script that didn't actually run.
It's since been rebuilt from the ground up into the modular system
described above: ten incremental milestones, each shipped in a fully
working, independently tested state — provider abstractions, an async
audio pipeline, wake-word debouncing, failure recovery, a plugin
architecture, and a 100+ test suite exercising the pure logic and
mocked I/O boundaries with zero flakiness.

## Architecture

```
                    ┌─────────────────────────────────────────┐
                    │              wake word (VAD +            │
                    │        openWakeWord, debounced)           │
                    └───────────────────┬───────────────────────┘
                                        ▼
   ┌──────────────┐   ┌──────────────────────┐   ┌──────────────────┐
   │  microphone   │──▶│  speech-to-text       │──▶│  LLM (streamed)   │
   │  (async, VAD  │   │  (OpenAI transcribe)  │   │  + tool calling   │
   │   hysteresis) │   └──────────────────────┘   └─────────┬────────┘
   └──────────────┘                                          │
          ▲                                                  ▼
          │            ┌──────────────────┐      ┌────────────────────┐
          └────────────│  barge-in race     │◀────│  sentence-grouped   │
       (interrupts a   │  (asyncio.wait)    │      │  streaming TTS      │
        reply mid-turn)└──────────────────┘      │  (producer/consumer  │
                                                    │   queue, gapless)   │
                                                    └────────────────────┘
```

Every arrow above is a swappable, independently testable component —
see [Extending CHAD](#extending-chad).

## Highlights

- **Three interaction modes** sharing one conversation engine: hands-free
  wake word, push-to-talk, and typed chat.
- **Tool-augmented LLM** — live weather, exact arithmetic, system
  telemetry, real-time clock — extensible via a one-file plugin API.
- **Persistent, bounded memory** across sessions via LLM summarization.
- **Data-driven personas** — the entire personality lives in a JSON
  system prompt, not code, so swapping who you're talking to is a new
  file, not a redeploy.
- **Automatic failure recovery** — retry-with-backoff on every network
  call, live microphone-reconnect on hardware disconnect.
- **A neon terminal HUD** — gradient-rendered banner, live CPU/RAM
  meters, synthesized (not shipped-as-assets) UI sound cues.
- **103 automated tests** covering config parsing, the debounce/VAD
  state machines, the tool-calling loop, and the plugin system — all
  through fakes/mocks, running in ~10 seconds with no API key or mic.

## Tech stack

Python 3.11 · `asyncio` · OpenAI (chat completions + speech-to-text) ·
Edge TTS · openWakeWord (ONNX runtime) · `sounddevice` · `pygame` ·
`rich` · `httpx` · `pytest` + `pytest-asyncio`

## Getting started

```powershell
git clone <this repo> && cd CHAD
python -m venv venv && venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -c "from openwakeword.utils import download_models; download_models()"
Copy-Item .env.example .env   # then add your OPENAI_API_KEY
python main.py                 # or --push-to-talk / --text
```

A trained wake-word `.onnx` model is required for the default hands-free
mode (`--text` and `--push-to-talk` don't need one) — train your own via
[openWakeWord's pipeline](https://github.com/dscripka/openWakeWord) and
point `wake_word.model_path` in `data/config.json` at it.

## Extending CHAD

Every external integration sits behind an abstract interface plus a
name-keyed registry — no caller ever imports a vendor SDK directly:

| To add a new... | Subclass | Register in |
|---|---|---|
| LLM provider (Anthropic, Gemini, Ollama...) | `LLMProvider` (`ai/providers.py`) | `_PROVIDERS` dict, same file |
| TTS provider (ElevenLabs...) | `TTSProvider` (`tts/base.py`) | `_PROVIDERS` dict in `tts/__init__.py` |
| Transcription provider | `Transcriber` (`audio/transcriber.py`) | `_TRANSCRIBERS` dict, same file |
| Tool the LLM can call | — | drop a file in `plugins/` (see below) |

### Plugins in 15 lines

```python
from plugins.base import plugin

@plugin(
    name="my_tool",
    description="One clear sentence the model uses to decide when to call this.",
    parameters={
        "type": "object",
        "properties": {"some_arg": {"type": "string", "description": "..."}},
        "required": ["some_arg"],
    },
)
async def my_tool(some_arg: str) -> str:
    return f"did something with {some_arg}"
```

`plugins/__init__.py` auto-discovers every module in the folder at
startup via `pkgutil` + `importlib` — no registry to edit, no restart
logic to write. Built-in examples: exact arithmetic (`calculator_plugin.py`,
safe-AST, not `eval()`), live weather (`weather_plugin.py`, via the free
Open-Meteo API), system telemetry (`system_plugin.py`), and the current
time (`time_plugin.py`).

## Configuration reference

Two places, two purposes: `data/config.json` for anything safe to share
(voice, sensitivity, model names, personality), `.env` for secrets and
per-machine overrides (never committed — see `.gitignore`).

<details>
<summary><strong>Full <code>data/config.json</code> field reference</strong></summary>

| Section | Field | Default | What it does |
|---|---|---|---|
| `assistant_name` | — | `"Assistant"` | The name spoken in status messages and used for the wake word banner. |
| `personality` | — | `"jerry"` | Which `data/personalities/<name>.json` file to load. |
| `wake_word` | `model_path` | *(required)* | Path to your trained `.onnx` wake word model. |
| | `sensitivity` | `0.35` | A per-frame score above this counts as a "hit." Lower = triggers more easily. |
| | `confirm_window` | `5` | How many recent frames are considered together when deciding to trigger. |
| | `hits_required` | `2` | How many of those `confirm_window` frames must be above `sensitivity` to trigger. |
| | `vad_threshold` | `0.0` (dataclass fallback is `0.45` if this key is ever removed) | openWakeWord's internal voice-activity gate. Left disabled deliberately — its lag window can silently zero short wake-phrase scores. |
| | `refractory_seconds` | `1.5` | Minimum time between two triggers, so one utterance can't fire twice. |
| | `debug_logging` / `debug_threshold` | `false` / `0.20` | Logs per-frame scores while tuning. |
| `audio` | `sample_rate` / `frame_duration_ms` | `16000` / `80` | Microphone sampling — 16kHz/80ms matches openWakeWord's expected input shape. |
| | `input_device` | `null` (system default) | Device index/name if you have multiple microphones. |
| | `speech_start_threshold` / `speech_end_threshold` | `0.018` / `0.012` | Hysteresis volume thresholds that start/end a recorded utterance. |
| | `silence_duration_seconds` | `0.35` | Silence duration before a recording is considered finished. |
| | `listen_start_timeout_seconds` / `max_utterance_seconds` | `6.0` / `12.0` | Timeout waiting for speech to start / hard cap on utterance length. |
| | `wake_buffer_flush_seconds` | `0.4` | Echo-avoidance: audio discarded right after the assistant stops talking. |
| `ai` | `provider` / `chat_model` / `transcribe_model` / `transcribe_language` | `openai` / `gpt-4o-mini` / `gpt-4o-mini-transcribe` / `en` | Model selection. |
| | `temperature` / `max_tokens` / `max_history_messages` | `0.8` / `120` / `12` | Generation and context-window tuning. |
| `tts` | `provider` / `edge_voice` | `edge` / `en-US-BrianNeural` | Any [Edge TTS voice](https://learn.microsoft.com/azure/ai-services/speech-service/language-support?tabs=tts). |
| `conversation` | `timeout_seconds` / `sleep_message` / `sleep_phrases` | `10.0` / `"Goodbye!"` / `[]` | Follow-up window and how a conversation ends. |
| `memory` | `enabled` | `true` | Persist/reload the rolling memory summary. |
| `ui` | `color` / `sound_effects` | `true` / `true` | Terminal styling and synthesized cue tones. |
| `plugins` | `enabled` | `true` | Whether tool-calling is exposed to the LLM at all. |
| `logging` | `level` | `"INFO"` | Log verbosity. |

</details>

<details>
<summary><strong><code>.env</code> reference</strong></summary>

| Variable | Required? | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | Yes | Chat completions and speech-to-text. |
| `ELEVENLABS_API_KEY` / `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` | Only if you add those providers | Interfaces exist; only OpenAI + Edge TTS are wired up today. |
| `LOG_LEVEL` / `CONFIG_PATH` / `WAKE_WORD_MODEL_PATH` | No | Per-machine overrides of the matching `data/config.json` values. |

</details>

## Testing

```powershell
pytest
```

103 tests, ~10 seconds, no API key or microphone required — the real
model/network/hardware boundaries (`audio/recorder.py`, `audio/player.py`,
`tts/edge.py`, `audio/transcriber.py`, the real openWakeWord ONNX model)
are exercised by hand against real hardware instead of mocked, since
faking them would test the mock, not the integration.

## Project layout

```
CHAD/
├── main.py            # Entry point (--text / --push-to-talk / default)
├── assistant.py          # Async orchestration - the conversation loop
├── ui.py                    # Neon terminal HUD: banner, status, sound cues
├── config.py                  # data/config.json + .env loading & validation
├── audio/                # Mic capture, VAD, wake word, playback, STT
├── ai/                     # LLM abstraction, conversation history, memory, prompts
├── tts/                      # Text-to-speech abstraction
├── plugins/                    # Drop-in LLM tool-calling plugin system
├── utils/                        # Retry, sentence-streaming, logging, timing
├── data/                # config.json, personas, persisted memory
├── models/                # Wake-word .onnx models (per-user, gitignored)
└── tests/                   # pytest suite
```

---

*Built solo, end to end — architecture, async pipeline design, provider
abstractions, plugin system, and test suite.*

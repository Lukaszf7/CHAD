# CHAD — Voice Assistant

CHAD is a modular, configurable desktop voice assistant: say a wake word,
ask a question, get a spoken answer. It also types, does push-to-talk,
remembers you between launches, and can call out to real tools (the
time, live weather, exact arithmetic, system stats) mid-conversation.

All nine planned milestones are complete — see the [Roadmap](#roadmap) at
the bottom for what shipped when.

## Features

- **Three ways to talk to it**: hands-free wake word (`python main.py`),
  push-to-talk (`--push-to-talk`), or plain typed chat (`--text`) — the
  same personality, memory, and plugins work in all three.
- **Streamed replies**: the model's reply is spoken sentence-by-sentence
  as it's generated, not after the whole response finishes.
- **Barge-in**: say the wake word again while it's still talking and it
  stops and listens immediately.
- **Persistent memory**: a rolling summary of what you've told it,
  carried across separate launches (not a raw transcript dump).
- **Plugins**: the model can call real tools mid-reply — current time,
  live weather, exact arithmetic, system CPU/RAM — and adding a new one
  is a single drop-in `.py` file, no other code changes.
- **Recovers from failures**: retries transient network errors, and
  reconnects automatically if the microphone gets unplugged mid-session.
- **Swappable personality**: the whole persona lives in a JSON file, not
  in code.

## Quick Start

1. **Open a terminal in the project folder.**
   In VS Code: `Terminal -> New Terminal`. Make sure it lands in
   `Documents/GitHub/CHAD`.

2. **Create a virtual environment** (keeps this project's packages
   separate from everything else on your machine):

   ```powershell
   python -m venv venv
   ```

3. **Activate it:**

   ```powershell
   venv\Scripts\Activate.ps1
   ```

   You'll know it worked because your prompt now starts with `(venv)`.

   > If you get an error about "running scripts is disabled on this
   > system," run this once, then retry step 3:
   > `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

4. **Install dependencies:**

   ```powershell
   pip install -r requirements.txt
   ```

   openWakeWord needs one extra one-time step to download its shared
   preprocessing models (not bundled in the pip package):

   ```powershell
   python -c "from openwakeword.utils import download_models; download_models()"
   ```

5. **Set up your secrets file:**

   ```powershell
   Copy-Item .env.example .env
   ```

   Then open `.env` in a text editor and paste your OpenAI API key after
   `OPENAI_API_KEY=`. Get a key at
   https://platform.openai.com/api-keys if you don't have one. See
   [Security](#security) below before reusing an old key.

6. **Make sure you have a wake word model.**
   A trained model should already be at `models/jerry_wakeword.onnx`. If
   you're starting fresh or want your own wake word, train one with
   [openWakeWord's training pipeline](https://github.com/dscripka/openWakeWord)
   and point `wake_word.model_path` in `data/config.json` at the result.
   (Only needed for the default hands-free mode — `--text` and
   `--push-to-talk` don't touch the wake word at all.)

7. **Run it:**

   ```powershell
   python main.py                # hands-free: say "Jerry", then ask something
   python main.py --push-to-talk # press Enter, speak, get a spoken reply
   python main.py --text         # type instead of speaking, no mic needed
   ```

### Expected result

A colored startup banner showing your configuration, then:

- **Default mode**: "`Jerry is listening for the wake word 'Jerry'.`" — say
  it, wait for the chime, then ask something.
- **`--push-to-talk`**: "`[Enter to talk]`" — press Enter, speak, release
  is automatic (it stops recording after you go quiet).
- **`--text`**: "`You: `" — type a message and press Enter.

A `logs/chad.log` file also appears — every run appends there, so you
have a history even after closing the terminal.

## Configuration

Two places, two purposes:

- **`data/config.json`** — anything safe to share: voice, wake word
  sensitivity, model names, timeouts, personality. Edit this freely.
- **`.env`** — secrets and machine-specific overrides only. Never
  committed (see `.gitignore`). Copy `.env.example` to create your own.
  Anything set here overrides the matching `data/config.json` value.

### `data/config.json` reference

Every field has a default (shown below) — you only need to set what
you're changing. See `config.py` for the authoritative source.

| Section | Field | Default | What it does |
|---|---|---|---|
| `assistant_name` | — | `"Assistant"` | The name spoken in status messages and used for the wake word banner. |
| `personality` | — | `"jerry"` | Which `data/personalities/<name>.json` file to load. |
| `wake_word` | `model_path` | *(required)* | Path to your trained `.onnx` wake word model. |
| | `sensitivity` | `0.35` | A per-frame score above this counts as a "hit." Lower = triggers more easily. |
| | `confirm_window` | `5` | How many recent frames are considered together when deciding to trigger. |
| | `hits_required` | `2` | How many of those `confirm_window` frames must be above `sensitivity` to trigger. |
| | `vad_threshold` | `0.0` (shipped in `data/config.json`; the Python dataclass fallback is `0.45` if this key is ever removed) | openWakeWord's internal voice-activity gate. **Leave at `0.0`** — see [Wake word tuning](#wake-word-tuning). |
| | `refractory_seconds` | `1.5` | Minimum time between two triggers, so one utterance can't fire twice. |
| | `debug_logging` | `false` | Log every per-frame score above `debug_threshold` — turn on when tuning. |
| | `debug_threshold` | `0.20` | Score floor for what gets logged when `debug_logging` is on. |
| `audio` | `sample_rate` | `16000` | Microphone sample rate in Hz. openWakeWord expects 16kHz. |
| | `frame_duration_ms` | `80` | Size of each audio chunk fed to VAD/wake word. |
| | `input_device` | `null` (system default) | Set to a device index or name if you have multiple microphones. |
| | `speech_start_threshold` / `speech_end_threshold` | `0.018` / `0.012` | Volume levels (hysteresis) that start/end a recorded utterance. |
| | `silence_duration_seconds` | `0.35` | How long you have to go quiet before recording stops. |
| | `listen_start_timeout_seconds` | `6.0` | How long to wait for you to start speaking before giving up. |
| | `max_utterance_seconds` | `12.0` | Hard cap on how long a single recording can run. |
| | `wake_buffer_flush_seconds` | `0.4` | How long to discard audio right after the assistant stops talking, so it doesn't hear its own voice echo as a false trigger. |
| `ai` | `provider` | `"openai"` | LLM backend (see `ai/providers.py`). |
| | `chat_model` | `"gpt-4o-mini"` | Model used for conversation. |
| | `transcribe_model` | `"gpt-4o-mini-transcribe"` | Model used for speech-to-text. |
| | `transcribe_language` | `"en"` | Language hint passed to the transcription model. |
| | `temperature` | `0.8` | Chat model creativity/randomness. |
| | `max_tokens` | `120` | Reply length cap — keep this small, replies are spoken aloud. |
| | `max_history_messages` | `12` | How many recent turns stay in context before older ones are trimmed. |
| `tts` | `provider` | `"edge"` | Text-to-speech backend (see `tts/`). |
| | `edge_voice` | `"en-US-BrianNeural"` | Any [Edge TTS voice name](https://learn.microsoft.com/azure/ai-services/speech-service/language-support?tabs=tts). |
| `conversation` | `timeout_seconds` | `10.0` | How long to wait for a follow-up question before going back to sleep. |
| | `sleep_message` | `"Goodbye!"` | Spoken when a sleep phrase is heard. |
| | `sleep_phrases` | `[]` | Phrases (substring match) that end the conversation, e.g. `"goodbye"`. |
| `memory` | `enabled` | `true` | Whether to persist/reload the rolling memory summary across launches. |
| `ui` | `color` | `true` | Colored terminal output. |
| | `sound_effects` | `true` | Short chime cues on wake/listen/think/speak/done. |
| `plugins` | `enabled` | `true` | Whether to load and expose plugins to the LLM as tools at all. |
| `logging` | `level` | `"INFO"` | Log verbosity (`DEBUG`/`INFO`/`WARNING`/`ERROR`). |

### `.env` reference

| Variable | Required? | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | Yes | Chat completions and speech-to-text. |
| `ELEVENLABS_API_KEY` | Only if you add an ElevenLabs TTS provider | Not used by the built-in `edge` provider. |
| `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` | Only if you add those providers | Interfaces exist for other providers; only OpenAI is implemented today. |
| `LOG_LEVEL` | No | Overrides `logging.level` from `data/config.json`. |
| `CONFIG_PATH` | No | Point at a different config.json entirely. |
| `WAKE_WORD_MODEL_PATH` | No | Override the wake word model path per-machine without editing config.json. |

## Personalities

A personality is just `data/personalities/<name>.json`:

```json
{
  "name": "Jerry",
  "system_prompt": "You are Jerry, a voice assistant who is a homie to whomever he is assisting..."
}
```

Add a new file, then set `"personality": "<name>"` in `data/config.json`.
Keep the system prompt short and explicit about speaking style (e.g. "1-3
sentences, no lists, no markdown") — replies are read aloud, so anything
a text chatbot would normally get away with (bullet points, long
paragraphs) sounds wrong spoken.

## Plugins

The assistant can call real tools mid-conversation instead of guessing —
ask "what's the weather in Chicago" or "what's 847 times 213" and it
actually looks it up / computes it exactly, via OpenAI-style function
calling: the model decides on its own when a question needs a tool, no
hardcoded trigger phrases required.

Built-in plugins (`plugins/`):

| Plugin | Tool name | What it does |
|---|---|---|
| `time_plugin.py` | `get_current_time` | Real local date/time. |
| `system_plugin.py` | `get_system_status` | Live CPU/RAM usage of the host machine. |
| `calculator_plugin.py` | `calculate` | Exact arithmetic via a safe AST evaluator (never `eval()`). |
| `weather_plugin.py` | `get_weather` | Live conditions via [Open-Meteo](https://open-meteo.com) — free, no API key needed. |

### Writing your own

Drop a new `.py` file in `plugins/`:

```python
from plugins.base import plugin

@plugin(
    name="my_tool",
    description="One clear sentence the model uses to decide when to call this.",
    parameters={  # omit entirely for a zero-argument tool
        "type": "object",
        "properties": {"some_arg": {"type": "string", "description": "..."}},
        "required": ["some_arg"],
    },
)
async def my_tool(some_arg: str) -> str:
    return f"did something with {some_arg}"
```

That's it — `plugins/__init__.py` auto-discovers every module in the
folder at startup, no registry to edit. A few things worth knowing:

- `description` is the *only* thing the model sees when deciding whether
  to call your tool — be specific ("use this whenever the user asks
  about X"), not just a restatement of the function name.
- A tool call costs a second model round-trip (decide to call it, get the
  result, generate the final answer), so tool-using replies are
  noticeably slower than plain chat — expect several seconds, not
  sub-second.
- If your handler raises, or the model hallucinates a tool name that
  doesn't exist, the assistant doesn't crash — it feeds an error string
  back to the model so it can recover gracefully in its spoken reply.
- Set `plugins.enabled: false` in `data/config.json` to disable the whole
  system (e.g. for a lower-latency, chat-only setup).

## Wake word tuning

The wake word pipeline has two independent layers, and confusing them is
the most common source of "it barely triggers" or "it's over-eager":

1. **openWakeWord's own model score**, gated by `wake_word.vad_threshold`
   — an internal Silero VAD check. **This should stay at `0.0`
   (disabled).** It gates on a *lagged* audio window (roughly 240-560ms
   *before* the current frame), which for a short single-word wake
   phrase often doesn't overlap the actual utterance at all — the score
   gets silently zeroed before your own debounce logic ever sees it.
   Symptom if this is misconfigured: you have to shout and repeat the
   wake word many times before it ever registers.
2. **This project's own debounce logic** (`audio/wakeword.py`): a score
   only counts as a "hit" above `wake_word.sensitivity`, and a trigger
   only fires once `hits_required` of the last `confirm_window` frames
   are hits. This is what actually prevents false positives — tune
   *this* layer, not the VAD gate.

To tune it:

1. Set `wake_word.debug_logging: true` and `wake_word.debug_threshold`
   low (e.g. `0.02`) in `data/config.json`, then run `python main.py`
   normally and watch `logs/chad.log` while you say the wake word.
2. **Under-triggering** (scores rarely cross `sensitivity`): lower
   `sensitivity`, or lower `hits_required`.
3. **Over-triggering** (fires on background noise/other words): raise
   `sensitivity`, or raise `hits_required`.
4. If scores barely register at all even close to the microphone, the
   `.onnx` model itself is likely the bottleneck (training data
   quality/quantity), not these settings — consider retraining via
   [openWakeWord's training pipeline](https://github.com/dscripka/openWakeWord),
   or temporarily pointing `wake_word.model_path` at one of
   openWakeWord's bundled pretrained models (`hey_jarvis`, `alexa`,
   `hey_mycroft`) to A/B test whether it's the model or the pipeline.

## Memory

Not a raw transcript log — a single rolling summary (~150 words), stored
at `data/memory/memory.json`. At the end of each conversation (sleep
phrase, timeout, or exit), the LLM folds that session into the existing
summary, and the result is re-injected into the system prompt on the
next launch. This keeps "remembering past conversations" bounded in size
and cost no matter how many sessions have happened. Set `memory.enabled:
false` in `data/config.json` to turn it off entirely.

## Extending CHAD

Every external integration is behind an abstract interface + a
name-keyed registry, so adding a new backend never requires touching
callers:

| To add a new... | Subclass | Register in |
|---|---|---|
| LLM provider (Anthropic, Gemini, Ollama...) | `LLMProvider` (`ai/providers.py`) | `_PROVIDERS` dict, same file |
| TTS provider (ElevenLabs...) | `TTSProvider` (`tts/base.py`) | `_PROVIDERS` dict in `tts/__init__.py` |
| Transcription provider | `Transcriber` (`audio/transcriber.py`) | `_TRANSCRIBERS` dict, same file |
| Tool/capability | — | Just drop a file in `plugins/`, see [Plugins](#plugins) |

Only OpenAI (chat + transcription) and Edge TTS are implemented today;
the other three secrets in `.env.example` are there for when someone
adds those providers.

## Project layout

```
CHAD/
├── main.py              # Entry point: argparse (--text / --push-to-talk / default)
├── assistant.py           # Orchestrator - the conversation loop for all three modes
├── ui.py                    # Terminal presentation: neon HUD banner, status lines, sound cues
├── config.py                  # Loads + validates data/config.json and .env
├── constants.py                 # Fixed values (paths, log format) — not user config
│
├── audio/                # Microphone, VAD, wake word, playback, transcription
├── ai/                     # LLM provider abstraction, conversation history, memory, prompts
├── tts/                      # Text-to-speech provider abstraction
├── plugins/                    # Drop-in tool-calling plugin system
├── utils/                        # Logging, retry, sentence-streaming, timing helpers
│
├── data/
│   ├── config.json              # All user-tunable settings
│   ├── personalities/              # Persona system prompts (JSON)
│   └── memory/                       # Persisted conversation summary (gitignored)
├── models/                # Wake word .onnx models (gitignored, per-user)
├── tests/                   # pytest suite (config, plugins, tool-calling loop, wake word...)
└── legacy/                    # Old proof-of-concept scripts, kept for reference only
```

## Running the tests

```powershell
pip install -r requirements.txt   # pulls in pytest + pytest-asyncio
pytest
```

The suite covers config parsing, conversation/memory bookkeeping, retry
logic, VAD and wake-word debounce math, and the plugin/tool-calling
system — all with fake models/HTTP clients, so it runs in seconds with no
API key or microphone needed. It does not exercise the real
microphone/speaker/network calls (`audio/recorder.py`, `audio/player.py`,
`tts/edge.py`, `audio/transcriber.py`) — those are verified by hand
against the real hardware/network instead.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Configuration is incomplete... Missing OPENAI_API_KEY` | You skipped the `.env` setup step, or left the value blank. |
| `Wake word model not found at ...` | Check `data/config.json` -> `wake_word.model_path` points to a real `.onnx` file in `models/`. |
| `ModuleNotFoundError: No module named 'dotenv'` (or similar) | You ran `python main.py` without activating the venv, or skipped `pip install -r requirements.txt`. |
| PowerShell won't run `Activate.ps1` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then retry. |
| Wake word barely triggers, or you have to shout | See [Wake word tuning](#wake-word-tuning) — check `vad_threshold` is `0.0` first. |
| `Could not open the microphone` | No mic connected, or the wrong `audio.input_device` is set. List devices with `python -c "import sounddevice; print(sounddevice.query_devices())"`. |
| Garbled/mojibake characters in the terminal banner | Should self-correct — `main.py` forces UTF-8 console output on Windows automatically. If it still looks wrong, your terminal font may not have the Unicode glyphs used in the banner. |
| A plugin makes replies noticeably slower | Expected — a tool call is a second model round-trip. See [Plugins](#plugins). |

## Security

Three OpenAI API keys were found hardcoded in plaintext in the original
proof-of-concept scripts before this rebuild (`legacy/*.bak`, kept only
for reference and gitignored from any real use). One of those keys is
still what's carrying `.env` today so the project kept working during
the rebuild. **If you haven't already, rotate it**: generate a fresh key
at https://platform.openai.com/api-keys, put the new one in `.env`, and
revoke the old one from the same page. `.env` is gitignored, so this
won't happen again going forward — just the original leak needs cleaning
up.

## Roadmap

- [x] Milestone 0 — Config, logging, project skeleton
- [x] Milestone 1 — AI provider abstraction + terminal text chat
- [x] Milestone 2 — TTS abstraction + streaming playback
- [x] Milestone 3 — Microphone capture, VAD, transcription
- [x] Milestone 4 — Wake word + full async voice pipeline (feature parity with the old script)
- [x] Milestone 5 — Error recovery, retries, persistent memory
- [x] Milestone 6 — Terminal UX polish (status display, sound effects)
- [x] Milestone 7 — Plugin system
- [x] Milestone 8 — Tests
- [x] Milestone 9 — Full documentation

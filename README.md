# CHAD — Voice Assistant

> **Status: under active reconstruction.** This README covers what's built so
> far (Milestone 0: configuration + logging foundation). It will grow with
> each milestone until the full assistant (wake word -> listen -> think ->
> speak) is complete. See the bottom of this file for the roadmap.

CHAD is a modular, configurable desktop voice assistant: say a wake word,
ask a question, get a spoken answer.

## Quick Start (Milestone 0)

These steps get the configuration/logging foundation running. There is no
voice interaction yet — that arrives in later milestones.

1. **Open a terminal in the project folder.**
   In VS Code: ``Terminal -> New Terminal``. Make sure it lands in
   `Documents/GitHub/CHAD`.

2. **Create a virtual environment** (keeps this project's packages separate
   from everything else on your machine):

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

5. **Set up your secrets file:**

   ```powershell
   Copy-Item .env.example .env
   ```

   Then open `.env` in a text editor and paste your OpenAI API key after
   `OPENAI_API_KEY=`. Get a key at
   https://platform.openai.com/api-keys if you don't have one.

   > A `.env` already exists in this project carrying over the key from
   > the old `Chad_speaking.py` script so things keep working — but that
   > key was previously exposed in plaintext in three files, so you should
   > revoke it and generate a fresh one when you get a chance.

6. **Run it:**

   ```powershell
   python main.py
   ```

### Expected result

You should see log lines like:

```
2026-06-30 20:40:00 | INFO     | __main__ | CHAD v2.0.0 starting up
2026-06-30 20:40:00 | INFO     | __main__ | Assistant name: Jerry
...
2026-06-30 20:40:00 | INFO     | __main__ | Configuration is valid. Milestone 1 will add the AI conversation loop.
```

A `logs/chad.log` file will also appear — every run appends there too, so
you have a history even after closing the terminal.

### Common problems

| Symptom | Fix |
|---|---|
| `Configuration is incomplete... Missing OPENAI_API_KEY` | You skipped step 5, or left the value blank in `.env`. |
| `Wake word model not found at ...` | The model file should already be at `models/jerry_wakeword.onnx`. If it's missing, check `data/config.json` -> `wake_word.model_path` points to the right file. |
| `ModuleNotFoundError: No module named 'dotenv'` | You ran `python main.py` without activating the venv first, or skipped step 4. Redo steps 3-4. |
| PowerShell won't run `Activate.ps1` | See the execution-policy note under step 3. |

## Project layout

```
CHAD/
├── main.py           # Entry point
├── config.py          # Loads + validates data/config.json and .env
├── constants.py        # Fixed values (paths, log format) — not user config
├── audio/              # Microphone, VAD, wake word, playback (Milestones 2-4)
├── ai/                 # LLM provider abstraction, conversation memory (Milestone 1)
├── tts/                 # Text-to-speech provider abstraction (Milestone 2)
├── plugins/             # Drop-in plugin system (Milestone 7)
├── utils/               # Logging and shared helpers
├── data/                # config.json + persistent conversation memory
├── models/               # Wake word .onnx models (gitignored, per-user)
├── tests/                # Automated tests (Milestone 8)
└── legacy/                # Old proof-of-concept scripts, kept for reference only
```

## Configuration

Two places, two purposes:

- **`data/config.json`** — anything safe to share: voice, wake word
  sensitivity, model names, timeouts, personality. Edit this freely.
- **`.env`** — secrets and machine-specific overrides only. Never
  committed (see `.gitignore`). Copy `.env.example` to create your own.

## Running the tests

```powershell
pip install -r requirements.txt   # pulls in pytest + pytest-asyncio
pytest
```

The suite covers config parsing, conversation/memory bookkeeping, retry
logic, VAD and wake-word debounce math, and the plugin/tool-calling
system - all with fake models/HTTP clients, so it runs in seconds with no
API key or microphone needed. It does not exercise the real
microphone/speaker/network calls (audio/recorder.py, audio/player.py,
tts/edge.py, audio/transcriber.py) - those are verified by hand per each
milestone's "How to Run" instructions above.

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
- [ ] Milestone 9 — Full documentation

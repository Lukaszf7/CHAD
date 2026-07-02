"""Fixed values that define the identity of the application itself.

Anything a user might reasonably want to change (voice, sensitivity,
model names, personality...) belongs in ``data/config.json`` or ``.env``
instead — see config.py. This file is only for values that would stop
being "CHAD" if they changed.
"""

from pathlib import Path

# --- Application identity ---------------------------------------------
APP_NAME = "CHAD"
APP_VERSION = "2.0.0"

# --- Filesystem layout ---------------------------------------------
# All paths are resolved relative to the project root (this file's folder)
# so the assistant works no matter what directory it's launched from.
PROJECT_ROOT = Path(__file__).resolve().parent

DEFAULT_CONFIG_PATH = PROJECT_ROOT / "data" / "config.json"
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"
DEFAULT_LOG_DIR = PROJECT_ROOT / "logs"
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_MODELS_DIR = PROJECT_ROOT / "models"
DEFAULT_MEMORY_PATH = PROJECT_ROOT / "data" / "memory" / "memory.json"

LOG_FILE_NAME = "chad.log"

# --- Logging format -------------------------------------------------
LOG_CONSOLE_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_FILE_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s | %(filename)s:%(lineno)d | %(message)s"
)
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_MAX_BYTES = 5 * 1024 * 1024  # 5 MB per file before rotating
LOG_BACKUP_COUNT = 3

# --- Environment variable names ---------------------------------------
# Centralized here so config.py and providers never hardcode a string key.
ENV_OPENAI_API_KEY = "OPENAI_API_KEY"
ENV_ELEVENLABS_API_KEY = "ELEVENLABS_API_KEY"
ENV_ANTHROPIC_API_KEY = "ANTHROPIC_API_KEY"
ENV_GOOGLE_API_KEY = "GOOGLE_API_KEY"
ENV_LOG_LEVEL = "LOG_LEVEL"
ENV_CONFIG_PATH = "CONFIG_PATH"
ENV_WAKE_WORD_MODEL_PATH = "WAKE_WORD_MODEL_PATH"

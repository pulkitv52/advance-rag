import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src.core.config import get_settings

settings = get_settings()

# Ensure log directory exists (if running outside of Makefile)
# Path to logs/backend relative to the project root
# Root is one level up from 'backend/'
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
LOG_DIR = PROJECT_ROOT / "logs" / "backend"
LOG_FILE = LOG_DIR / "app.log"

if not LOG_DIR.exists():
    os.makedirs(LOG_DIR, exist_ok=True)

# Define format
log_format = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# Root logger setup
root_logger = logging.getLogger()
root_logger.setLevel(getattr(logging, settings.LOG_LEVEL))

# Cleanup any existing handlers (like from basicConfig)
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)

# ── Console Handler ─────────────────────────────────────────────
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_format)
root_logger.addHandler(console_handler)

# ── File Handler (Rotating) ─────────────────────────────────────
file_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=10 * 1024 * 1024,  # 10MB
    backupCount=5,
)
file_handler.setFormatter(log_format)
root_logger.addHandler(file_handler)

# Create the application logger
logger = logging.getLogger("adv_rag")

logger.info("Initializing Advance-Rag logger...")
logger.info(f"Persistent logs will be saved to: {LOG_FILE}")

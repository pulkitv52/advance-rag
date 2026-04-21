import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/logs", tags=["Logs"])

# Path to logs/frontend relative to the project root
# Root is one level up from 'backend/'
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
LOG_DIR = PROJECT_ROOT / "logs" / "frontend"
LOG_FILE = LOG_DIR / "app.log"

if not LOG_DIR.exists():
    os.makedirs(LOG_DIR, exist_ok=True)


class RemoteLogEntry(BaseModel):
    level: str
    message: str
    url: Optional[str] = None
    stack: Optional[str] = None


@router.post("/frontend")
async def receive_frontend_log(entry: RemoteLogEntry, request: Request):
    """
    Receives a log entry from the frontend and appends it to logs/frontend/app.log.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    client_host = request.client.host if request.client else "unknown"

    log_line = (
        f"{timestamp} [{entry.level.upper()}] [BROWSER] {client_host} | "
        f"URL: {entry.url} | MSG: {entry.message}"
    )

    if entry.stack:
        log_line += f"\nSTACK: {entry.stack}"

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_line + "\n")

    return {"status": "ok"}

import os
from pathlib import Path
import secrets

BASE_DIR = Path(__file__).resolve().parent

class Config:
    # Set SECRET_KEY in the environment for deployments. A per-run fallback is
    # acceptable only for local demos and intentionally invalidates old sessions.
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    DATABASE = os.environ.get("DATABASE_PATH", str(BASE_DIR / "logicai.db"))
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@logicai.local")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"

"""Configuration, SQLite database, settings store and authentication."""
import json
import os
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
MODELS = ROOT / "models"
STORE = Path(os.environ.get("AGRIMIND_STORE", ROOT / "storage"))
UPLOADS = STORE / "uploads"
for p in (STORE, UPLOADS):
    p.mkdir(parents=True, exist_ok=True)
DB_PATH = STORE / "agrimind.db"

try:  # optional .env support without extra dependency
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))
except FileNotFoundError:
    pass

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
  password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'farmer', active INTEGER NOT NULL DEFAULT 1,
  language TEXT DEFAULT 'en', created_at REAL NOT NULL, last_login REAL);
CREATE TABLE IF NOT EXISTS conversations (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, title TEXT,
  created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY, conversation_id INTEGER NOT NULL, role TEXT NOT NULL,
  content TEXT NOT NULL, citations TEXT, meta TEXT, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS documents (id INTEGER PRIMARY KEY, filename TEXT NOT NULL, title TEXT, file_type TEXT,
  size_bytes INTEGER, n_chunks INTEGER DEFAULT 0, uploaded_by INTEGER, is_demo INTEGER DEFAULT 0,
  created_at REAL NOT NULL, sha256 TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS chunks (id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL, idx INTEGER NOT NULL,
  text TEXT NOT NULL, page INTEGER);
CREATE TABLE IF NOT EXISTS query_logs (id INTEGER PRIMARY KEY, user_id INTEGER, feature TEXT, query TEXT,
  language TEXT, provider TEXT, model TEXT, latency_ms REAL, n_sources INTEGER, groundedness REAL, ok INTEGER,
  error TEXT, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS eval_runs (id INTEGER PRIMARY KEY, kind TEXT NOT NULL, config TEXT, summary TEXT,
  details TEXT, created_by INTEGER, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS market_prices (id INTEGER PRIMARY KEY, state TEXT, district TEXT, market TEXT,
  commodity TEXT, variety TEXT, grade TEXT, arrival_date TEXT, min_price REAL, max_price REAL, modal_price REAL,
  source TEXT, UNIQUE(market, commodity, variety, grade, arrival_date));
CREATE INDEX IF NOT EXISTS ix_chunks_doc ON chunks(document_id);
CREATE INDEX IF NOT EXISTS ix_msg_conv ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS ix_price ON market_prices(commodity, arrival_date);
"""

_lock = threading.RLock()


@contextmanager
def db():
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    try:
        with _lock:
            yield con
            con.commit()
    finally:
        con.close()


def init_db():
    with db() as c:
        c.executescript(SCHEMA)
        # migrate installs that were configured for Gemini
        c.execute("DELETE FROM settings WHERE key IN ('gemini_api_key','gemini_model')")
        c.execute("UPDATE settings SET value='xai' WHERE key='llm_provider' AND value IN ('gemini','grok')")


def rows(sql, params=()):
    with db() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def row(sql, params=()):
    r = rows(sql, params)
    return r[0] if r else None


def execute(sql, params=()):
    with db() as c:
        cur = c.execute(sql, params)
        return cur.lastrowid


# ---------------------------------------------------------------- settings
DEFAULTS = {
    "llm_provider": os.environ.get("LLM_PROVIDER", "xai"),  # xai | ollama
    "xai_api_key": "" if os.environ.get("XAI_API_KEY", "").startswith("your_") else os.environ.get("XAI_API_KEY", ""),
    "xai_base_url": os.environ.get("XAI_BASE_URL", "https://api.x.ai/v1"),
    "xai_model": os.environ.get("XAI_MODEL", "grok-4-1-fast-reasoning"),
    "ollama_url": os.environ.get("OLLAMA_URL", "http://localhost:11434"),
    "ollama_model": os.environ.get("OLLAMA_MODEL", "llama3.2:3b"),
    "embedding_model": os.environ.get("EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"),
    "temperature": "0.3",
    "llm_timeout": os.environ.get("LLM_TIMEOUT", "90"),
    "top_k": "4",
    "chunk_size": "900",
    "chunk_overlap": "150",
    "grounding_threshold": "0.55",
    "data_gov_api_key": os.environ.get("DATA_GOV_API_KEY", ""),
}
SECRET_KEYS = {"xai_api_key", "data_gov_api_key"}


def get_setting(key):
    r = row("SELECT value FROM settings WHERE key=?", (key,))
    return r["value"] if r and r["value"] not in (None, "") else DEFAULTS.get(key, "")


def all_settings():
    """Settings for the admin UI. Secrets are never returned: only whether they are set and where from."""
    out = {k: get_setting(k) for k in DEFAULTS if k not in SECRET_KEYS}
    for k in SECRET_KEYS:
        stored = row("SELECT value FROM settings WHERE key=?", (k,))
        out[f"{k}_set"] = bool(get_setting(k))
        out[f"{k}_source"] = "admin" if stored and stored["value"] else ("env" if DEFAULTS.get(k) else None)
    if out["llm_provider"] in ("gemini", "grok"):
        out["llm_provider"] = "xai"
    return out


def set_setting(key, value):
    if key not in DEFAULTS:
        raise HTTPException(400, f"Unknown setting {key}")
    if value is None:  # clear -> fall back to the environment default
        execute("DELETE FROM settings WHERE key=?", (key,))
        return
    execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)))


# ---------------------------------------------------------------- auth
_secret_file = STORE / ".jwt_secret"
if not _secret_file.exists():
    _secret_file.write_text(secrets.token_urlsafe(48))
JWT_SECRET = os.environ.get("JWT_SECRET") or _secret_file.read_text().strip()
TOKEN_HOURS = 24
bearer = HTTPBearer(auto_error=False)


def hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode()[:72], bcrypt.gensalt()).decode()


def check_pw(pw: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode()[:72], h.encode())
    except ValueError:
        return False


def make_token(user):
    return jwt.encode({"sub": str(user["id"]), "role": user["role"], "exp": int(time.time()) + TOKEN_HOURS * 3600},
                      JWT_SECRET, algorithm="HS256")


def current_user(cred: HTTPAuthorizationCredentials = Depends(bearer)):
    if not cred:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = jwt.decode(cred.credentials, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    u = row("SELECT id,email,name,role,active,language,created_at FROM users WHERE id=?", (int(payload["sub"]),))
    if not u or not u["active"]:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account disabled or missing")
    return u


def admin_user(u=Depends(current_user)):
    if u["role"] != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    return u


def log_query(user_id, feature, query, **kw):
    execute("INSERT INTO query_logs(user_id,feature,query,language,provider,model,latency_ms,n_sources,groundedness,ok,"
            "error,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (user_id, feature, (query or "")[:2000], kw.get("language"), kw.get("provider"), kw.get("model"),
             kw.get("latency_ms"), kw.get("n_sources"), kw.get("groundedness"), int(kw.get("ok", True)),
             kw.get("error"), time.time()))


def jdump(o):
    return json.dumps(o, ensure_ascii=False)

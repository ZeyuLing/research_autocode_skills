#!/usr/bin/env python3
"""TODO Dashboard — Multi-project web UI for managing autorun tasks.

Manages multiple projects from a single web server. Each project has its own
.claude/ directory with independent DB, skills, and context. Projects are
registered dynamically from the web UI.

Usage:
    # Start with one project (auto-detected from cwd or explicit):
    python app.py --port 8081
    python app.py --port 8081 --project /path/to/project1

    # Add more projects from the web UI at runtime.
"""
import argparse
import json
import os
import re
import select
import signal
import sqlite3
import subprocess
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path

import yaml

from flask import Flask, render_template, request, jsonify, abort, redirect, url_for, make_response

SCRIPT_DIR = Path(__file__).resolve().parent
TASK_MANAGER = SCRIPT_DIR / "task_manager.py"
META_DIR = SCRIPT_DIR.parent / ".dashboard"
PROJECTS_FILE = META_DIR / "projects.json"
TAIJI_TOKEN_FILE = META_DIR / "taiji_token"

app = Flask(__name__, template_folder=str(SCRIPT_DIR / "templates"))

# ───────────────────────────────────────────────────────────────────────────
# Performance: dop-fuse (cephfs-over-FUSE) makes every SQLite open expensive
# (~2s per connect+PRAGMA+close). To compensate we:
#   • run ensure_db() at most once per DB path per process
#   • skip re-setting PRAGMA journal_mode=WAL on every get_db() (it's a
#     persistent DB-header flag; one-time is enough)
#   • cache get_all_projects_with_meta() results for a few seconds
# ───────────────────────────────────────────────────────────────────────────
_DB_READY: set = set()         # abs paths of DBs whose schema is up-to-date
_STATS_CACHE: dict = {}         # key -> (expires_at_epoch, value)
_STATS_CACHE_TTL = 15.0         # seconds — longer than frontend poll interval (~5s)

# Idempotency guard for POST /api/tasks — collapses double-submits
# (frontend double-click, Ctrl+Enter×2, retried fetch, etc.) within a short window.
# key = (slug, client_nonce) OR (slug, desc_signature); value = (expires_at, task_id, skill)
_CREATE_DEDUP: dict = {}
_CREATE_DEDUP_TTL = 5.0         # seconds — a second POST inside this window is the SAME intent
_CREATE_DEDUP_LOCK = threading.Lock()


def get_taiji_token():
    """Read taiji token from persistent file."""
    try:
        if TAIJI_TOKEN_FILE.exists():
            return TAIJI_TOKEN_FILE.read_text().strip()
    except Exception:
        pass
    return ""


def set_taiji_token(token: str):
    """Write taiji token to persistent file."""
    META_DIR.mkdir(parents=True, exist_ok=True)
    TAIJI_TOKEN_FILE.write_text(token.strip())
    # Also set env for current process so child processes inherit it
    os.environ["TOKEN"] = token.strip()


# ═══════════════════════════════════════════════════════════════════════════
# Security — localhost-only write protection
# ═══════════════════════════════════════════════════════════════════════════

def _is_localhost():
    """Check if the request originates from localhost (127.0.0.1 / ::1)."""
    remote = request.remote_addr or ""
    return remote in ("127.0.0.1", "::1", "localhost")


# ═══════════════════════════════════════════════════════════════════════════
# Project registry — persisted in ~/.claude-dashboard/projects.json
# ═══════════════════════════════════════════════════════════════════════════

def _load_projects():
    """Load registered projects from disk. Returns list of project dicts."""
    if PROJECTS_FILE.exists():
        try:
            return json.loads(PROJECTS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return []


def _save_projects(projects):
    META_DIR.mkdir(parents=True, exist_ok=True)
    PROJECTS_FILE.write_text(json.dumps(projects, indent=2, ensure_ascii=False))


def _project_slug(path_str):
    """Short identifier derived from path: last component of the resolved path."""
    return Path(path_str).resolve().name


def register_project(path_str):
    """Register a new project directory. Idempotent."""
    p = Path(path_str).resolve()
    if not p.is_dir():
        return False, f"目录不存在: {p}"
    projects = _load_projects()
    existing_paths = {proj["path"] for proj in projects}
    if str(p) in existing_paths:
        return True, "已注册"
    slug = _project_slug(p)
    # Deduplicate slugs by appending parent
    existing_slugs = {proj["slug"] for proj in projects}
    if slug in existing_slugs:
        slug = f"{p.parent.name}_{slug}"
    projects.append({
        "path": str(p),
        "slug": slug,
        "name": p.name,
        "added_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })
    _save_projects(projects)
    return True, slug


def unregister_project(slug):
    projects = _load_projects()
    projects = [p for p in projects if p["slug"] != slug]
    _save_projects(projects)


def get_registered_projects():
    return _load_projects()


def find_project_by_slug(slug):
    for p in _load_projects():
        if p["slug"] == slug:
            return p
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Per-project paths — derived from project root, no globals
# ═══════════════════════════════════════════════════════════════════════════

class ProjectPaths:
    """All paths for a given project, computed on the fly.

    Persistence strategy
    ────────────────────
    All *writable* data (DB, notes) lives under the centralised dashboard store:
        cc_skills/.dashboard/data/<slug>/
            autorun-tasks.db   ← SQLite task database
            project_notes.md   ← project-level markdown notes

    Source-tree paths (skills, TODO_LIST.md) are still read from the project
    directory, but we never write there — so read-only mounts (apdcephfs etc.)
    always work fine.
    """
    def __init__(self, root_str, slug=None):
        self.root = Path(root_str).resolve()
        self.name = self.root.name
        self.slug = slug or self.root.name
        # Centralised writable store — always on local disk
        self._store = META_DIR / "data" / self.slug
        self.db = self._store / "autorun-tasks.db"
        self.context_file = self._store / "project_notes.md"
        # Read-only project-tree paths
        self.skills_dir = self.root / ".claude" / "skills"
        self.todo_file = self.root / "TODO_LIST.md"
        # Legacy: also read notes from project tree if local store is empty
        self._legacy_context = self.root / ".claude" / "project_context.md"
        self._legacy_db = self.root / ".claude" / "autorun-tasks.db"

    def ensure_db(self):
        # Fast path: already initialized this process → skip expensive
        # schema probes (18× SELECT round-trips on dop-fuse)
        db_key = str(self.db)
        if db_key in _DB_READY:
            return
        self._store.mkdir(parents=True, exist_ok=True)
        # One-time migration: copy legacy DB if local store is empty
        if not self.db.exists() and self._legacy_db.exists():
            try:
                import shutil
                shutil.copy2(str(self._legacy_db), str(self.db))
            except Exception:
                pass
        conn = self.get_db()
        conn.executescript(_CREATE_TABLES_SQL)
        for col, coldef in [
            ("skill",                "TEXT"),
            ("project_path",         "TEXT"),
            ("agent_id",             "TEXT"),
            ("agent_status",         "TEXT DEFAULT 'none'"),
            ("acceptance_type",      "TEXT NOT NULL DEFAULT 'auto'"),
            ("acceptance_criteria",  "TEXT"),
            ("human_review",         "INTEGER NOT NULL DEFAULT 0"),
            ("auto_execute",         "INTEGER NOT NULL DEFAULT 1"),
            ("cost_usd",             "REAL"),
            ("total_input_tokens",   "INTEGER"),
            ("total_output_tokens",  "INTEGER"),
            ("config_user",          "TEXT"),
            ("max_cost_usd",         "REAL DEFAULT 5.0"),
            ("model",                "TEXT DEFAULT 'sonnet'"),
            ("effort",               "TEXT DEFAULT 'medium'"),
            ("archived",             "INTEGER NOT NULL DEFAULT 0"),
            ("session_id",           "TEXT"),
            ("estimated_cost_usd",   "REAL"),
            ("interactive",          "INTEGER NOT NULL DEFAULT 0"),
            ("jsonl_offset",         "INTEGER NOT NULL DEFAULT 0"),
            ("cache_create_tokens",  "INTEGER"),
            ("cache_read_tokens",    "INTEGER"),
        ]:
            try:
                conn.execute(f"SELECT {col} FROM tasks LIMIT 1")
            except sqlite3.OperationalError:
                conn.execute(f"ALTER TABLE tasks ADD COLUMN {col} {coldef}")
        conn.commit()
        conn.close()
        _DB_READY.add(db_key)

    def get_db(self):
        db_key = str(self.db)
        first_time = db_key not in _DB_READY
        if first_time:
            self._store.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db))
        conn.row_factory = sqlite3.Row
        # WAL is a persistent DB-header flag — setting it once is enough.
        # Skipping on hot path saves a round-trip (~100ms on dop-fuse).
        if first_time:
            try:
                conn.execute("PRAGMA journal_mode=WAL")
            except sqlite3.OperationalError:
                pass  # read-only fallback — should never happen with centralised store
        conn.execute("PRAGMA foreign_keys=ON")
        return conn


_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS tasks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    description     TEXT NOT NULL,
    tag             TEXT,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','in_progress','completed','failed','decomposed')),
    parent_id       INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    position        REAL NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M','now','localtime')),
    started_at      TEXT,
    completed_at    TEXT,
    duration_minutes REAL,
    conclusion      TEXT,
    modified_files  TEXT,
    notes           TEXT,
    skill           TEXT,
    project_path    TEXT,
    agent_id        TEXT,
    agent_status    TEXT DEFAULT 'none'
                    CHECK (agent_status IN ('none','running','idle','done')),
    acceptance_type TEXT NOT NULL DEFAULT 'auto'
                    CHECK (acceptance_type IN ('human','test','file','custom','auto')),
    acceptance_criteria TEXT,
    human_review    INTEGER NOT NULL DEFAULT 0,
    auto_execute    INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS task_relations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id       INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    target_id       INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    relation_type   TEXT NOT NULL CHECK (relation_type IN ('blocks','conflicts','related')),
    note            TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M','now','localtime')),
    UNIQUE(source_id, target_id, relation_type)
);
CREATE TABLE IF NOT EXISTS context_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id         INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    entry_type      TEXT NOT NULL DEFAULT 'insight'
                    CHECK (entry_type IN ('insight','decision','warning','note')),
    content         TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M','now','localtime'))
);
CREATE TABLE IF NOT EXISTS task_messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id         INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('user','agent','system')),
    content         TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'done'
                    CHECK (status IN ('done','pending_send','sending')),
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M','now','localtime'))
);
"""

_MIGRATE_SQL = """
ALTER TABLE tasks ADD COLUMN agent_id TEXT;
ALTER TABLE tasks ADD COLUMN agent_status TEXT DEFAULT 'none';
"""


def _get_pp():
    """Get ProjectPaths for the current request's ?p= parameter."""
    slug = request.args.get("p") or request.form.get("p")
    if not slug:
        slug = request.cookies.get("last_project")
    if slug:
        proj = find_project_by_slug(slug)
        if proj:
            return ProjectPaths(proj["path"], slug=proj["slug"]), slug
    # Fallback: first registered project
    projects = get_registered_projects()
    if projects:
        p = projects[0]
        return ProjectPaths(p["path"], slug=p["slug"]), p["slug"]
    return None, None


def _get_pp_or_404():
    pp, slug = _get_pp()
    if pp is None:
        abort(404)
    return pp, slug


# ═══════════════════════════════════════════════════════════════════════════
# DB query helpers (all take conn as parameter, no globals)
# ═══════════════════════════════════════════════════════════════════════════

def row_to_dict(row):
    return dict(row) if row else None


def get_counts(conn):
    rows = conn.execute("SELECT status, COUNT(*) as c FROM tasks GROUP BY status").fetchall()
    c = {r["status"]: r["c"] for r in rows}
    total = sum(c.values())
    active = total - c.get("decomposed", 0)
    return {"pending": c.get("pending", 0), "in_progress": c.get("in_progress", 0),
            "completed": c.get("completed", 0), "failed": c.get("failed", 0),
            "decomposed": c.get("decomposed", 0), "total": total, "active_total": active}


def get_tasks(conn, status_filter="all"):
    if status_filter and status_filter != "all":
        rows = conn.execute("SELECT * FROM tasks WHERE status=? ORDER BY position ASC", (status_filter,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM tasks ORDER BY position ASC").fetchall()
    return [row_to_dict(r) for r in rows]


def get_task_relations(conn, task_id):
    out = conn.execute(
        "SELECT r.*, t.description as target_desc, t.status as target_status, t.tag as target_tag "
        "FROM task_relations r JOIN tasks t ON r.target_id=t.id WHERE r.source_id=?", (task_id,)).fetchall()
    inc = conn.execute(
        "SELECT r.*, t.description as source_desc, t.status as source_status, t.tag as source_tag "
        "FROM task_relations r JOIN tasks t ON r.source_id=t.id WHERE r.target_id=?", (task_id,)).fetchall()
    result = {"blocks": [], "blocked_by": [], "conflicts": [], "related": []}
    for r in out:
        d = row_to_dict(r)
        e = {"relation_id": d["id"], "task_id": d["target_id"], "description": d["target_desc"],
             "status": d["target_status"], "tag": d["target_tag"], "note": d["note"]}
        result[{"blocks": "blocks", "conflicts": "conflicts", "related": "related"}[r["relation_type"]]].append(e)
    for r in inc:
        d = row_to_dict(r)
        e = {"relation_id": d["id"], "task_id": d["source_id"], "description": d["source_desc"],
             "status": d["source_status"], "tag": d["source_tag"], "note": d["note"]}
        if r["relation_type"] == "blocks":
            result["blocked_by"].append(e)
        else:
            key = r["relation_type"]  # conflicts or related
            already = {x["task_id"] for x in result[key]}
            if d["source_id"] not in already:
                result[key].append(e)
    return result


def get_all_relations(conn):
    rows = conn.execute(
        "SELECT r.id,r.source_id,r.target_id,r.relation_type,r.note,"
        "s.description as source_desc,s.status as source_status,"
        "t.description as target_desc,t.status as target_status "
        "FROM task_relations r JOIN tasks s ON r.source_id=s.id JOIN tasks t ON r.target_id=t.id ORDER BY r.id"
    ).fetchall()
    return [row_to_dict(r) for r in rows]


def check_blocked(conn, tid):
    rows = conn.execute(
        "SELECT t.id,t.description,t.status FROM task_relations r JOIN tasks t ON r.source_id=t.id "
        "WHERE r.target_id=? AND r.relation_type='blocks' AND t.status NOT IN ('completed','decomposed')",
        (tid,)).fetchall()
    return [row_to_dict(r) for r in rows]


def check_conflicts_active(conn, tid):
    rows = conn.execute(
        "SELECT DISTINCT t.id,t.description,t.status FROM ("
        "  SELECT target_id as tid FROM task_relations WHERE source_id=? AND relation_type='conflicts'"
        "  UNION SELECT source_id FROM task_relations WHERE target_id=? AND relation_type='conflicts'"
        ") c JOIN tasks t ON c.tid=t.id WHERE t.status='in_progress'",
        (tid, tid)).fetchall()
    return [row_to_dict(r) for r in rows]


def get_context_log(conn, limit=50, task_id=None):
    if task_id:
        rows = conn.execute(
            "SELECT cl.*,t.description as task_desc FROM context_log cl "
            "LEFT JOIN tasks t ON cl.task_id=t.id WHERE cl.task_id=? ORDER BY cl.id DESC LIMIT ?",
            (task_id, limit)).fetchall()
    else:
        rows = conn.execute(
            "SELECT cl.*,t.description as task_desc FROM context_log cl "
            "LEFT JOIN tasks t ON cl.task_id=t.id ORDER BY cl.id DESC LIMIT ?", (limit,)).fetchall()
    return [row_to_dict(r) for r in rows]


def get_task_messages(conn, task_id, limit=200):
    """Return messages for a task.  When limit is set, returns the LAST N messages
    (most recent), ordered ASC so the UI can render top-to-bottom chronologically.
    Returns (messages_list, has_more_before) tuple when limit is set.
    """
    if limit:
        # Count total to know if there are older messages
        total = conn.execute(
            "SELECT COUNT(*) FROM task_messages WHERE task_id=?", (task_id,)).fetchone()[0]
        has_more = total > limit
        rows = conn.execute(
            "SELECT * FROM task_messages WHERE task_id=? ORDER BY id DESC LIMIT ?",
            (task_id, limit)).fetchall()
        rows = list(reversed(rows))  # back to ASC order
        return [row_to_dict(r) for r in rows], has_more
    else:
        rows = conn.execute(
            "SELECT * FROM task_messages WHERE task_id=? ORDER BY id ASC", (task_id,)).fetchall()
        return [row_to_dict(r) for r in rows], False


def add_task_message(conn, task_id, role, content, status="done"):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.execute(
        "INSERT INTO task_messages (task_id, role, content, status, created_at) VALUES (?,?,?,?,?)",
        (task_id, role, content, status, now))
    conn.commit()
    return cur.lastrowid


def get_pending_messages(conn):
    """Return all user messages waiting to be sent to agents (status=pending_send)."""
    rows = conn.execute(
        "SELECT tm.*, t.agent_id, t.agent_status FROM task_messages tm "
        "JOIN tasks t ON tm.task_id=t.id "
        "WHERE tm.status='pending_send' ORDER BY tm.id ASC").fetchall()
    return [row_to_dict(r) for r in rows]


def _has_path(conn, from_id, to_id, rel_type, visited=None):
    if visited is None: visited = set()
    if from_id == to_id: return True
    if from_id in visited: return False
    visited.add(from_id)
    for row in conn.execute("SELECT target_id FROM task_relations WHERE source_id=? AND relation_type=?",
                            (from_id, rel_type)).fetchall():
        if _has_path(conn, row["target_id"], to_id, rel_type, visited): return True
    return False


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# ═══════════════════════════════════════════════════════════════════════════
# TaskExecutor — auto-execute tasks via Claude Code headless process
# ═══════════════════════════════════════════════════════════════════════════

CLAUDE_CODE_BIN = os.environ.get(
    "CLAUDE_CODE_BIN",
    os.path.expanduser("~/.npm/node_modules/lib/node_modules/@tencent/claude-code-internal/dist/claude-code-internal.js"),
)
NODE_BIN = os.environ.get(
    "NODE_BIN",
    "/codev/opt/nodejs/20.10.0/bin/node",
)
CONFIG_DIR = SCRIPT_DIR.parent  # cc_skills/ directory containing *.json configs


def get_available_configs():
    """Return list of user config names (without .json extension)."""
    configs = []
    for f in sorted(CONFIG_DIR.glob("*.json")):
        configs.append(f.stem)  # e.g. "hannliu", "chingshuai"
    return configs


def load_user_config(username: str) -> dict:
    """Load a user's OAuth config from cc_skills/<username>.json."""
    p = CONFIG_DIR / f"{username}.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


_global_model_lock = threading.Lock()

# Regex matching ANSI escape sequences (e.g. \x1b[1m, \x1b[0;32m) and
# broken bracket-only remnants (e.g. "[1m]", "[0;32m]") that appear when
# env vars are copied from formatted terminal output. Also strips trailing
# brackets left over from partial matches.
_ANSI_ESCAPE_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]\]?|\[[0-9;]*[a-zA-Z]\]?')


def _strip_ansi(s: str) -> str:
    """Strip ANSI escape codes and bracket remnants from a string."""
    return _ANSI_ESCAPE_RE.sub('', s)


def _set_global_model(model_id: str):
    """Write model to the global settings.json that claude-code-internal reads.

    claude-code-internal determines its model from the "model" field in
    $CLAUDE_SETTINGS_DIR/settings.json (or $CLAUDE_CONFIG_DIR/settings.json).
    This function atomically updates that field.

    Uses a threading lock to prevent race conditions when multiple tasks
    start concurrently and try to write different models.
    """
    with _global_model_lock:
        settings_dir = Path(os.environ.get("CLAUDE_SETTINGS_DIR",
                             os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))))
        settings_file = settings_dir / "settings.json"
        try:
            current = json.loads(settings_file.read_text()) if settings_file.exists() else {}
        except Exception:
            current = {}
        current["model"] = model_id
        settings_dir.mkdir(parents=True, exist_ok=True)
        settings_file.write_text(json.dumps(current, indent=2, ensure_ascii=False))


def _set_global_model_settings(settings_dict: dict):
    """Write model+effort to ~/.claude-internal/settings.json.

    The Tencent claude-code-internal wrapper hard-codes
    CLAUDE_CONFIG_DIR=~/.claude-internal and strips any env overrides,
    so this is the ONLY path CC will read user settings from.

    Acquires the global lock and holds it so the caller can spawn the
    subprocess before another task overwrites the file.
    NOTE: The lock is released automatically when this function returns;
    for race-free spawn, the caller should spawn immediately after.
    """
    with _global_model_lock:
        settings_dir = Path.home() / ".claude-internal"
        settings_file = settings_dir / "settings.json"
        try:
            current = json.loads(settings_file.read_text()) if settings_file.exists() else {}
        except Exception:
            current = {}
        current.update(settings_dict)
        settings_dir.mkdir(parents=True, exist_ok=True)
        settings_file.write_text(json.dumps(current, indent=2, ensure_ascii=False))


class TaskExecutor:
    """Manages Claude Code headless processes for auto-executing tasks.

    Each task gets its own daemon thread that:
    1. Launches `claude -p <prompt> --output-format stream-json --permission-mode dontAsk`
    2. Reads stdout line-by-line, parsing stream-json events
    3. Writes execution log entries to task_messages
    4. Updates task status on completion/failure
    """

    def __init__(self):
        self._threads: dict[int, threading.Thread] = {}    # task_id -> Thread
        self._stopped: set[int] = set()                     # task_ids manually stopped
        self._lock = threading.Lock()

    # ── PID / log file helpers ──────────────────────────────────────────

    @staticmethod
    def _logs_dir(pp: "ProjectPaths") -> Path:
        d = pp._store / "logs"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @staticmethod
    def _pids_dir(pp: "ProjectPaths") -> Path:
        d = pp._store / "pids"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _log_path(self, pp, task_id):
        return self._logs_dir(pp) / f"{task_id}.jsonl"

    def _pid_path(self, pp, task_id):
        return self._pids_dir(pp) / f"{task_id}.json"

    def _write_pid(self, pp, task_id, pid, pgid):
        self._pid_path(pp, task_id).write_text(
            json.dumps({"pid": pid, "pgid": pgid, "task_id": task_id,
                        "project_slug": pp.slug, "started": now_str()}))

    def _read_pid(self, pp, task_id):
        p = self._pid_path(pp, task_id)
        if p.exists():
            try:
                return json.loads(p.read_text())
            except Exception:
                pass
        return None

    def _remove_pid(self, pp, task_id):
        try:
            p = self._pid_path(pp, task_id)
            if p.exists():
                p.unlink()
        except Exception:
            pass

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        """Check if a process with given PID is still running."""
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False

    @staticmethod
    def _drain_stderr_nonblocking(proc, max_bytes: int = 2000, timeout: float = 0.5) -> str:
        """Read whatever is currently available on proc.stderr WITHOUT blocking
        on a live subprocess.

        Background: task #33 hung for ~35 minutes because `proc.stderr.read()`
        blocks until stderr reaches EOF — and stderr only hits EOF when the
        subprocess exits. When CC was alive but slow to create its session
        JSONL, the tail-log 30s wait fell through and then sat inside
        `proc.stderr.read()` silently for the entire CC run, producing no DB
        writes and making the UI look frozen.

        This helper uses `select` + non-blocking reads so it returns whatever
        stderr bytes are already buffered within `timeout` seconds, never
        more. Safe to call on a live subprocess.
        """
        if proc is None or proc.stderr is None:
            return ""
        try:
            fd = proc.stderr.fileno()
        except Exception:
            return ""
        # If the process has already exited, a plain read is safe and fast.
        if proc.poll() is not None:
            try:
                return proc.stderr.read().decode("utf-8", errors="replace")[:max_bytes]
            except Exception:
                return ""
        # Live process: poll stderr with select, read only what's ready.
        chunks: list[bytes] = []
        total = 0
        deadline = None
        try:
            import time as _t
            deadline = _t.monotonic() + max(0.0, timeout)
            while total < max_bytes:
                remaining = deadline - _t.monotonic()
                if remaining <= 0:
                    break
                r, _, _ = select.select([fd], [], [], min(remaining, 0.1))
                if not r:
                    # Nothing ready right now — bail, don't block.
                    break
                try:
                    chunk = os.read(fd, min(4096, max_bytes - total))
                except BlockingIOError:
                    break
                except Exception:
                    break
                if not chunk:
                    # EOF — process closed stderr.
                    break
                chunks.append(chunk)
                total += len(chunk)
        except Exception:
            pass
        try:
            return b"".join(chunks).decode("utf-8", errors="replace")[:max_bytes]
        except Exception:
            return ""

    # ── Public API ──────────────────────────────────────────────────────

    def start_task(self, task_id: int, pp: "ProjectPaths", prompt: str,
                    config_user: str = None, model: str = None, effort: str = None,
                    resume_session_id: str = None):
        """Launch a Claude Code process for the given task."""
        with self._lock:
            if task_id in self._threads:
                return False  # already running
            self._threads[task_id] = None  # placeholder

        thread = threading.Thread(
            target=self._run_task,
            args=(task_id, pp, prompt, config_user, model, effort, resume_session_id),
            daemon=True,
            name=f"executor-task-{task_id}",
        )
        with self._lock:
            self._threads[task_id] = thread
        thread.start()
        return True

    def stop_task(self, task_id: int, pp: "ProjectPaths" = None) -> bool:
        """Terminate a running Claude Code process."""
        with self._lock:
            self._stopped.add(task_id)

        # Try to get pgid from PID file (works even after server restart)
        pgid = None
        if pp:
            info = self._read_pid(pp, task_id)
            if info:
                pgid = info.get("pgid")

        if pgid is None:
            return False
        try:
            os.killpg(pgid, signal.SIGTERM)
            import time; time.sleep(2)
            # Check if still alive, force kill
            if self._pid_alive(pgid):
                os.killpg(pgid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass
        if pp:
            self._remove_pid(pp, task_id)
        return True

    def is_running(self, task_id: int, pp: "ProjectPaths" = None) -> bool:
        with self._lock:
            if task_id in self._threads:
                return True
        # Fallback: check PID file (process may have survived server restart)
        if pp:
            info = self._read_pid(pp, task_id)
            if info and self._pid_alive(info["pid"]):
                return True
        return False

    def _log(self, pp: "ProjectPaths", task_id: int, event: str, message: str):
        """Write a system message to task_messages."""
        content = f"[{event}] {message}"
        try:
            conn = pp.get_db()
            add_task_message(conn, task_id, "system", content, status="done")
            conn.close()
        except Exception:
            pass

    def _update_cost(self, pp: "ProjectPaths", task_id: int, cost_usd: float,
                     input_tokens: int = None, output_tokens: int = None,
                     cache_create_tokens: int = None, cache_read_tokens: int = None):
        """Update running estimated cost and token counts in DB without changing status."""
        try:
            conn = pp.get_db()
            updates = ["estimated_cost_usd=?"]
            values = [round(cost_usd, 4)]
            if input_tokens is not None:
                updates.append("total_input_tokens=?")
                values.append(input_tokens)
            if output_tokens is not None:
                updates.append("total_output_tokens=?")
                values.append(output_tokens)
            if cache_create_tokens is not None:
                updates.append("cache_create_tokens=?")
                values.append(cache_create_tokens)
            if cache_read_tokens is not None:
                updates.append("cache_read_tokens=?")
                values.append(cache_read_tokens)
            values.append(task_id)
            conn.execute(f"UPDATE tasks SET {','.join(updates)} WHERE id=?", values)
            conn.commit()
            conn.close()
        except Exception:
            pass

    @staticmethod
    def _model_pricing(model_name: str):
        """Return per-1M-token prices: (price_in, price_cache_create, price_cache_read, price_out).

        input_tokens in Anthropic usage excludes cache_read and cache_creation — they
        are reported as separate fields and priced differently:
          - cache_creation_input_tokens ≈ 1.25× input price (write premium)
          - cache_read_input_tokens     ≈ 0.10× input price (read discount)

        Pricing tiers (May 2026):
          - Opus 4.5/4.6/4.7:   $5 / $6.25 / $0.50 / $25
          - Sonnet 4/4.5/4.6:   $3 / $3.75 / $0.30 / $15
          - Haiku 4.5:           $1 / $1.25 / $0.10 / $5
          - Haiku 3.5:           $0.80 / $1.00 / $0.08 / $4
        """
        m = (model_name or "").lower()
        if "opus" in m:
            return (5.0, 6.25, 0.50, 25.0)
        if "haiku" in m:
            # Haiku 4.5 vs 3.5: detect by model name
            if "3.5" in m or "3-5" in m:
                return (0.80, 1.00, 0.08, 4.0)
            # Default to Haiku 4.5 pricing (current generation)
            return (1.0, 1.25, 0.10, 5.0)
        # default: sonnet
        return (3.0, 3.75, 0.30, 15.0)

    def _infer_rc_from_jsonl(self, jsonl_path, turn_count):
        """Infer process exit status from session JSONL when real exit code is unavailable.

        When recovering a task whose process is not our child (e.g., after server
        restart), we can't get the real exit code via waitpid. Instead, check the
        JSONL tail for evidence of clean vs interrupted exit:

        - If the last line is a 'result' event → clean exit → rc=0
        - If the last assistant message has stop='end_turn' with output_tokens > 0
          → Claude finished its response → rc=0
        - If the last assistant message has stop=None and output_tokens=0
          → interrupted mid-stream → rc=-1 (failed)
        - If there were turns but we can't determine → rc=-1 (fail-safe)
        """
        if not jsonl_path or not os.path.exists(jsonl_path):
            return 0 if turn_count > 0 else -1

        try:
            last_assistant = None
            has_result = False
            with open(jsonl_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    etype = ev.get("type", "")
                    if etype == "assistant":
                        last_assistant = ev
                    elif etype == "result":
                        has_result = True

            # 'result' event means Claude process exited cleanly
            if has_result:
                return 0

            # Check last assistant message
            if last_assistant:
                msg = last_assistant.get("message", {})
                stop = msg.get("stop_reason") or msg.get("stop")
                out_tok = msg.get("usage", {}).get("output_tokens", 0)

                if stop in ("end_turn",) and out_tok > 0:
                    # Claude finished its final response → clean exit
                    return 0
                elif stop == "tool_use" and out_tok > 0:
                    # Claude called a tool but never got the result → interrupted
                    return -1
                elif stop is None and out_tok == 0:
                    # Mid-stream interruption → crash
                    return -1

            # Can't determine — default to failed for safety
            return -1 if turn_count > 0 else -1
        except Exception:
            return 0 if turn_count > 0 else -1

    def _calculate_cost_from_jsonl(self, jsonl_path, model_hint=None):
        """Parse entire session JSONL and compute precise cost from usage fields.

        Returns (cost_usd, total_input_tokens, total_output_tokens).
        Falls back to (0, 0, 0) on any error.

        Correctness notes:
          - Each turn emits multiple assistant lines that share the same message.id
            and the same usage object. We dedupe by message.id so tokens are not
            counted N times for an N-block response.
          - Anthropic's `input_tokens` is already the *uncached* input count — we
            must NOT subtract cache_read from it. cache_creation and cache_read
            are additive, priced separately.
          - Final cost = (input*p_in + cache_create*p_cc + cache_read*p_cr + out*p_out)/1e6
        """
        total_in = 0            # uncached input
        total_out = 0
        total_cache_create = 0
        total_cache_read = 0
        # pricing — updated per observed model
        price_in, price_cache_create, price_cache_read, price_out = (
            self._model_pricing(model_hint or "sonnet"))
        seen_msg_ids = set()

        try:
            with open(str(jsonl_path), "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if event.get("type") != "assistant":
                        continue
                    msg = event.get("message", {})
                    # Detect model for pricing (stays on whichever model we last saw)
                    model_name = msg.get("model", "") or (model_hint or "")
                    if model_name:
                        price_in, price_cache_create, price_cache_read, price_out = (
                            self._model_pricing(model_name))
                    usage = msg.get("usage", {})
                    if not usage or usage.get("output_tokens", 0) <= 0:
                        # stream-start / pre-final events
                        continue
                    # Dedupe: one turn → many assistant lines sharing message.id
                    mid = msg.get("id")
                    if mid:
                        if mid in seen_msg_ids:
                            continue
                        seen_msg_ids.add(mid)
                    total_in += usage.get("input_tokens", 0)
                    total_out += usage.get("output_tokens", 0)
                    total_cache_create += usage.get("cache_creation_input_tokens", 0)
                    total_cache_read += usage.get("cache_read_input_tokens", 0)
        except Exception as e:
            print(f"[cost-jsonl] Error reading {jsonl_path}: {e}")
            return (0.0, 0, 0)

        cost = (
            total_in * price_in
            + total_cache_create * price_cache_create
            + total_cache_read * price_cache_read
            + total_out * price_out
        ) / 1_000_000
        # Return a logical "total input" including cache tokens so downstream
        # token displays reflect full billed input volume.
        logical_in = total_in + total_cache_create + total_cache_read
        return (round(cost, 6), logical_in, total_out)

    def _update_status(self, pp: "ProjectPaths", task_id: int, status: str,
                        cost_usd: float = None):
        """Update task status in DB."""
        try:
            conn = pp.get_db()
            updates = ["status=?"]
            values = [status]
            if cost_usd is not None:
                updates.append("cost_usd=?")
                values.append(round(cost_usd, 4))
            if status == "completed":
                ca = now_str()
                updates.append("completed_at=?")
                values.append(ca)
                row = conn.execute("SELECT started_at FROM tasks WHERE id=?", (task_id,)).fetchone()
                if row and row["started_at"]:
                    try:
                        d = (datetime.strptime(ca, "%Y-%m-%d %H:%M") -
                             datetime.strptime(row["started_at"], "%Y-%m-%d %H:%M")).total_seconds() / 60
                        updates.append("duration_minutes=?")
                        values.append(round(d, 1))
                    except ValueError:
                        pass
            values.append(task_id)
            conn.execute(f"UPDATE tasks SET {','.join(updates)} WHERE id=?", values)
            conn.commit()
            conn.close()
        except Exception:
            pass

    def _check_result_complete(self, result_text: str) -> bool:
        """Check if the result text indicates genuine task completion.

        Uses explicit TASK_COMPLETED / TASK_INCOMPLETE markers injected
        via the prompt preamble.  Falls back to keyword heuristics if
        the agent forgot to include a marker.
        """
        if "TASK_COMPLETED" in result_text and "TASK_INCOMPLETE" not in result_text:
            return True
        if "TASK_INCOMPLETE" in result_text:
            return False
        # No marker found — be conservative: treat as incomplete
        return False

    # Prompt template — loaded from file, cached in memory
    _prompt_cache: str = ""
    _prompt_mtime: float = 0
    _PROMPT_FILE = SCRIPT_DIR / "autorun_prompt.md"

    @classmethod
    def _get_preamble(cls) -> str:
        """Read autorun_prompt.md with mtime-based cache."""
        try:
            mt = cls._PROMPT_FILE.stat().st_mtime
            if mt != cls._prompt_mtime or not cls._prompt_cache:
                cls._prompt_cache = cls._PROMPT_FILE.read_text(encoding="utf-8")
                cls._prompt_mtime = mt
        except Exception:
            # Fallback if file missing
            cls._prompt_cache = "你正在无人值守的全自动环境中运行。如果你确定无法完成任务，请输出 TASK_INCOMPLETE 并说明原因。\n\n"
        return cls._prompt_cache

    def _build_prompt(self, pp: "ProjectPaths", task_id: int, description: str) -> str:
        """Build the full prompt for the INITIAL CC launch.

        For full-auto (non-interactive) tasks, the prompt is prefixed with
        "/full-auto " which triggers the full-auto skill. The skill contains
        the Task Reviewer self-review mechanism and all execution rules.
        Historical user messages are included because full-auto runs as a
        single batch — all context must be in the first prompt.

        For interactive tasks, only the current description is sent (no
        history). Past messages were already delivered via stdin on previous
        --resume calls and live in the session JSONL. Re-injecting them
        would cause unbounded prompt growth on long conversations (root
        cause of #54's "Prompt is too long" death spiral).
        """
        desc = description

        # Determine mode
        _is_interactive = False
        try:
            _ic3 = pp.get_db()
            _ir3 = _ic3.execute("SELECT interactive FROM tasks WHERE id=?", (task_id,)).fetchone()
            _ic3.close()
            _is_interactive = bool(_ir3 and _ir3["interactive"])
        except Exception:
            pass

        if not _is_interactive:
            # Full-auto mode: prefix with /full-auto to trigger the skill.
            desc = f"/full-auto {desc}"
        else:
            # Interactive mode: if starts with "/", keep it (user intentionally
            # invoked a skill in interactive mode).
            pass

        parts = [desc]
        try:
            conn = pp.get_db()
            # Include acceptance criteria
            row = conn.execute(
                "SELECT acceptance_criteria FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row and row["acceptance_criteria"]:
                parts.append(f"\n验收标准:\n{row['acceptance_criteria']}")

            if not _is_interactive:
                # Full-auto only: include historical user messages as context.
                # Interactive tasks do NOT include history — messages are
                # delivered one-at-a-time via stdin and persist in session JSONL.
                msgs = conn.execute(
                    "SELECT role, content FROM task_messages WHERE task_id=? AND role='user' ORDER BY id ASC",
                    (task_id,)).fetchall()
                if msgs:
                    parts.append("\n用户补充消息:")
                    for m in msgs:
                        parts.append(f"- {m['content']}")
            conn.close()
        except Exception:
            pass
        return "\n".join(parts)

    def _run_task(self, task_id: int, pp: "ProjectPaths", prompt: str,
                   config_user: str = None, model: str = None, effort: str = None,
                   resume_session_id: str = None):
        """Thread entry point.

        Wraps _run_task_inner in a single top-level catch. ANY unhandled
        exception bubbles to here and is recorded in THREE places:
          1. stderr (print full traceback — visible in orbit.log)
          2. task_messages as 'agent_fail' (visible in Web UI)
          3. DB status=failed + PID file cleanup (so UI no longer shows running)

        The inner function is deliberately written WITHOUT silent catches
        (`except Exception: pass`). Hiding errors there is what caused the
        #27 bug: an ENOTCONN on log_file.close() in a `finally:` swallowed
        the crash and left the task stuck in_progress forever.
        """
        try:
            self._run_task_inner(task_id, pp, prompt, config_user, model,
                                  effort, resume_session_id)
        except BaseException as e:
            tb = traceback.format_exc()
            # 1. stderr — visible in orbit.log so ops can see the crash
            sys.stderr.write(
                f"\n[executor-task-{task_id}] UNHANDLED EXCEPTION:\n{tb}\n")
            sys.stderr.flush()
            # 2+3. Best-effort UI/DB update. If THIS also fails we still
            # want the re-raise to mark the thread as crashed, so each
            # recovery step is wrapped individually and the failure is
            # printed rather than silently swallowed.
            try:
                self._log(pp, task_id, "agent_fail",
                          f"❌ 执行器崩溃: {type(e).__name__}: {e}\n{tb}")
            except Exception as log_err:
                sys.stderr.write(
                    f"[executor-task-{task_id}] also failed to log crash: {log_err}\n")
            try:
                self._update_status(pp, task_id, "failed")
            except Exception as upd_err:
                sys.stderr.write(
                    f"[executor-task-{task_id}] also failed to update status: {upd_err}\n")
            try:
                self._remove_pid(pp, task_id)
            except Exception as rm_err:
                sys.stderr.write(
                    f"[executor-task-{task_id}] also failed to remove pid: {rm_err}\n")
            # Re-raise so the thread exits with error — makes Python log
            # "Exception in thread ..." (fail loud, not silent).
            raise
        finally:
            # Always clean up the thread registry, even on crash
            with self._lock:
                self._threads.pop(task_id, None)

    def _run_task_inner(self, task_id: int, pp: "ProjectPaths", prompt: str,
                   config_user: str = None, model: str = None, effort: str = None,
                   resume_session_id: str = None):
        """Main execution loop — runs in a daemon thread."""
        # Mark as running immediately so UI reflects correct state
        try:
            _sc = pp.get_db()
            _sc.execute("UPDATE tasks SET agent_status='running' WHERE id=?", (task_id,))
            _sc.commit(); _sc.close()
        except Exception:
            pass

        user_label = f" (用户: {config_user})" if config_user else ""
        model_label = f" [模型: {model}]" if model else ""
        effort_label = f" [推理强度: {effort}]" if effort else ""
        is_resume = bool(resume_session_id)
        action_label = "🔄 继续执行（追加预算）" if is_resume else "🚀 全托管执行启动"
        self._log(pp, task_id, "agent_start", f"{action_label}{user_label}{model_label}{effort_label}")

        # On resume, the session JSONL already contains the full conversation
        # history — we only need to send the NEW user message, not re-inject
        # the task description + all historical messages via _build_prompt().
        # _build_prompt() accumulates ALL past user messages which causes
        # context bloat on long-running interactive tasks (root cause of #54's
        # "Prompt is too long" death spiral).
        if resume_session_id:
            full_prompt = prompt  # just the current message, no history
        else:
            full_prompt = self._build_prompt(pp, task_id, prompt)

        # Log the full prompt so users can see what was sent to Claude
        self._log(pp, task_id, "phase", f"📋 执行 Prompt:\n{full_prompt}")

        # Interactive mode: runs like a normal terminal session with full
        # auto-compact support. Cost tracking via session JSONL logs.
        import uuid as _uuid
        if resume_session_id:
            session_id = resume_session_id
        else:
            session_id = str(_uuid.uuid4())

        # Persist session_id to DB for future resume
        try:
            conn = pp.get_db()
            conn.execute("UPDATE tasks SET session_id=? WHERE id=?", (session_id, task_id))
            conn.commit(); conn.close()
        except Exception:
            pass

        cmd = [
            NODE_BIN, CLAUDE_CODE_BIN,
            "--verbose",
            "--allow-dangerously-skip-permissions",
            "--dangerously-skip-permissions",
        ]

        if resume_session_id:
            cmd.extend(["--resume", resume_session_id])
        else:
            cmd.extend(["--session-id", session_id])

        # System prompt injection based on mode
        _is_interactive = False
        try:
            _ic2 = pp.get_db()
            _ir2 = _ic2.execute("SELECT interactive FROM tasks WHERE id=?", (task_id,)).fetchone()
            _ic2.close()
            _is_interactive = bool(_ir2 and _ir2["interactive"])
        except Exception:
            pass

        if _is_interactive:
            # Interactive mode: minimal system prompt, allow natural conversation
            cmd.extend(["--append-system-prompt",
                        "你正在与用户进行交互式对话。每次回复后等待用户的下一条消息。"
                        "像在终端中一样自然对话——可以提问、请求确认、分步执行。"
                        "用户的消息会通过 stdin 传入。"])
        # Full-auto mode: no system prompt injection here.
        # Instead, the prompt is prefixed with "/full-auto" in _build_prompt,
        # which triggers the full-auto skill (with Task Reviewer) via CC's
        # native skill loading mechanism.

        # Effort / reasoning intensity (claude-code CLI enum: low, medium, high, xhigh, max)
        # xhigh / max 仅 Opus 4.7 生效，其他模型 CLI 会静默降级到 high
        if effort and effort in ("low", "medium", "high", "xhigh", "max"):
            cmd.extend(["--effort", effort])

        project_path = str(pp.root)
        env = os.environ.copy()

        # Allow bypassPermissions under root: CC blocks --dangerously-skip-permissions
        # when getuid()==0 unless IS_SANDBOX=1. We're running in a controlled
        # environment where full permissions are required for task automation.
        env["IS_SANDBOX"] = "1"

        # Disable CC's built-in auto-update / telemetry probes. The internal
        # updater hits https://mirrors.tencent.com/npm/... on every launch;
        # when that mirror times out, the subprocess dies silently before
        # writing the session JSONL, and _tail_log's 30s wait gives up.
        # (This is the root cause of task #33's "重启直接失败" — stderr:
        #  "自动检查更新失败：Request timed out: GET https://mirrors.tencent.com/...".)
        # CC itself supports these exact flags (see its disableTelemetry()).
        env["DISABLE_AUTOUPDATER"] = "1"
        env["DISABLE_TELEMETRY"] = "1"
        env["DISABLE_ERROR_REPORTING"] = "1"
        env["DISABLE_INSTALLATION_CHECKS"] = "1"
        env["DISABLE_COST_WARNINGS"] = "1"
        env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"

        # Inject Taiji token so /taiji skill can use it
        taiji_token = get_taiji_token()
        if taiji_token:
            env["TOKEN"] = taiji_token

        # Model selection: claude-code-internal reads model from the global
        # settings.json "model" field. We write the task-level model AFTER
        # the user-level default so it takes priority.
        # (The web UI writes user-level model on page load; we overwrite here
        # right before spawning the process so the task model wins.)
        # Fix: if model/effort params are None (e.g. resume endpoint), read from DB
        # rather than blindly defaulting to "sonnet"/"medium".
        if not model or not effort:
            try:
                _mc = pp.get_db()
                _mr = _mc.execute("SELECT model, effort FROM tasks WHERE id=?", (task_id,)).fetchone()
                _mc.close()
                if not model:
                    model = _mr["model"] if (_mr and _mr["model"]) else "sonnet"
                if not effort:
                    effort = _mr["effort"] if (_mr and _mr["effort"]) else "medium"
            except Exception:
                model = model or "sonnet"
                effort = effort or "medium"
        effective_model = model
        if effective_model != "auto":
            model_map = {
                "sonnet": _strip_ansi(env.get("ANTHROPIC_DEFAULT_SONNET_MODEL", "claude-sonnet-4-6")),
                "opus": _strip_ansi(env.get("ANTHROPIC_DEFAULT_OPUS_MODEL", "claude-opus-4-6")),
                "haiku": _strip_ansi(env.get("ANTHROPIC_DEFAULT_HAIKU_MODEL", "claude-haiku-4-5")),
            }
            model_id = model_map.get(effective_model, effective_model)
            # NOTE: The Tencent claude-code-internal wrapper ALWAYS hard-codes
            # CLAUDE_CONFIG_DIR=~/.claude-internal and strips any env overrides
            # we pass. So per-task CLAUDE_CONFIG_DIR isolation is impossible.
            # Instead, we write to the global ~/.claude-internal/settings.json
            # and hold the lock through subprocess creation to prevent races.
            # The lock is released after Popen returns (CC reads settings.json
            # at startup before its first API call).
            _model_settings = {"model": model_id}
            if effort and effort in ("low", "medium", "high", "xhigh", "max"):
                _model_settings["effortLevel"] = effort
            # _set_global_model_and_effort writes atomically to the canonical path
            _set_global_model_settings(_model_settings)

        # Log the actual CLI parameters being used
        cli_params = []
        cli_params.append(f"模型: {effective_model}" + (f" (settings.json → {model_id})" if effective_model != "auto" else ""))
        if effort and effort in ("low", "medium", "high", "xhigh", "max"):
            cli_params.append(f"推理强度: {effort} (--effort {effort})")
        else:
            cli_params.append("推理强度: medium (默认)")
        self._log(pp, task_id, "info",
                  f"⚙️ 启动参数: {' | '.join(cli_params)}\n💡 模型将在收到首条 API 响应后验证")

        # If a user config is specified, override the auth token
        if config_user:
            user_cfg = load_user_config(config_user)
            if user_cfg.get("accessToken"):
                _launch_token = user_cfg["accessToken"]
                env["ANTHROPIC_AUTH_TOKEN"] = _launch_token
                env["ANTHROPIC_CUSTOM_HEADERS"] = f"x-api-key: {_launch_token}"
                # Pass --token to override wrapper's OAuth (config.json) auth flow
                # Without this, claude-code-internal ignores env vars and uses config.json
                cmd.extend(["--token", _launch_token])
                # Log token fingerprint for billing verification
                _tk = _launch_token
                self._log(pp, task_id, "info",
                          f"🔑 计费账号: {config_user} (token: {_tk[:4]}...{_tk[-4:]})")
            else:
                self._log(pp, task_id, "warning",
                          f"⚠️ 用户 {config_user} 配置中无 accessToken，将使用默认账号")
        else:
            self._log(pp, task_id, "info", "🔑 计费账号: 默认 (未指定 config_user)")

        # Run as current user (not sudo — bypassPermissions is blocked under root)
        # env is already a copy of os.environ with config overrides applied

        # stdout → file (captures text output from interactive mode)
        log_path = self._log_path(pp, task_id)
        log_file = open(str(log_path), "w")

        # Session JSONL path: ~/.claude-internal/projects/<slug>/<session_id>.jsonl
        # claude-code converts project path to slug by replacing ALL
        # non-alphanumeric chars with dashes (not just '/').
        import re as _re
        proj_slug = _re.sub(r'[^a-zA-Z0-9]', '-', project_path)
        session_jsonl = Path.home() / ".claude-internal" / "projects" / proj_slug / f"{session_id}.jsonl"

        # ── Skip initial CC launch for interactive resume with no prompt ──
        # When auto-resume triggers (e.g. server restart + user sends message),
        # the message is stored as pending_send and prompt is empty.
        # Don't launch CC with an empty prompt — go straight to the message
        # loop, which will pick up the pending_send message and deliver it
        # via --resume properly.
        _skip_initial_launch = (is_resume and _is_interactive
                                and not full_prompt.strip())

        # Read persisted JSONL offset for resume — needed by both paths
        _initial_offset = 0
        _initial_tokens = None
        if is_resume:
            try:
                _ofc = pp.get_db()
                _ofr = _ofc.execute(
                    "SELECT jsonl_offset, total_input_tokens, total_output_tokens, "
                    "estimated_cost_usd, cache_create_tokens, cache_read_tokens "
                    "FROM tasks WHERE id=?", (task_id,)
                ).fetchone()
                _ofc.close()
                if _ofr and _ofr["jsonl_offset"]:
                    _initial_offset = int(_ofr["jsonl_offset"])
                    _db_cache_create = _ofr["cache_create_tokens"] or 0
                    _db_cache_read = _ofr["cache_read_tokens"] or 0
                    _db_logical_in = _ofr["total_input_tokens"] or 0
                    _db_uncached_in = max(0, _db_logical_in - _db_cache_create - _db_cache_read)
                    _initial_tokens = {
                        "input": _db_uncached_in,
                        "output": _ofr["total_output_tokens"] or 0,
                        "cache_create": _db_cache_create,
                        "cache_read": _db_cache_read,
                        "turn_count": 0,
                        "seen_ids": [],
                        "last_text": "",
                        "model_validated": True,
                    }
                    self._log(pp, task_id, "info",
                              f"📄 从 JSONL 偏移 {_initial_offset} 继续读取（跳过已处理事件）")
            except Exception:
                pass

        if _skip_initial_launch:
            self._log(pp, task_id, "info",
                      "💬 交互模式恢复：等待消息投递…")
            proc = None
            tail_result = {
                "turn_count": 1,  # Fake: prevent _skip_msg_loop from skipping
                "jsonl_offset": _initial_offset,
                "status_finalized": False,
            }
            log_file.close()
        else:
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=log_file,
                    stderr=subprocess.PIPE,
                    cwd=project_path,
                    env=env,
                    bufsize=0,
                    start_new_session=True,
                )
                # Send prompt via stdin and close — claude starts processing after EOF
                proc.stdin.write(full_prompt.encode("utf-8"))
                proc.stdin.write(b"\n")
                proc.stdin.flush()
                proc.stdin.close()
            except Exception as e:
                log_file.close()
                self._log(pp, task_id, "agent_fail", f"启动失败: {e}")
                self._update_status(pp, task_id, "failed")
                with self._lock:
                    self._threads.pop(task_id, None)
                return

            # Quick check: if process dies immediately, capture stderr
            import time
            time.sleep(2)
            if proc.poll() is not None:
                stderr_out = ""
                try:
                    stderr_out = proc.stderr.read().decode("utf-8", errors="replace")[:2000]
                except Exception:
                    pass
                self._log(pp, task_id, "agent_fail",
                          f"进程立即退出 (code={proc.returncode}): {stderr_out}")
                self._update_status(pp, task_id, "failed")
                log_file.close()
                with self._lock:
                    self._threads.pop(task_id, None)
                return

            # Persist PID so we can recover after server restart
            try:
                pgid = os.getpgid(proc.pid)
            except OSError:
                pgid = proc.pid
            self._write_pid(pp, task_id, proc.pid, pgid)

            tail_result = None
            # IMPORTANT: do NOT wrap this in try/except to "safely" close the log
            # file. The ENOTCONN bug (#27) was caused by log_file.close() raising
            # from within `finally:` and silently killing the thread. Let any
            # IO/RPC exception bubble to _run_task's top-level catch, which
            # records it everywhere (stderr + UI + DB) before re-raising.
            try:
                tail_result = self._tail_log(proc, log_file, pp, task_id, session_jsonl,
                                              defer_status=True,
                                              jsonl_offset=_initial_offset,
                                              prior_tokens=_initial_tokens)
            finally:
                # Close quietly: if this raises (e.g. broken mount), the exception
                # will replace any in-flight tail_log exception and still reach
                # _run_task's top catch — fail loud, not silent.
                log_file.close()
                self._remove_pid(pp, task_id)

        # ── Message loop: wait for follow-up messages, resume session ──
        # After the main execution ends, poll for pending_send user messages.
        # If any arrive within the wait window, use --resume to inject them.
        # Task is still in_progress at this point — status update is deferred.
        #
        # Skip the message loop if execution failed at startup (no turns) —
        # no point waiting for follow-up messages on a broken task.
        # Also skip if _tail_log already finalized status (e.g. cost limit hit).
        import time as _time
        _skip_msg_loop = tail_result and tail_result.get("turn_count", 0) == 0
        _status_already_finalized = tail_result and tail_result.get("status_finalized", False)
        if _skip_msg_loop:
            self._log(pp, task_id, "info", "⏩ 无有效执行轮次，跳过消息等待")
        if _status_already_finalized:
            _skip_msg_loop = True

        # Determine mode: interactive vs full-auto
        _is_interactive = False
        try:
            _ic = pp.get_db()
            _ir = _ic.execute("SELECT interactive FROM tasks WHERE id=?", (task_id,)).fetchone()
            _ic.close()
            _is_interactive = bool(_ir and _ir["interactive"])
        except Exception:
            pass

        if _is_interactive:
            # Interactive mode: CC ran one turn, now wait for user input indefinitely.
            # Only exit when user explicitly ends the session (stop button → status='failed')
            # or cost limit is hit.
            _MAX_IDLE_WAIT = 86400  # 24h
            if not _skip_msg_loop:
                self._log(pp, task_id, "info",
                          "💬 交互模式：等待你的消息…")
                # Mark agent as idle so the UI shows "waiting for input"
                try:
                    _ac = pp.get_db()
                    _ac.execute("UPDATE tasks SET agent_status='idle' WHERE id=?", (task_id,))
                    _ac.commit(); _ac.close()
                except Exception:
                    pass
        else:
            # Full-auto mode: CC completed its task. Give a short window (60s)
            # for the user to send a quick follow-up, then finalize as completed.
            _MAX_IDLE_WAIT = 60
            if not _skip_msg_loop:
                self._log(pp, task_id, "info",
                          "✅ 全托管执行完成。60 秒内可追加消息，否则自动结束。")

        # ── Plan mode auto-approval ──
        # If ExitPlanMode was the last tool call before CC exited, the plan
        # was written but not yet approved. Auto-inject an approval message
        # so the plan gets executed without manual intervention.
        # This happens because CC closes after ExitPlanMode when stdin is EOF.
        _plan_pending = tail_result and tail_result.get("plan_exit_pending", False)
        if _plan_pending and not _skip_msg_loop:
            self._log(pp, task_id, "info", "📋 检测到 Plan 待批准，自动注入执行指令")
            try:
                _plan_db = pp.get_db()
                _plan_db.execute(
                    "INSERT INTO task_messages (task_id, role, content, status) VALUES (?, 'user', ?, 'pending_send')",
                    (task_id, "approved, please execute the plan now"))
                _plan_db.commit(); _plan_db.close()
            except Exception as e:
                self._log(pp, task_id, "warning", f"⚠️ 自动注入 plan 批准消息失败: {e}")

        _POLL_INTERVAL = 2
        idle_start = _time.time()
        while not _skip_msg_loop and _time.time() - idle_start < _MAX_IDLE_WAIT:
            _time.sleep(_POLL_INTERVAL)
            # Check if task was externally stopped (e.g. user clicked stop button).
            # We ONLY catch sqlite3.OperationalError here because it is expected
            # (brief lock contention on concurrent writes). Any other exception
            # should bubble to _run_task's top catch so it's visible.
            try:
                conn_chk = pp.get_db()
                st_row = conn_chk.execute("SELECT status FROM tasks WHERE id=?", (task_id,)).fetchone()
                conn_chk.close()
                if st_row and st_row["status"] in ("failed",):
                    # Only break on externally-set failure (e.g. manual stop)
                    break
            except sqlite3.OperationalError as e:
                sys.stderr.write(f"[executor-task-{task_id}] transient DB read error: {e}\n")
            # Check for pending messages — same policy: only swallow DB locks
            try:
                conn_msg = pp.get_db()
                pending = conn_msg.execute(
                    "SELECT id, content FROM task_messages "
                    "WHERE task_id=? AND role='user' AND status IN ('pending_send','sending') "
                    "ORDER BY id", (task_id,)
                ).fetchall()
                conn_msg.close()
            except sqlite3.OperationalError as e:
                sys.stderr.write(f"[executor-task-{task_id}] transient DB read error: {e}\n")
                pending = []
            if not pending:
                continue

            # Found pending messages — resume session
            combined = "\n".join(pm["content"] for pm in pending)
            self._log(pp, task_id, "info", f"📨 收到用户消息，恢复会话")
            # Mark agent as running again
            try:
                _ac2 = pp.get_db()
                _ac2.execute("UPDATE tasks SET agent_status='running' WHERE id=?", (task_id,))
                _ac2.commit(); _ac2.close()
            except Exception:
                pass

            # Mark messages as 'sending' (not 'done' yet!) — we only
            # promote to 'done' after CC actually processes them.  If CC
            # crashes before responding, we revert to 'pending_send' so
            # the message loop can re-deliver.
            try:
                conn_msg = pp.get_db()
                for pm in pending:
                    conn_msg.execute("UPDATE task_messages SET status='sending' WHERE id=?", (pm["id"],))
                conn_msg.commit(); conn_msg.close()
            except sqlite3.OperationalError as e:
                sys.stderr.write(f"[executor-task-{task_id}] transient DB write error: {e}\n")

            # Launch resume process — re-set model in settings.json first
            # to prevent another task's model from being used.
            try:
                _resume_settings = {"model": model_id}
                if effort and effort in ("low", "medium", "high", "xhigh", "max"):
                    _resume_settings["effortLevel"] = effort
                _set_global_model_settings(_resume_settings)
            except NameError:
                pass  # model_id not defined (auto mode)

            # Re-read config_user from DB — user may have changed the billing
            # account on the detail page since the task was first launched.
            try:
                _cu_conn = pp.get_db()
                _cu_row = _cu_conn.execute(
                    "SELECT config_user FROM tasks WHERE id=?", (task_id,)
                ).fetchone()
                _cu_conn.close()
                _current_config_user = _cu_row["config_user"] if _cu_row else config_user
            except Exception:
                _current_config_user = config_user
            if _current_config_user:
                _cu_cfg = load_user_config(_current_config_user)
                if _cu_cfg.get("accessToken"):
                    _resume_token = _cu_cfg["accessToken"]
                    env["ANTHROPIC_AUTH_TOKEN"] = _resume_token
                    env["ANTHROPIC_CUSTOM_HEADERS"] = f"x-api-key: {_resume_token}"
                    _tk = _resume_token
                    self._log(pp, task_id, "info",
                              f"🔑 恢复计费账号: {_current_config_user} (token: {_tk[:4]}...{_tk[-4:]})")
                else:
                    _resume_token = None
            elif "ANTHROPIC_AUTH_TOKEN" in env:
                # config_user was cleared — revert to default token
                env.pop("ANTHROPIC_AUTH_TOKEN", None)
                env.pop("ANTHROPIC_CUSTOM_HEADERS", None)
                _resume_token = None
            else:
                _resume_token = None

            resume_cmd = [
                NODE_BIN, CLAUDE_CODE_BIN,
                "--verbose",
                "--allow-dangerously-skip-permissions",
                "--dangerously-skip-permissions",
                "--resume", session_id,
            ]
            # Pass --token to override the wrapper's OAuth flow (config.json)
            # Without this, claude-code-internal ignores ANTHROPIC_AUTH_TOKEN env var
            # and always uses the token from ~/.claude-internal/config.json
            if _resume_token:
                resume_cmd.extend(["--token", _resume_token])
            if effort and effort in ("low", "medium", "high", "xhigh", "max"):
                resume_cmd.extend(["--effort", effort])

            resume_log = open(str(self._log_path(pp, task_id)), "a")
            try:
                resume_proc = subprocess.Popen(
                    resume_cmd,
                    stdin=subprocess.PIPE,
                    stdout=resume_log,
                    stderr=subprocess.PIPE,
                    cwd=project_path,
                    env=env,
                    bufsize=0,
                    start_new_session=True,
                )
                resume_proc.stdin.write(combined.encode("utf-8"))
                resume_proc.stdin.write(b"\n")
                resume_proc.stdin.flush()
                resume_proc.stdin.close()
            except Exception as e:
                self._log(pp, task_id, "error", f"恢复会话失败: {e}")
                resume_log.close()
                # Revert sending → pending_send so message can be retried
                try:
                    _rv = pp.get_db()
                    _rv.execute(
                        "UPDATE task_messages SET status='pending_send' "
                        "WHERE task_id=? AND role='user' AND status='sending'",
                        (task_id,))
                    _rv.commit(); _rv.close()
                except Exception:
                    pass
                break

            # Quick check
            _time.sleep(2)
            if resume_proc.poll() is not None:
                stderr_out = ""
                try:
                    stderr_out = resume_proc.stderr.read().decode("utf-8", errors="replace")[:500]
                except Exception:
                    pass
                self._log(pp, task_id, "error", f"恢复进程立即退出 (code={resume_proc.returncode}): {stderr_out}")
                resume_log.close()
                # Revert sending → pending_send so message loop can retry
                try:
                    _rv = pp.get_db()
                    _rv.execute(
                        "UPDATE task_messages SET status='pending_send' "
                        "WHERE task_id=? AND role='user' AND status='sending'",
                        (task_id,))
                    _rv.commit(); _rv.close()
                except Exception:
                    pass
                # Track consecutive failures to avoid infinite retry
                _resume_failures = getattr(self, f'_resume_fail_{task_id}', 0) + 1
                setattr(self, f'_resume_fail_{task_id}', _resume_failures)
                if _resume_failures >= 3:
                    self._log(pp, task_id, "error", "❌ 恢复连续失败3次，放弃重试")
                    # Mark messages as done to avoid infinite loop
                    try:
                        _fc = pp.get_db()
                        _fc.execute(
                            "UPDATE task_messages SET status='done' "
                            "WHERE task_id=? AND role='user' AND status='pending_send'",
                            (task_id,))
                        _fc.commit(); _fc.close()
                    except Exception:
                        pass
                    break
                self._log(pp, task_id, "info", "🔄 消息已回退，将重新投递")
                idle_start = _time.time()  # reset idle timer for retry
                continue

            # Update PID file for crash recovery
            try:
                pgid = os.getpgid(resume_proc.pid)
            except OSError:
                pgid = resume_proc.pid
            self._write_pid(pp, task_id, resume_proc.pid, pgid)

            # Tail the resumed session (same JSONL file).
            # Same rationale as above: NO silent catch — let any broken-mount
            # or parse error reach _run_task's top-level handler.
            try:
                _prev_offset = tail_result.get("jsonl_offset", 0) if tail_result else 0
                _prev_tokens = tail_result.get("prior_tokens") if tail_result else None
                resume_result = self._tail_log(resume_proc, resume_log, pp, task_id,
                                                session_jsonl, defer_status=True,
                                                jsonl_offset=_prev_offset,
                                                prior_tokens=_prev_tokens)
                if resume_result:
                    tail_result = resume_result  # update with latest result
                    # If cost limit was hit inside _tail_log, it already set
                    # status=failed — break out of message loop immediately.
                    if resume_result.get("status_finalized"):
                        # Cost limit: mark sending messages as done (they were
                        # delivered even though CC may not have finished).
                        try:
                            _dc = pp.get_db()
                            _dc.execute(
                                "UPDATE task_messages SET status='done' "
                                "WHERE task_id=? AND role='user' AND status='sending'",
                                (task_id,))
                            _dc.commit(); _dc.close()
                        except Exception:
                            pass
                        break
                # Promote or revert 'sending' messages based on whether CC
                # actually processed them (turn_count > 0).
                _resume_had_turns = resume_result and resume_result.get("turn_count", 0) > 0
                if _resume_had_turns:
                    # CC responded — promote sending → done
                    try:
                        _dc = pp.get_db()
                        _dc.execute(
                            "UPDATE task_messages SET status='done' "
                            "WHERE task_id=? AND role='user' AND status='sending'",
                            (task_id,))
                        _dc.commit(); _dc.close()
                    except Exception:
                        pass
                    # Reset consecutive-failure counter on success
                    if hasattr(self, f'_resume_fail_{task_id}'):
                        delattr(self, f'_resume_fail_{task_id}')
                else:
                    # CC didn't produce any turns — revert sending → pending_send
                    try:
                        _rv = pp.get_db()
                        _sending_count = _rv.execute(
                            "SELECT COUNT(*) as c FROM task_messages "
                            "WHERE task_id=? AND role='user' AND status='sending'",
                            (task_id,)).fetchone()["c"]
                        if _sending_count > 0:
                            _rv.execute(
                                "UPDATE task_messages SET status='pending_send' "
                                "WHERE task_id=? AND role='user' AND status='sending'",
                                (task_id,))
                            _rv.commit()
                            self._log(pp, task_id, "info",
                                      "🔄 消息未被处理，已回退为待发送")
                        _rv.close()
                    except Exception:
                        pass
            finally:
                resume_log.close()
                self._remove_pid(pp, task_id)

            # Reset idle timer after each resume completes
            idle_start = _time.time()
            # If interactive, set back to idle (waiting for next message)
            if _is_interactive:
                self._log(pp, task_id, "info", "💬 交互模式：等待你的消息…")
                try:
                    _ac3 = pp.get_db()
                    _ac3.execute("UPDATE tasks SET agent_status='idle' WHERE id=?", (task_id,))
                    _ac3.commit(); _ac3.close()
                except Exception:
                    pass

            # ── Plan mode auto-approval (resume path) ──
            # Same logic as initial launch: if CC exited right after ExitPlanMode,
            # auto-inject an approval message so the plan gets executed.
            if resume_result and resume_result.get("plan_exit_pending", False):
                self._log(pp, task_id, "info", "📋 检测到 Plan 待批准，自动注入执行指令")
                try:
                    _plan_db = pp.get_db()
                    _plan_db.execute(
                        "INSERT INTO task_messages (task_id, role, content, status) VALUES (?, 'user', ?, 'pending_send')",
                        (task_id, "approved, please execute the plan now"))
                    _plan_db.commit(); _plan_db.close()
                except Exception as e:
                    self._log(pp, task_id, "warning", f"⚠️ 自动注入 plan 批准消息失败: {e}")

        # ── Finalize task status after message loop ends ──
        # Kill any lingering claude-code process before finalizing.
        # We explicitly re-raise if kill fails because a stuck claude process
        # is a real problem worth surfacing, not something to paper over.
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                sys.stderr.write(
                    f"[executor-task-{task_id}] terminate timed out, sending SIGKILL\n")
                proc.kill()
                proc.wait(timeout=5)

        # Finalize status. NO outer try/except here — if _finalize_task_status
        # or _update_status fails, _run_task's top catch records the crash
        # with a full traceback. Previously this block had nested
        # `try/except Exception: pass` that masked real failures.
        if tail_result:
            # Skip re-finalization if _tail_log already set status (e.g. cost limit).
            # Without this guard, _finalize_task_status would overwrite the correct
            # cost_usd with a stale value from a previous run's tail_result.
            if tail_result.get("status_finalized"):
                pass  # Status already set by _tail_log — nothing to do
            else:
                # Interactive mode: if we had successful turns, treat as completed
                # regardless of the process exit code. The message loop exiting
                # (idle timeout or user stop) is a normal end for interactive tasks,
                # not an error. The rc=-1 from _tail_log only means "process was
                # not a direct child" or "process already exited", not a real failure.
                if _is_interactive and tail_result.get("turn_count", 0) > 0:
                    tail_result["rc"] = 0
                self._finalize_task_status(pp, task_id, tail_result)
        else:
            # tail_result is None — _tail_log exited without producing a result
            # dict. Could be broken mount, early abort, etc.
            self._log(pp, task_id, "agent_fail",
                      "❌ 执行异常，无法确定结果 (tail_log 未返回 result)")
            self._update_status(pp, task_id, "failed")

        # ── Final cleanup ──
        # Thread registry cleanup is handled in _run_task's finally block
        # to ensure it runs even on crash.

    def _tail_log(self, proc, log_file, pp: "ProjectPaths", task_id: int,
                  session_jsonl=None, defer_status=False, jsonl_offset=0,
                  prior_tokens=None):
        """Monitor session JSONL for cost/progress; wait for process exit.

        In interactive mode, claude-code writes structured events to the
        session JSONL file at ~/.claude-internal/projects/<slug>/<session>.jsonl.
        We tail that file for cost tracking and progress updates.
        If session_jsonl is None, fall back to tailing stdout (legacy --print mode).

        jsonl_offset: byte offset to seek to before reading (skip already-processed lines).
        prior_tokens: dict with prior token counts to continue accumulating from.
        """
        import time

        # Read max_cost_usd from DB
        max_cost_usd = 5.0
        try:
            conn = pp.get_db()
            row = conn.execute("SELECT max_cost_usd FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row and row["max_cost_usd"] is not None:
                max_cost_usd = float(row["max_cost_usd"])
            conn.close()
        except Exception:
            pass
        # NOTE: token counts are NOT read from DB as prior values.
        # _tail_log reads the session JSONL from the beginning, which already
        # contains the full history for this session. Adding DB-stored prior
        # counts would double-count tokens.

        self._log(pp, task_id, "info", f"💰 成本上限: ${max_cost_usd:.1f}")

        # ── Wait for session JSONL to appear (may take a few seconds) ──
        jsonl_path = str(session_jsonl) if session_jsonl else None
        is_recovery = proc is None
        if is_recovery:
            print(f"[recover-tail] task#{task_id} jsonl_path={jsonl_path} exists={os.path.exists(jsonl_path) if jsonl_path else 'N/A'}")
        if jsonl_path:
            # Extended wait (120s): CC cold-start on slow filesystems / after
            # the Tencent npm mirror fix can take 30–60s before writing the
            # first JSONL event. The previous 30s cutoff caused task #33 to
            # mislog a "never appeared" warning 3s before the file actually
            # showed up.
            _JSONL_WAIT_SECS = 120
            for _ in range(_JSONL_WAIT_SECS):
                if os.path.exists(jsonl_path):
                    break
                if proc is not None and proc.poll() is not None:
                    break
                time.sleep(1)
            if not os.path.exists(jsonl_path):
                # JSONL still missing — log diagnostic BUT keep going.
                # Use non-blocking stderr drain: a plain proc.stderr.read()
                # on a live subprocess blocks until stderr EOF (= proc exit),
                # which froze task #33 silently for ~35 minutes.
                stderr_out = self._drain_stderr_nonblocking(proc, max_bytes=2000, timeout=0.5)
                rc = proc.returncode if (proc and proc.poll() is not None) else "running"
                self._log(pp, task_id, "error",
                          f"⚠️ 等待{_JSONL_WAIT_SECS}秒后仍未生成 session JSONL (进程状态: {rc})"
                          + (f"\nstderr: {stderr_out}" if stderr_out else ""))

        # ── Tail session JSONL ──
        # When resuming, start from prior token counts to avoid double-counting.
        _pt = prior_tokens or {}
        _running_input_tokens = _pt.get("input", 0)
        _running_output_tokens = _pt.get("output", 0)
        _running_cache_create = _pt.get("cache_create", 0)
        _running_cache_read = _pt.get("cache_read", 0)
        _turn_count = _pt.get("turn_count", 0)
        _price_in, _price_cache_create, _price_cache_read, _price_out = self._model_pricing("sonnet")
        _seen_msg_ids = set(_pt.get("seen_ids", []))
        last_assistant_text = _pt.get("last_text", "")
        _model_validated = bool(_pt.get("model_validated", False))
        _plan_exit_pending = False  # True if ExitPlanMode was the last tool call
        _in_plan_mode = False  # True if currently in plan mode
        _idle_break = False  # True if we broke out due to idle detection
        _last_stop_reason = ""  # Track last assistant stop_reason for idle detection

        _jsonl_offset = jsonl_offset  # track how far we've read
        if jsonl_path and os.path.exists(jsonl_path):
            if is_recovery:
                print(f"[recover-tail] task#{task_id} entering JSONL read loop")
            with open(jsonl_path, "r") as f:
                # Skip already-processed portion of JSONL
                if jsonl_offset > 0:
                    f.seek(jsonl_offset)
                while True:
                    line = f.readline()
                    if line:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            event = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        # Reset drain retry counter — we got a valid line,
                        # so there may be more coming even after proc exit
                        if hasattr(self, f'_drain_retries_{task_id}'):
                            setattr(self, f'_drain_retries_{task_id}', 0)
                        # Reset idle silence timer — we got output
                        if hasattr(self, f'_no_output_since_{task_id}'):
                            delattr(self, f'_no_output_since_{task_id}')

                        etype = event.get("type", "")

                        if etype == "assistant":
                            msg_obj = event.get("message", {})
                            # Track stop_reason for idle detection:
                            # end_turn = CC done, waiting for user
                            # tool_use = CC waiting for tool result (NOT idle!)
                            _sr = msg_obj.get("stop_reason", "")
                            if _sr:
                                _last_stop_reason = _sr
                            # Detect model for pricing (skip synthetic/injected messages)
                            model_name = msg_obj.get("model", "")
                            if model_name and model_name != "<synthetic>":
                                _price_in, _price_cache_create, _price_cache_read, _price_out = (
                                    self._model_pricing(model_name))

                            # Model validation: log actual model on first REAL assistant message
                            # Skip synthetic messages (rate-limit errors, compaction, etc.)
                            if model_name and not _model_validated and model_name != "<synthetic>":
                                _model_validated = True
                                try:
                                    _vconn = pp.get_db()
                                    _vrow = _vconn.execute(
                                        "SELECT model, effort FROM tasks WHERE id=?", (task_id,)
                                    ).fetchone()
                                    _vconn.close()
                                    expected_model = _vrow["model"] if _vrow else None
                                    expected_effort = _vrow["effort"] if _vrow else None
                                    # Model validation
                                    if expected_model and expected_model != "auto":
                                        # Map short names to check against actual model
                                        _model_keywords = {
                                            "sonnet": "sonnet", "opus": "opus", "haiku": "haiku"
                                        }
                                        expected_kw = _model_keywords.get(expected_model, expected_model)
                                        if expected_kw.lower() not in model_name.lower():
                                            self._log(pp, task_id, "warning",
                                                      f"⚠️ 模型不一致！期望 {expected_model}，实际使用 {model_name}")
                                        else:
                                            self._log(pp, task_id, "info",
                                                      f"✅ 模型验证通过: {model_name}")
                                    else:
                                        self._log(pp, task_id, "info",
                                                  f"ℹ️ 实际使用模型: {model_name}")
                                    # Effort validation: can only confirm CLI param was passed,
                                    # API response doesn't include effort info
                                    if expected_effort and expected_effort in ("low", "high", "xhigh", "max"):
                                        self._log(pp, task_id, "info",
                                                  f"✅ 推理强度已设置: --effort {expected_effort} (CLI参数已传入，API无法二次验证)")
                                    elif expected_effort == "medium" or not expected_effort:
                                        self._log(pp, task_id, "info",
                                                  f"ℹ️ 推理强度: medium (默认)")
                                except Exception:
                                    pass

                            usage = msg_obj.get("usage", {})
                            # Only count "final" events (output_tokens > 0).
                            # JSONL emits multiple assistant events per turn:
                            # stream-start events duplicate input_tokens with output=0,
                            # only the final event has the real token counts.
                            # Also: a single turn may emit one assistant line per
                            # content block (text + tool_use + tool_use + …), all
                            # sharing the same message.id and usage — dedupe by id
                            # so tokens aren't counted N× for an N-block reply.
                            if usage and usage.get("output_tokens", 0) > 0:
                                _mid = msg_obj.get("id")
                                _is_dup = bool(_mid and _mid in _seen_msg_ids)
                                if _mid and not _is_dup:
                                    _seen_msg_ids.add(_mid)
                                if not _is_dup:
                                    _running_input_tokens += usage.get("input_tokens", 0)
                                    _running_output_tokens += usage.get("output_tokens", 0)
                                    _running_cache_create += usage.get("cache_creation_input_tokens", 0)
                                    _running_cache_read += usage.get("cache_read_input_tokens", 0)
                                    _turn_count += 1

                                    # input_tokens is already UNCACHED; cache tokens are additive
                                    est_cost = (
                                        _running_input_tokens * _price_in
                                        + _running_cache_create * _price_cache_create
                                        + _running_cache_read * _price_cache_read
                                        + _running_output_tokens * _price_out
                                    ) / 1_000_000
                                    # Logical billed input = uncached + cache_create + cache_read
                                    _logical_in = (
                                        _running_input_tokens
                                        + _running_cache_create
                                        + _running_cache_read
                                    )
                                    self._update_cost(pp, task_id, est_cost,
                                                      _logical_in, _running_output_tokens,
                                                      _running_cache_create, _running_cache_read)
                                    # Also persist jsonl_offset for crash safety
                                    try:
                                        _oc2 = pp.get_db()
                                        _oc2.execute("UPDATE tasks SET jsonl_offset=? WHERE id=?",
                                                     (f.tell(), task_id))
                                        _oc2.commit(); _oc2.close()
                                    except Exception:
                                        pass

                                    # Re-read max_cost_usd from DB each check (user may have increased it)
                                    try:
                                        _conn = pp.get_db()
                                        _row = _conn.execute("SELECT max_cost_usd FROM tasks WHERE id=?", (task_id,)).fetchone()
                                        if _row and _row["max_cost_usd"] is not None:
                                            max_cost_usd = float(_row["max_cost_usd"])
                                        _conn.close()
                                    except Exception:
                                        pass

                                    # Check cost limit (using estimated cost)
                                    if est_cost > max_cost_usd:
                                        self._log(pp, task_id, "agent_fail",
                                                  f"💰 成本超限！估算 ${est_cost:.2f}，上限 ${max_cost_usd:.2f}，强制终止")
                                        self.stop_task(task_id, pp)
                                        self._update_status(pp, task_id, "failed", cost_usd=est_cost)
                                        # Return a proper result dict instead of None so
                                        # the caller's tail_result gets updated and
                                        # _finalize_task_status doesn't overwrite with stale data.
                                        # status_finalized=True tells caller to skip re-finalization.
                                        return {
                                            "rc": -1,
                                            "est_cost": est_cost,
                                            "turn_count": _turn_count,
                                            "last_assistant_text": last_assistant_text,
                                            "result_text": "",
                                            "proc": proc,
                                            "status_finalized": True,
                                            "jsonl_offset": _jsonl_offset,
                                            "prior_tokens": {
                                                "input": _running_input_tokens,
                                                "output": _running_output_tokens,
                                                "cache_create": _running_cache_create,
                                                "cache_read": _running_cache_read,
                                                "turn_count": _turn_count,
                                                "seen_ids": list(_seen_msg_ids),
                                                "last_text": last_assistant_text,
                                                "model_validated": _model_validated,
                                            },
                                        }



                            # Extract text and tool use for progress / streaming
                            content_blocks = msg_obj.get("content", [])
                            texts = []
                            for block in content_blocks:
                                if isinstance(block, dict):
                                    if block.get("type") == "text":
                                        texts.append(block.get("text", ""))
                                    elif block.get("type") == "thinking":
                                        thinking_text = block.get("thinking", "")
                                        if thinking_text:
                                            self._log(pp, task_id, "thinking", thinking_text)
                                    elif block.get("type") == "tool_use":
                                        tool_name = block.get("name", "unknown")
                                        tool_input = block.get("input", {})
                                        # Format tool details like terminal
                                        detail = ""
                                        if tool_name == "Bash":
                                            cmd = tool_input.get("command", "")
                                            detail = f"\n```bash\n{cmd}\n```" if cmd else ""
                                        elif tool_name in ("Read", "Write", "Edit"):
                                            fp = tool_input.get("file_path", "") or tool_input.get("path", "")
                                            detail = f" `{fp}`" if fp else ""
                                        elif tool_name == "Glob":
                                            pat = tool_input.get("pattern", "")
                                            path = tool_input.get("path", "")
                                            detail = f" `{pat}`" + (f" in `{path}`" if path else "")
                                        elif tool_name == "Grep":
                                            pat = tool_input.get("pattern", "")
                                            path = tool_input.get("path", "")
                                            detail = f" `{pat}`" + (f" in `{path}`" if path else "")
                                        elif tool_name == "WebSearch":
                                            q = tool_input.get("query", "")
                                            detail = f" `{q}`" if q else ""
                                        elif tool_name == "WebFetch":
                                            url = tool_input.get("url", "")
                                            detail = f" `{url}`" if url else ""
                                        elif tool_name == "Agent":
                                            desc = tool_input.get("description", "")
                                            stype = tool_input.get("subagent_type", "")
                                            prompt_preview = (tool_input.get("prompt", "") or "")[:200]
                                            detail = f" **{desc}**" if desc else ""
                                            if stype:
                                                detail += f" ({stype})"
                                            if prompt_preview:
                                                detail += f"\n> {prompt_preview}{'…' if len(tool_input.get('prompt',''))>200 else ''}"
                                        elif tool_name == "Skill":
                                            skill = tool_input.get("skill", "")
                                            args = tool_input.get("args", "")
                                            detail = f" `/{skill}`" + (f" {args[:100]}" if args else "")
                                        elif tool_name == "TodoWrite":
                                            detail = f" ({len(tool_input.get('todos', []))} items)"
                                        elif tool_name == "TaskCreate":
                                            subj = tool_input.get("subject", "")
                                            detail = f" `{subj}`" if subj else ""
                                        elif tool_name == "TaskUpdate":
                                            tid = tool_input.get("taskId", "")
                                            st = tool_input.get("status", "")
                                            detail = f" #{tid}" + (f" → {st}" if st else "")
                                        elif tool_name in ("TaskList", "TaskGet"):
                                            tid = tool_input.get("taskId", "")
                                            detail = f" #{tid}" if tid else ""
                                        elif tool_name == "EnterPlanMode":
                                            detail = " 📋 进入规划模式"
                                            _in_plan_mode = True
                                        elif tool_name == "ExitPlanMode":
                                            detail = " 📋 退出规划模式"
                                            _plan_exit_pending = True
                                            _in_plan_mode = False
                                        elif tool_name == "AskUserQuestion":
                                            qs = tool_input.get("questions", [])
                                            if qs and isinstance(qs, list):
                                                detail = f" `{qs[0].get('question', '')[:100]}`"
                                        elif tool_name == "NotebookEdit":
                                            nb = tool_input.get("notebook_path", "")
                                            detail = f" `{nb}`" if nb else ""
                                        elif tool_name == "CronCreate":
                                            cron = tool_input.get("cron", "")
                                            detail = f" `{cron}`" if cron else ""
                                        elif tool_name == "ScheduleWakeup":
                                            reason = tool_input.get("reason", "")
                                            detail = f" {reason[:100]}" if reason else ""
                                        elif tool_name == "SendMessage":
                                            to = tool_input.get("to", "")
                                            detail = f" → {to}" if to else ""
                                        self._log(pp, task_id, "tool_use",
                                                  f"🔧 {tool_name}{detail}")
                            if texts:
                                text = "\n".join(texts)
                                # Filter out CC's internal "No response requested" message
                                # that occurs when --resume injects "Continue from where you left off"
                                if text.strip() == "No response requested.":
                                    continue
                                if text != last_assistant_text:
                                    last_assistant_text = text
                                    # Use [assistant] event type for full-fidelity
                                    # streaming output (rendered as chat bubbles in
                                    # the frontend, not condensed info pills).
                                    self._log(pp, task_id, "assistant", text)

                        elif etype == "user":
                            # Extract tool results for display
                            user_content = event.get("message", {}).get("content", [])
                            if isinstance(user_content, list):
                                for block in user_content:
                                    if isinstance(block, dict) and block.get("type") == "tool_result":
                                        result_text = block.get("content", "")
                                        if isinstance(result_text, list):
                                            # Multi-block result
                                            parts = []
                                            for rb in result_text[:3]:
                                                if isinstance(rb, dict) and rb.get("type") == "text":
                                                    parts.append(rb.get("text", ""))
                                            result_text = "\n".join(parts)
                                        if result_text and len(str(result_text)) > 10:
                                            # Only log non-trivial results
                                            self._log(pp, task_id, "tool_result", str(result_text))

                        elif etype == "system" and event.get("subtype") == "compact_boundary":
                            self._log(pp, task_id, "info", "🔄 Context compacted")

                        elif etype == "last-prompt":
                            # last-prompt appears both mid-conversation (resume boundary)
                            # and at the very end (CC waiting for input). We cannot
                            # reliably distinguish these here — the same event type is
                            # used for both. Do NOT break on this event; rely on the
                            # "no new readline + process alive" polling loop combined
                            # with pending_send detection to handle idle state.
                            pass

                        elif etype == "attachment":
                            att = event.get("attachment", {})
                            if not isinstance(att, dict):
                                pass
                            else:
                                atype = att.get("type", "")
                                if atype == "invoked_skills":
                                    # Custom skill invocation (e.g. /taiji, /full-auto)
                                    skills_list = att.get("skills", [])
                                    names = [s.get("name", "?") for s in skills_list if isinstance(s, dict)]
                                    if names:
                                        self._log(pp, task_id, "info",
                                                  f"🎯 调用 Skill: /{', /'.join(names)}")
                                elif atype == "plan_mode":
                                    self._log(pp, task_id, "info", "📋 进入规划模式 (Plan Mode)")
                                elif atype == "plan_mode_exit":
                                    self._log(pp, task_id, "info", "📋 退出规划模式")
                                elif atype == "plan_mode_reentry":
                                    self._log(pp, task_id, "info", "📋 重新进入规划模式")
                                elif atype == "edited_text_file":
                                    fname = att.get("filename", "")
                                    snippet = att.get("snippet", "")
                                    # Detect /model command (edits settings.json)
                                    if "settings.json" in fname and snippet:
                                        self._log(pp, task_id, "info",
                                                  f"⚙️ 设置已变更 (`{fname}`)\n```\n{snippet[:500]}\n```")
                                    elif fname:
                                        self._log(pp, task_id, "info",
                                                  f"📝 文件已编辑: `{fname}`")
                                elif atype == "todo_reminder":
                                    items = att.get("content", [])
                                    if isinstance(items, list) and items:
                                        parts = []
                                        for it in items[:10]:
                                            if isinstance(it, dict):
                                                st = it.get("status", "pending")
                                                icon = {"completed": "✅", "in_progress": "🔄", "pending": "⬜"}.get(st, "⬜")
                                                parts.append(f"{icon} {it.get('content', '')[:80]}")
                                        if parts:
                                            self._log(pp, task_id, "info",
                                                      f"📋 任务进度:\n" + "\n".join(parts))
                                elif atype == "command_permissions":
                                    tools = att.get("allowedTools", [])
                                    if tools:
                                        self._log(pp, task_id, "info",
                                                  f"🔑 授权工具: {', '.join(tools)}")

                    else:
                        # No new line — check if process is still alive
                        if is_recovery and _turn_count > 0 and not hasattr(self, f'_recovery_logged_{task_id}'):
                            setattr(self, f'_recovery_logged_{task_id}', True)
                            print(f"[recover-tail] task#{task_id} caught up: {_turn_count} turns, in=${_running_input_tokens} out=${_running_output_tokens}, now polling for new lines")

                        # ── Idle detection: no new output for 30s with process alive ──
                        # CC writes `stop_reason=end_turn` then stops writing JSONL.
                        # If we've seen at least one turn and nothing new for 30s,
                        # the session is idle (waiting for user input via stdin).
                        # IMPORTANT: Only trigger if last stop_reason was "end_turn".
                        # If stop_reason was "tool_use", CC is waiting for a tool
                        # result (e.g. a long-running Bash command) — NOT idle!
                        if not hasattr(self, f'_no_output_since_{task_id}'):
                            setattr(self, f'_no_output_since_{task_id}', time.time())
                        _silence_secs = time.time() - getattr(self, f'_no_output_since_{task_id}')
                        _can_idle = _last_stop_reason == "end_turn"
                        if _can_idle and (_turn_count > 0 or is_recovery) and _silence_secs > 30:
                            # Confirm process is still alive (not just slow to exit)
                            _proc_alive = False
                            if proc is not None:
                                _proc_alive = proc.poll() is None
                            else:
                                info = self._read_pid(pp, task_id)
                                _proc_alive = bool(info and self._pid_alive(info["pid"]))
                            if _proc_alive:
                                _idle_break = True
                                break

                        # Check for pending user messages — break to deliver them
                        # Only check every few seconds to avoid DB spam
                        if not hasattr(self, f'_last_pm_check_{task_id}'):
                            setattr(self, f'_last_pm_check_{task_id}', 0)
                        _now = time.time()
                        # In recovery mode, _turn_count may be 0 (prior turns already
                        # processed). Still check for pending messages so they don't
                        # get stuck. The `_turn_count > 0 or is_recovery` condition
                        # allows recovery to detect leftover pending_send messages.
                        if (_turn_count > 0 or is_recovery) and _now - getattr(self, f'_last_pm_check_{task_id}') > 3:
                            setattr(self, f'_last_pm_check_{task_id}', _now)
                            try:
                                _pm_conn = pp.get_db()
                                _pm_count = _pm_conn.execute(
                                    "SELECT COUNT(*) as c FROM task_messages "
                                    "WHERE task_id=? AND role='user' AND status='pending_send'",
                                    (task_id,)).fetchone()["c"]
                                _pm_conn.close()
                                if _pm_count > 0:
                                    self._log(pp, task_id, "info", "📨 检测到待发送消息，退出监控进入消息处理")
                                    # In recovery mode, there's no message loop after
                                    # _tail_log — use idle_break to auto-start execution.
                                    if is_recovery:
                                        _idle_break = True
                                    break
                            except Exception:
                                pass

                        if proc is not None:
                            rc = proc.poll()
                            if rc is not None:
                                # Process ended — wait briefly for filesystem
                                # flush then loop back to read remaining lines
                                # through the FULL event processing path above
                                # (not a token-only drain).
                                time.sleep(1.5)
                                _proc_dead_retries = getattr(self, f'_drain_retries_{task_id}', 0) + 1
                                setattr(self, f'_drain_retries_{task_id}', _proc_dead_retries)
                                if _proc_dead_retries > 3:
                                    break  # no more data after 3 empty reads
                                continue  # loop back to readline()
                        else:
                            # Recovered process — check PID file
                            info = self._read_pid(pp, task_id)
                            if info and not self._pid_alive(info["pid"]):
                                time.sleep(1.5)
                                _proc_dead_retries = getattr(self, f'_drain_retries_{task_id}', 0) + 1
                                setattr(self, f'_drain_retries_{task_id}', _proc_dead_retries)
                                if _proc_dead_retries > 3:
                                    break
                                continue
                        time.sleep(0.5)
                _jsonl_offset = f.tell()  # save position for next call
                # Persist offset to DB so future resume/restart starts from here
                try:
                    _oc = pp.get_db()
                    _oc.execute("UPDATE tasks SET jsonl_offset=? WHERE id=?",
                                (_jsonl_offset, task_id))
                    _oc.commit(); _oc.close()
                except Exception:
                    pass
                # Clean up dynamic attrs
                for _attr in (f'_drain_retries_{task_id}', f'_last_pm_check_{task_id}',
                              f'_recovery_logged_{task_id}', f'_no_output_since_{task_id}'):
                    if hasattr(self, _attr):
                        delattr(self, _attr)
        else:
            # No session JSONL — just wait for process to end
            if proc is not None:
                proc.wait()

        # ── Idle break: CC is waiting for input, don't finalize ──
        if _idle_break:
            # Set agent_status='idle' and return without finalizing task status.
            # For recovery path: this means the task stays in_progress/idle.
            # For normal path (defer_status=True): caller handles the message loop.
            try:
                _ic = pp.get_db()
                _ic.execute("UPDATE tasks SET agent_status='idle', jsonl_offset=? WHERE id=?",
                            (_jsonl_offset, task_id))
                _ic.commit(); _ic.close()
            except Exception:
                pass
            self._log(pp, task_id, "info", "💬 交互模式：等待你的消息…")
            # For recovery: check if there are pending messages waiting.
            # If so, start a new execution thread to deliver them.
            if is_recovery:
                with self._lock:
                    self._threads.pop(task_id, None)
                try:
                    _pm_db = pp.get_db()
                    _pm_pending = _pm_db.execute(
                        "SELECT COUNT(*) as c FROM task_messages "
                        "WHERE task_id=? AND role='user' AND status IN ('pending_send','sending')",
                        (task_id,)).fetchone()["c"]
                    _pm_task = _pm_db.execute(
                        "SELECT session_id, model, effort, config_user FROM tasks WHERE id=?",
                        (task_id,)).fetchone()
                    _pm_db.close()
                    if _pm_pending > 0 and _pm_task and _pm_task["session_id"]:
                        self._log(pp, task_id, "info", f"📨 检测到 {_pm_pending} 条待发送消息，启动执行线程")
                        self.start_task(task_id, pp, "",
                                       config_user=_pm_task["config_user"],
                                       model=_pm_task["model"],
                                       effort=_pm_task["effort"],
                                       resume_session_id=_pm_task["session_id"])
                except Exception as e:
                    print(f"[recover-tail] task#{task_id} pending msg check error: {e}")
            # Return a result that signals idle state (not finalized)
            return {
                "rc": 0,
                "est_cost": 0,
                "turn_count": _turn_count,
                "last_assistant_text": last_assistant_text,
                "result_text": "",
                "proc": proc,
                "plan_exit_pending": _plan_exit_pending,
                "idle_break": True,
                "status_finalized": False,
                "jsonl_offset": _jsonl_offset,
                "prior_tokens": {
                    "input": _running_input_tokens,
                    "output": _running_output_tokens,
                    "cache_create": _running_cache_create,
                    "cache_read": _running_cache_read,
                    "turn_count": _turn_count,
                    "seen_ids": list(_seen_msg_ids),
                    "last_text": last_assistant_text,
                    "model_validated": _model_validated,
                },
            }

        # ── Final cost calculation and status ──
        est_cost = (
            _running_input_tokens * _price_in
            + _running_cache_create * _price_cache_create
            + _running_cache_read * _price_cache_read
            + _running_output_tokens * _price_out
        ) / 1_000_000
        _logical_in_final = (
            _running_input_tokens + _running_cache_create + _running_cache_read
        )
        self._update_cost(pp, task_id, est_cost,
                          _logical_in_final, _running_output_tokens)
        # NOTE: We no longer do a full JSONL rescan here (_calculate_cost_from_jsonl).
        # The incremental tracking above is the source of truth and avoids
        # double-counting when _tail_log is called multiple times (resume path).

        # Also write to cost_usd as final value
        try:
            conn = pp.get_db()
            conn.execute("UPDATE tasks SET cost_usd=? WHERE id=?",
                         (round(est_cost, 4), task_id))
            conn.commit(); conn.close()
        except Exception:
            pass

        # Read stdout log for result text
        result_text = ""
        try:
            log_path = self._log_path(pp, task_id)
            with open(str(log_path), "r") as lf:
                result_text = lf.read().strip()
                # Trim to last 2000 chars for summary
                if len(result_text) > 2000:
                    result_text = "..." + result_text[-2000:]
        except Exception:
            pass

        # Determine success: if process exited 0 and we got some turns
        rc = proc.returncode if (proc is not None and proc.poll() is not None) else None
        if rc is None and proc is not None:
            # Process still alive — wait a bit for it to finish naturally
            try:
                proc.wait(timeout=10)
                rc = proc.returncode
            except subprocess.TimeoutExpired:
                # Still running after 10s — terminate it
                # If we had valid turns, treat as success (agent did work then went idle)
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except Exception:
                    try:
                        proc.kill()
                        proc.wait(timeout=3)
                    except Exception:
                        pass
                rc = 0 if _turn_count > 0 else -1
        elif rc is None:
            rc = -1  # No process
        if is_recovery and rc == -1:
            # For recovered processes, try to get exit code via waitpid
            try:
                info = self._read_pid(pp, task_id)
                if info:
                    pid = info["pid"]
                    _pid, _status = os.waitpid(pid, os.WNOHANG)
                    if _pid != 0:
                        rc = os.WEXITSTATUS(_status) if os.WIFEXITED(_status) else -1
                    else:
                        rc = -1  # still running? shouldn't happen here
            except ChildProcessError:
                # Not our child — can't get exit code; check JSONL for clean exit
                rc = self._infer_rc_from_jsonl(jsonl_path, _turn_count)
                print(f"[recover-tail] task#{task_id} not a child process, inferred rc={rc} (turns={_turn_count})")
            except Exception as e:
                rc = self._infer_rc_from_jsonl(jsonl_path, _turn_count)
                print(f"[recover-tail] task#{task_id} waitpid error: {e}, inferred rc={rc}")
        if is_recovery:
            print(f"[recover-tail] task#{task_id} FINAL: rc={rc}, turns={_turn_count}, cost=${est_cost:.4f}")

        # Build result info dict
        _tail_result = {
            "rc": rc,
            "est_cost": est_cost,
            "turn_count": _turn_count,
            "last_assistant_text": last_assistant_text,
            "result_text": result_text,
            "proc": proc,
            "plan_exit_pending": _plan_exit_pending,
            # State for continuation: pass to next _tail_log call to avoid
            # re-reading the entire JSONL and double-counting tokens/messages.
            "jsonl_offset": _jsonl_offset,
            "prior_tokens": {
                "input": _running_input_tokens,
                "output": _running_output_tokens,
                "cache_create": _running_cache_create,
                "cache_read": _running_cache_read,
                "turn_count": _turn_count,
                "seen_ids": list(_seen_msg_ids),
                "last_text": last_assistant_text,
                "model_validated": _model_validated,
            },
        }

        # If defer_status is True, return the result without updating status
        # (caller will update status after the message loop)
        if defer_status:
            return _tail_result

        self._finalize_task_status(pp, task_id, _tail_result)

        # Clean up _threads if called directly (recovery path, not via _run_task)
        if is_recovery:
            with self._lock:
                self._threads.pop(task_id, None)
            # Clean up PID file
            try:
                pid_path = pp._store / "pids" / f"{task_id}.json"
                if pid_path.exists():
                    pid_path.unlink()
            except Exception:
                pass

    def _finalize_task_status(self, pp, task_id, result):
        """Update task status based on execution result.

        Extracted from _tail_log so it can be called either immediately
        (recovery path) or after the message loop (normal path).
        """
        rc = result["rc"]
        est_cost = result["est_cost"]
        _turn_count = result["turn_count"]
        last_assistant_text = result["last_assistant_text"]
        result_text = result["result_text"]
        proc = result["proc"]

        if rc == 0 and _turn_count > 0:
            # rc==0 with valid turns = task completed, unless TASK_INCOMPLETE
            check_text = last_assistant_text + "\n" + result_text
            if "TASK_INCOMPLETE" in check_text:
                # Explicit incomplete marker — agent says it couldn't finish
                self._log(pp, task_id, "agent_fail",
                          f"⚠️ 任务未完成 (${est_cost:.4f}, {_turn_count} turns): agent 报告 TASK_INCOMPLETE")
                self._update_status(pp, task_id, "failed", cost_usd=est_cost)
            else:
                # Normal completion — rc==0 means Claude exited cleanly
                self._log(pp, task_id, "agent_done",
                          f"✅ 执行完成 (${est_cost:.4f}, {_turn_count} turns)")
                self._update_status(pp, task_id, "completed", cost_usd=est_cost)
        elif _turn_count > 0:
            self._log(pp, task_id, "agent_fail",
                      f"⚠️ 进程退出 (code={rc}, ${est_cost:.4f}, {_turn_count} turns)")
            self._update_status(pp, task_id, "failed", cost_usd=est_cost)
        else:
            # No turns at all — startup failure
            # Use non-blocking stderr drain (see _drain_stderr_nonblocking
            # docstring): a raw read() on a live subprocess blocks until EOF.
            stderr_out = self._drain_stderr_nonblocking(proc, max_bytes=2000, timeout=0.5)
            stdout_out = ""
            try:
                log_path = self._log_path(pp, task_id)
                with open(str(log_path), "r") as lf:
                    stdout_out = lf.read().strip()[:500]
            except Exception:
                pass
            detail = stderr_out or stdout_out or "(无详细信息)"
            self._log(pp, task_id, "agent_fail",
                      f"❌ 进程无有效输出 (code={rc}): {detail}")
            self._update_status(pp, task_id, "failed", cost_usd=est_cost)

    def recover_tasks(self):
        """Called on server startup — reconcile DB state with actual processes.

        Two passes:
          1. PID-file driven: reattach surviving processes, finalize dead ones.
          2. DB-driven orphan sweep: scan all tasks where status='in_progress'
             and whose registered PID (if any) is not alive. This covers the
             case where the executor thread crashed mid-flight (e.g. the #27
             ENOTCONN bug) leaving NO pid file but the DB still says running.
             Without this pass those tasks would hang forever.
        """
        projects = get_registered_projects()
        seen_task_ids: set[tuple[str, int]] = set()  # (slug, task_id)
        for proj in projects:
            pp = ProjectPaths(proj["path"], slug=proj["slug"])
            pids_dir = pp._store / "pids"
            if pids_dir.exists():
                for pid_file in pids_dir.glob("*.json"):
                    self._recover_one_from_pidfile(pp, pid_file, seen_task_ids)
            # Second pass: DB sweep for orphaned in_progress tasks
            self._sweep_orphan_in_progress(pp, seen_task_ids)

    def _recover_one_from_pidfile(self, pp, pid_file, seen_task_ids):
        """Handle a single entry in pids/*.json during startup recovery."""
        try:
            info = json.loads(pid_file.read_text())
            task_id = info["task_id"]
            pid = info["pid"]
        except (OSError, ValueError, KeyError) as e:
            sys.stderr.write(f"[recover] bad pid file {pid_file}: {e}\n")
            if pid_file.exists():
                pid_file.unlink()
            return

        seen_task_ids.add((pp.slug, task_id))

        if self._pid_alive(pid):
            # Process survived — start tail thread.
            # Reconstruct session_jsonl path from DB.
            # Only sqlite lock errors are expected here; other errors are real.
            session_jsonl = None
            try:
                conn = pp.get_db()
                row = conn.execute("SELECT session_id FROM tasks WHERE id=?", (task_id,)).fetchone()
                conn.close()
                if row and row["session_id"]:
                    import re as _re
                    proj_slug = _re.sub(r'[^a-zA-Z0-9]', '-', str(pp.root))
                    session_jsonl = Path.home() / ".claude-internal" / "projects" / proj_slug / f"{row['session_id']}.jsonl"
            except sqlite3.OperationalError as e:
                sys.stderr.write(f"[recover] task#{task_id} DB read error: {e}\n")

            # Read persisted jsonl_offset from DB to avoid re-processing old events
            _recover_offset = 0
            try:
                _roc = pp.get_db()
                _ror = _roc.execute("SELECT jsonl_offset FROM tasks WHERE id=?", (task_id,)).fetchone()
                _roc.close()
                if _ror and _ror["jsonl_offset"]:
                    _recover_offset = int(_ror["jsonl_offset"])
            except Exception:
                pass

            with self._lock:
                if task_id in self._threads:
                    return
                self._threads[task_id] = None
            thread = threading.Thread(
                target=self._tail_log,
                args=(None, None, pp, task_id, session_jsonl),
                kwargs={"jsonl_offset": _recover_offset},
                daemon=True,
                name=f"recover-task-{task_id}",
            )
            with self._lock:
                self._threads[task_id] = thread
            thread.start()
            print(f"  ↳ Recovered task #{task_id} (PID {pid})")
            return

        # ── Process died while server was down ──
        # For interactive tasks: don't finalize — keep in_progress/idle
        # so the user can resume the conversation later.
        try:
            conn = pp.get_db()
            row = conn.execute("SELECT status, interactive FROM tasks WHERE id=?", (task_id,)).fetchone()
            conn.close()
            current_status = row["status"] if row else None
            is_interactive = bool(row["interactive"]) if row else False
        except sqlite3.OperationalError as e:
            sys.stderr.write(f"[recover] task#{task_id} DB read error: {e}\n")
            current_status = None
            is_interactive = False

        if current_status in ("completed", "failed"):
            if pid_file.exists():
                pid_file.unlink()
            print(f"  ↳ Task #{task_id} already {current_status}, cleaned PID file")
            return

        if is_interactive:
            # Interactive task whose CC process died during server restart:
            # set to idle (waiting for user) — NOT completed/failed.
            try:
                conn = pp.get_db()
                conn.execute("UPDATE tasks SET agent_status='idle' WHERE id=?", (task_id,))
                conn.commit(); conn.close()
            except Exception:
                pass
            self._log(pp, task_id, "info",
                      "💬 服务重启，交互会话保持活跃。发送消息可继续对话。")
            if pid_file.exists():
                pid_file.unlink()
            print(f"  ↳ Interactive task #{task_id}: kept in_progress/idle after restart")
            return

        # Not yet finalized — determine final state from log.
        # Errors reading the log are logged and force a 'failed' finalization
        # rather than silently skipping.
        log_path = self._log_path(pp, task_id)
        if log_path.exists():
            last_text = ""
            has_result = False
            try:
                with open(str(log_path)) as lf:
                    for line in lf:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            ev = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if ev.get("type") == "result":
                            has_result = True
                            result_text = ev.get("result", "")
                            cost = ev.get("total_cost_usd", 0)
                            if self._check_result_complete(result_text):
                                self._log(pp, task_id, "agent_done",
                                          f"✅ 执行完成 (恢复判定, ${cost:.4f})\n{result_text}")
                                self._update_status(pp, task_id, "completed", cost_usd=cost)
                            else:
                                self._log(pp, task_id, "agent_fail",
                                          f"⚠️ 任务未完成 (恢复判定, ${cost:.4f})\n{result_text}")
                                self._update_status(pp, task_id, "failed", cost_usd=cost)
                        elif ev.get("type") == "assistant":
                            for b in ev.get("message", {}).get("content", []):
                                if isinstance(b, dict) and b.get("type") == "text":
                                    last_text = b.get("text", "")
            except OSError as e:
                sys.stderr.write(f"[recover] task#{task_id} log read error: {e}\n")
                self._log(pp, task_id, "agent_fail",
                          f"⚠️ 恢复时读取日志失败: {e}")
                self._update_status(pp, task_id, "failed")

            if not has_result:
                if self._check_result_complete(last_text):
                    self._log(pp, task_id, "agent_done", "执行完成 (恢复判定，无结果事件)")
                    self._update_status(pp, task_id, "completed")
                else:
                    self._log(pp, task_id, "agent_fail",
                              "⚠️ 进程在服务重启期间终止，未输出完成标记")
                    self._update_status(pp, task_id, "failed")
        else:
            self._log(pp, task_id, "agent_fail", "进程在服务重启期间丢失")
            self._update_status(pp, task_id, "failed")

        if pid_file.exists():
            pid_file.unlink()
        print(f"  ↳ Finalized dead task #{task_id} (PID {pid})")

    def _sweep_orphan_in_progress(self, pp, seen_task_ids):
        """Mark as failed any in_progress task whose executor thread is gone.

        Runs AFTER the PID-file pass. Catches the case where the executor
        thread died without leaving a pid file (e.g. crashed before
        _write_pid, or the pid file was removed by _remove_pid in a
        partial cleanup path, but the DB status was never updated).

        A task is considered orphaned when BOTH are true:
          - status = 'in_progress'
          - no pid file exists for it in this project
            (and it wasn't already handled by the PID-file pass above)

        This is what would have auto-recovered #27: the ENOTCONN killed
        the thread AND removed the pid file, but DB stayed in_progress.
        """
        try:
            conn = pp.get_db()
            rows = conn.execute(
                "SELECT id, interactive FROM tasks WHERE status='in_progress'"
            ).fetchall()
            conn.close()
        except sqlite3.OperationalError as e:
            sys.stderr.write(f"[orphan-sweep] DB read error: {e}\n")
            return

        for row in rows:
            task_id = row["id"]
            if (pp.slug, task_id) in seen_task_ids:
                continue  # already handled by PID-file pass
            # Interactive tasks: keep alive as idle, don't mark as failed
            if row["interactive"]:
                try:
                    conn = pp.get_db()
                    conn.execute("UPDATE tasks SET agent_status='idle' WHERE id=?", (task_id,))
                    conn.commit(); conn.close()
                except Exception:
                    pass
                # Check if there are pending messages waiting to be sent.
                # If so, auto-start execution to deliver them.
                _has_pending = False
                try:
                    _opc = pp.get_db()
                    _op_count = _opc.execute(
                        "SELECT COUNT(*) as c FROM task_messages "
                        "WHERE task_id=? AND role='user' AND status IN ('pending_send','sending')",
                        (task_id,)).fetchone()["c"]
                    _op_task = _opc.execute(
                        "SELECT session_id, model, effort, config_user FROM tasks WHERE id=?",
                        (task_id,)).fetchone()
                    _opc.close()
                    if _op_count > 0 and _op_task and _op_task["session_id"]:
                        _has_pending = True
                        self._log(pp, task_id, "info",
                                  f"📨 检测到 {_op_count} 条待发送消息，自动恢复执行")
                        self.start_task(task_id, pp, "",
                                       config_user=_op_task["config_user"],
                                       model=_op_task["model"],
                                       effort=_op_task["effort"],
                                       resume_session_id=_op_task["session_id"])
                except Exception as e:
                    print(f"  ↳ Orphan task #{task_id} pending check error: {e}")
                if not _has_pending:
                    self._log(pp, task_id, "info",
                              "💬 服务重启，交互会话保持活跃。发送消息可继续对话。")
                print(f"  ↳ Interactive orphan task #{task_id}: kept in_progress/idle"
                      + (f" (auto-resumed {_op_count} pending msgs)" if _has_pending else ""))
                continue
            # No pid file → executor thread is definitely not around.
            # (Running thread would have a pid file from _write_pid.)
            self._log(pp, task_id, "agent_fail",
                      "⚠️ 发现孤儿任务: DB 状态为 in_progress 但无存活进程。"
                      "可能原因: 执行线程崩溃 (如文件系统挂载中断)。自动标记为 failed。"
                      "可通过 /api/tasks/{id}/resume 继续会话。")
            self._update_status(pp, task_id, "failed")
            print(f"  ↳ Swept orphan in_progress task #{task_id} → failed")


# Global executor instance
task_executor = TaskExecutor()
# ═══════════════════════════════════════════════════════════════════════════

_skills_cache = {}  # keyed by project path


def _parse_skill_md(md_path, name):
    """Parse a SKILL.md file and return an info dict."""
    info = {"name": name, "description": "", "short_desc": name}
    try:
        text = md_path.read_text(encoding="utf-8", errors="replace")
        fm_m = re.match(r'^---\s*\n(.*?)\n---', text, re.DOTALL)
        if fm_m:
            fm = yaml.safe_load(fm_m.group(1))
            if isinstance(fm, dict):
                info["description"] = fm.get("description", "").strip()
                info["short_desc"] = info["description"].split("\n")[0][:120]
    except Exception:
        pass
    return info


def _parse_claude_md(md_path, name):
    """Extract first non-empty line from CLAUDE.md as short description."""
    info = {"name": name, "description": "", "short_desc": name}
    try:
        text = md_path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            line = line.strip().lstrip("#").strip()
            if line:
                info["short_desc"] = line[:120]
                info["description"] = line[:120]
                break
    except Exception:
        pass
    return info


def scan_skills(skills_dir):
    """Scan skills directory with four-level fallback:
    1. <skill_dir>/SKILL.md                      (standard)
    2. <skill_dir>/skills/*/SKILL.md             (bundled sub-skills, e.g. pua)
    3. <skill_dir>/.claude/skills/*/SKILL.md     (repo-style packages, e.g. Skill-Research-Figure, TaijiSkills)
    4. <skill_dir>/CLAUDE.md                     (legacy fallback)
    """
    skills = []
    seen_names = set()
    if not skills_dir.is_dir():
        return skills
    for d in sorted(skills_dir.iterdir()):
        if not d.is_dir():
            continue
        # Level 1: direct SKILL.md
        direct_md = d / "SKILL.md"
        if direct_md.exists():
            info = _parse_skill_md(direct_md, d.name)
            skills.append(info)
            seen_names.add(d.name)
            continue
        # Level 2: bundled sub-skills at skills/*/SKILL.md
        sub_skills_dir = d / "skills"
        if sub_skills_dir.is_dir():
            sub_added = False
            for sub in sorted(sub_skills_dir.iterdir()):
                if not sub.is_dir():
                    continue
                sub_md = sub / "SKILL.md"
                if sub_md.exists() and sub.name not in seen_names:
                    info = _parse_skill_md(sub_md, sub.name)
                    skills.append(info)
                    seen_names.add(sub.name)
                    sub_added = True
            if sub_added:
                continue
        # Level 3: repo-style .claude/skills/*/SKILL.md
        dot_claude_skills = d / ".claude" / "skills"
        if dot_claude_skills.is_dir():
            sub_added = False
            for sub in sorted(dot_claude_skills.iterdir()):
                if not sub.is_dir():
                    continue
                sub_md = sub / "SKILL.md"
                if sub_md.exists() and sub.name not in seen_names:
                    info = _parse_skill_md(sub_md, sub.name)
                    skills.append(info)
                    seen_names.add(sub.name)
                    sub_added = True
            if sub_added:
                continue
        # Level 4: CLAUDE.md fallback
        claude_md = d / "CLAUDE.md"
        if claude_md.exists() and d.name not in seen_names:
            info = _parse_claude_md(claude_md, d.name)
            skills.append(info)
            seen_names.add(d.name)
    return skills


USER_SKILLS_DIR = Path.home() / ".claude" / "skills"


def get_skills(pp):
    key = str(pp.root)
    if key not in _skills_cache:
        project_skills = scan_skills(pp.skills_dir)
        user_skills = scan_skills(USER_SKILLS_DIR)
        # Merge: project skills take precedence over user skills
        seen = {s["name"] for s in project_skills}
        merged = list(project_skills)
        for s in user_skills:
            if s["name"] not in seen:
                merged.append(s)
                seen.add(s["name"])
        _skills_cache[key] = merged
    return _skills_cache[key]


def parse_skill_input(text, pp):
    """Detect /skill_name anywhere in the text (not just at the start).

    Returns (skill_name, description, skill_tag).
    If a skill is found, description is the full text (skill stays inline).
    """
    known = {s["name"] for s in get_skills(pp)}
    # Search for /skillname anywhere (after start, space, or newline)
    for m in re.finditer(r'(?:^|(?<=\s))\/(\S+)', text.strip()):
        name = m.group(1)
        if name in known:
            return name, text.strip(), name
    return None, text.strip(), None


# ═══════════════════════════════════════════════════════════════════════════
# Context file helpers
# ═══════════════════════════════════════════════════════════════════════════

def read_context(pp):
    # Prefer centralised store; fall back to legacy project-tree file
    if pp.context_file.exists():
        return pp.context_file.read_text(encoding="utf-8")
    if pp._legacy_context.exists():
        try:
            text = pp._legacy_context.read_text(encoding="utf-8")
            # Migrate to centralised store
            write_context(pp, text)
            return text
        except Exception:
            pass
    return ""


def write_context(pp, content):
    pp._store.mkdir(parents=True, exist_ok=True)
    pp.context_file.write_text(content, encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════
# Common template context
# ═══════════════════════════════════════════════════════════════════════════

# Stable color palette for projects (cycles if >8 projects)
_PROJECT_COLORS = [
    "#4f86c6", "#e07b54", "#5aaa6f", "#a86dc0",
    "#d4a017", "#3aacb8", "#c75d7b", "#7a8fa6",
]

def _get_project_color(slug):
    projects = get_registered_projects()
    idx = next((i for i, p in enumerate(projects) if p["slug"] == slug), 0)
    return _PROJECT_COLORS[idx % len(_PROJECT_COLORS)]


def get_all_projects_with_meta():
    """Return all registered projects with stats + color, for multi-project view."""
    # TTL cache — called on every page load AND /api/stats poll (~5s interval).
    # With dop-fuse each DB open costs ~2s; caching gives 1s freshness for ~0ms cost.
    import time as _time
    now = _time.time()
    cached = _STATS_CACHE.get("projects_meta")
    if cached and cached[0] > now:
        return cached[1]
    projects = get_registered_projects()
    result = []
    for i, proj in enumerate(projects):
        pp = ProjectPaths(proj["path"], slug=proj["slug"])
        color = _PROJECT_COLORS[i % len(_PROJECT_COLORS)]
        try:
            pp.ensure_db()
            conn = pp.get_db()
            rows = conn.execute("SELECT status, COUNT(*) as c FROM tasks GROUP BY status").fetchall()
            conn.close()
            c = {r["status"]: r["c"] for r in rows}
            total = sum(c.values())
            result.append({**proj, "color": color,
                           "counts": {"pending": c.get("pending", 0),
                                      "in_progress": c.get("in_progress", 0),
                                      "completed": c.get("completed", 0),
                                      "failed": c.get("failed", 0),
                                      "total": total}})
        except Exception:
            result.append({**proj, "color": color,
                           "counts": {"pending": 0, "in_progress": 0,
                                      "completed": 0, "failed": 0, "total": 0}})
    _STATS_CACHE["projects_meta"] = (now + _STATS_CACHE_TTL, result)
    return result


def get_all_tasks_across_projects(status_filter="all", show_archived=False):
    """Aggregate tasks from all registered projects for the unified view."""
    import time as _time
    now = _time.time()
    cache_key = ("all_tasks", status_filter, show_archived)
    cached = _STATS_CACHE.get(cache_key)
    if cached and cached[0] > now:
        return cached[1]
    projects = get_registered_projects()
    all_tasks = []
    for i, proj in enumerate(projects):
        pp = ProjectPaths(proj["path"], slug=proj["slug"])
        color = _PROJECT_COLORS[i % len(_PROJECT_COLORS)]
        try:
            pp.ensure_db()
            conn = pp.get_db()
            archive_clause = "" if show_archived else " AND (archived=0 OR archived IS NULL)"
            if status_filter and status_filter != "all":
                rows = conn.execute(
                    f"SELECT * FROM tasks WHERE status=?{archive_clause} ORDER BY position ASC",
                    (status_filter,)).fetchall()
            else:
                rows = conn.execute(
                    f"SELECT * FROM tasks WHERE 1=1{archive_clause} ORDER BY position ASC").fetchall()
            for r in rows:
                t = row_to_dict(r)
                t["_project_slug"] = proj["slug"]
                t["_project_name"] = proj["name"]
                t["_project_path"] = proj["path"]
                t["_project_color"] = color
                t["_is_blocked"] = len(check_blocked(conn, t["id"])) > 0
                t["_has_active_conflict"] = len(check_conflicts_active(conn, t["id"])) > 0
                all_tasks.append(t)
            conn.close()
        except Exception:
            pass
    _STATS_CACHE[cache_key] = (now + _STATS_CACHE_TTL, all_tasks)
    return all_tasks


def _base_ctx(pp, slug):
    """Common variables injected into every template."""
    projects_meta = get_all_projects_with_meta()
    color = next((p["color"] for p in projects_meta if p["slug"] == slug), "#4f86c6")
    return {
        "project_root": str(pp.root),
        "project_name": pp.name,
        "project_slug": slug,
        "project_color": color,
        "all_projects": projects_meta,  # now includes color + counts
    }


# ═══════════════════════════════════════════════════════════════════════════
# Page routes
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    pp, slug = _get_pp()
    if pp is None:
        return render_template("no_project.html", all_projects=[])

    status_filter = request.args.get("status", "all")
    project_filter = request.args.get("proj", "all")  # filter by project slug
    show_archived = request.args.get("archived", "0") == "1"
    sort_order = request.args.get("sort", "newest")  # newest (default) or position

    # Multi-project aggregated view
    projects_meta = get_all_projects_with_meta()
    all_tasks = get_all_tasks_across_projects(status_filter, show_archived=show_archived)
    if project_filter != "all":
        all_tasks = [t for t in all_tasks if t["_project_slug"] == project_filter]

    # Sort tasks: newest first (by created_at desc) or by position (legacy)
    if sort_order == "newest":
        all_tasks.sort(key=lambda t: t.get("created_at", "") or "", reverse=True)
    # else: keep default position-based order from DB

    # Aggregate counts across all projects
    agg = {"pending": 0, "in_progress": 0, "completed": 0, "failed": 0,
           "decomposed": 0, "total": 0, "active_total": 0}
    for p in projects_meta:
        for k in ("pending", "in_progress", "completed", "failed"):
            agg[k] += p["counts"].get(k, 0)
        agg["total"] += p["counts"].get("total", 0)
    agg["active_total"] = agg["total"] - agg.get("decomposed", 0)

    resp = app.make_response(render_template("index.html",
        tasks=all_tasks, counts=agg, current_filter=status_filter,
        project_filter=project_filter, projects_meta=projects_meta,
        show_archived=show_archived, sort_order=sort_order,
        todo_file_exists=pp.todo_file.exists(),
        skills=get_skills(pp),
        **_base_ctx(pp, slug)))
    resp.set_cookie("last_project", slug, max_age=86400 * 365)
    return resp


@app.route("/task/<int:task_id>")
def task_detail(task_id):
    pp, slug = _get_pp_or_404()
    conn = pp.get_db()
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        conn.close(); abort(404)
    task = row_to_dict(row)
    task["parsed_files"] = []
    if task.get("modified_files"):
        try:
            f = json.loads(task["modified_files"])
            task["parsed_files"] = f if isinstance(f, list) else []
        except Exception:
            task["parsed_files"] = [task["modified_files"]]
    parent = None
    if task.get("parent_id"):
        pr = conn.execute("SELECT id,description FROM tasks WHERE id=?", (task["parent_id"],)).fetchone()
        parent = row_to_dict(pr)
    subs = [row_to_dict(r) for r in conn.execute(
        "SELECT * FROM tasks WHERE parent_id=? ORDER BY position ASC", (task_id,)).fetchall()]
    rels = get_task_relations(conn, task_id)
    blockers = check_blocked(conn, task_id)
    conflicts = check_conflicts_active(conn, task_id)
    task_ctx = get_context_log(conn, limit=50, task_id=task_id)
    messages, has_more_msgs = get_task_messages(conn, task_id, limit=200)
    all_tasks = [row_to_dict(r) for r in conn.execute(
        "SELECT id,description,tag,status FROM tasks WHERE id!=? ORDER BY position ASC", (task_id,)).fetchall()]
    conn.close()
    return render_template("detail.html",
        task=task, parent=parent, subtasks=subs, relations=rels,
        blockers=blockers, conflicts_active=conflicts, all_tasks=all_tasks,
        task_context=task_ctx, messages=messages, has_more_msgs=has_more_msgs,
        skills=get_skills(pp),
        config_users=get_available_configs(),
        **_base_ctx(pp, slug))


@app.route("/context")
def context_page():
    pp, slug = _get_pp_or_404()
    conn = pp.get_db()
    entries = get_context_log(conn, limit=200)
    conn.close()
    return render_template("context.html", entries=entries, context_md=read_context(pp),
                           skills=get_skills(pp), **_base_ctx(pp, slug))


@app.route("/skills")
def skills_page():
    pp, slug = _get_pp_or_404()
    return render_template("skills.html", skills=get_skills(pp), **_base_ctx(pp, slug))


# ═══════════════════════════════════════════════════════════════════════════
# API — Projects
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/projects", methods=["GET"])
def api_list_projects():
    projects = get_registered_projects()
    # Annotate with task counts
    for proj in projects:
        pp = ProjectPaths(proj["path"], slug=proj["slug"])
        if pp.db.exists():
            try:
                conn = pp.get_db()
                proj["counts"] = get_counts(conn)
                conn.close()
            except Exception:
                proj["counts"] = None
        else:
            proj["counts"] = None
    return jsonify({"projects": projects})


@app.route("/api/projects", methods=["POST"])
def api_add_project():
    data = request.get_json(force=True)
    path = data.get("path", "").strip()
    if not path:
        return jsonify({"ok": False, "error": "path is required"}), 400
    ok, msg = register_project(path)
    if ok:
        slug = msg if msg != "已注册" else _project_slug(path)
        pp = ProjectPaths(path, slug=slug)
        pp.ensure_db()
        name = Path(path).resolve().name
        color = _get_project_color(slug)
        return jsonify({"ok": True, "slug": slug, "name": name, "color": color})
    return jsonify({"ok": False, "error": msg}), 400


@app.route("/api/path-suggest")
def api_path_suggest():
    """Return directory completions for a given path prefix, VSCode-style.

    Logic:
    - Empty input  → list cwd children
    - Ends with /  → list that dir's children (support .. normalization)
    - Otherwise    → list siblings matching the typed basename prefix
    Returns {cwd, suggestions: [{display, full}]}
    """
    prefix = request.args.get("q", "")
    try:
        cwd = Path.cwd()

        if not prefix:
            # No input → list cwd
            parent = cwd
            basename = ""
        elif prefix.endswith("/"):
            # Trailing slash → resolve and list that dir
            parent = Path(prefix).resolve()
            basename = ""
        else:
            raw = Path(prefix)
            if raw.is_absolute():
                parent = raw.parent
                basename = raw.name
            else:
                parent = (cwd / raw).resolve().parent
                basename = raw.name

        # Resolve .. etc
        parent = parent.resolve()

        if not parent.is_dir():
            return jsonify({"cwd": str(cwd), "suggestions": []})

        # Gather matching subdirs
        suggestions = []
        try:
            entries = sorted(parent.iterdir(), key=lambda e: e.name.lower())
        except PermissionError:
            return jsonify({"cwd": str(cwd), "suggestions": []})

        for entry in entries:
            if not entry.is_dir():
                continue
            # Skip hidden only if not explicitly typed
            if entry.name.startswith(".") and not basename.startswith("."):
                continue
            if basename and not entry.name.lower().startswith(basename.lower()):
                continue
            suggestions.append({"display": entry.name, "full": str(entry)})
            if len(suggestions) >= 15:
                break

        return jsonify({"cwd": str(cwd), "suggestions": suggestions})
    except Exception as exc:
        return jsonify({"cwd": str(Path.cwd()), "suggestions": [], "error": str(exc)})

@app.route("/api/projects/<slug>", methods=["DELETE"])
def api_remove_project(slug):
    unregister_project(slug)
    resp = jsonify({"ok": True})
    # Clear cookie if it was pointing at this project
    if request.cookies.get("last_project") == slug:
        resp.delete_cookie("last_project")
    return resp


# ═══════════════════════════════════════════════════════════════════════════
# API — Tasks (all project-scoped via ?p=slug)
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/stats")
def api_stats():
    """Cross-project stats + tasks, optionally filtered by project slug."""
    status_filter = request.args.get("status", "all")
    project_filter = request.args.get("proj", "all")
    sort_order = request.args.get("sort", "newest")
    projects_meta = get_all_projects_with_meta()
    all_tasks = get_all_tasks_across_projects(status_filter)
    if project_filter != "all":
        all_tasks = [t for t in all_tasks if t["_project_slug"] == project_filter]
    # Sort tasks: newest first (by created_at desc) or by position (legacy)
    if sort_order == "newest":
        all_tasks.sort(key=lambda t: t.get("created_at", "") or "", reverse=True)
    agg = {"pending": 0, "in_progress": 0, "completed": 0, "failed": 0,
           "decomposed": 0, "total": 0, "active_total": 0}
    for p in projects_meta:
        for k in ("pending", "in_progress", "completed", "failed"):
            agg[k] += p["counts"].get(k, 0)
        agg["total"] += p["counts"].get("total", 0)
    agg["active_total"] = agg["total"] - agg.get("decomposed", 0)
    payload = {"counts": agg, "tasks": all_tasks,
               "projects": projects_meta,
               "config_users": get_available_configs()}
    # Cheap ETag — lets the browser's If-None-Match skip the JSON download
    # when nothing has changed since the last poll (dashboard polls every 5s
    # regardless). Hash a stable subset; excludes volatile fields like elapsed.
    import hashlib as _hl, json as _json
    tag_src = _json.dumps({
        "c": agg,
        "t": [(t.get("id"), t.get("status"), t.get("agent_status"), t.get("cost_usd"),
               t.get("total_input_tokens"), t.get("started_at"),
               t.get("_is_blocked"), t.get("_has_active_conflict"),
               (t.get("description") or "")[:64]) for t in all_tasks],
        "p": [(p.get("slug"), p.get("counts")) for p in projects_meta],
    }, sort_keys=True).encode("utf-8")
    etag = '"' + _hl.md5(tag_src).hexdigest() + '"'
    inm = request.headers.get("If-None-Match", "")
    if inm and inm == etag:
        resp = make_response("", 304)
        resp.headers["ETag"] = etag
        resp.headers["Cache-Control"] = "no-cache"
        return resp
    resp = jsonify(payload)
    resp.headers["ETag"] = etag
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.route("/api/tasks", methods=["POST"])
def api_create_task():
    data = request.get_json(force=True)
    # Allow caller to specify a project slug in the body (multi-project task creation)
    body_slug = data.get("project_slug", "").strip()
    if body_slug:
        proj = find_project_by_slug(body_slug)
        if not proj:
            return jsonify({"ok": False, "error": f"Project not found: {body_slug}"}), 404
        pp = ProjectPaths(proj["path"], slug=proj["slug"])
        slug = body_slug
    else:
        pp, slug = _get_pp_or_404()
    raw = data.get("description", "").strip()
    tag = data.get("tag", "").strip() or None
    acceptance_criteria = data.get("acceptance_criteria", "").strip() or None
    human_review = 1 if data.get("human_review") else 0
    auto_execute = 1  # Always auto-execute — no reason to create a task and not start it
    interactive = 1 if data.get("interactive") else 0
    config_user = data.get("config_user", "").strip() or None
    max_cost_usd = float(data.get("max_cost_usd", 5.0))
    model = data.get("model", "sonnet").strip() or "sonnet"
    effort = data.get("effort", "medium").strip() or "medium"
    if effort not in ("low", "medium", "high", "xhigh", "max"):
        effort = "medium"
    # Server-side downgrade 与 Claude Code CLI 对齐：
    # xhigh 仅 Opus 4.7；max 仅 Opus；其他模型会被 CLI 静默降级，这里提前降为 high 避免隐蔽失效
    if effort in ("xhigh", "max") and model != "opus":
        effort = "high"
    if not raw:
        return jsonify({"ok": False, "error": "Description is required"}), 400

    # ── Idempotency guard: collapse double-submits ───────────────────────────
    # A duplicate POST (same client_nonce, OR same project+description signature)
    # arriving inside _CREATE_DEDUP_TTL returns the *original* task id instead
    # of spawning a second row + second Claude Code process.
    import time as _time, hashlib as _hashlib
    client_nonce = (data.get("client_nonce") or "").strip()
    desc_sig = _hashlib.sha1(f"{slug}\0{raw}\0{tag or ''}\0{model}\0{effort}".encode("utf-8")).hexdigest()[:16]
    dedup_keys = [("n", slug, client_nonce)] if client_nonce else []
    dedup_keys.append(("s", slug, desc_sig))
    _now = _time.time()
    with _CREATE_DEDUP_LOCK:
        # GC expired entries
        expired = [k for k, (exp, _tid, _sk) in _CREATE_DEDUP.items() if exp < _now]
        for k in expired:
            _CREATE_DEDUP.pop(k, None)
        for k in dedup_keys:
            hit = _CREATE_DEDUP.get(k)
            if hit and hit[0] >= _now:
                _dup_tid, _dup_skill = hit[1], hit[2]
                return jsonify({"ok": True, "id": _dup_tid, "skill": _dup_skill,
                                "project_slug": slug,
                                "auto_execute": bool(auto_execute),
                                "auto_started": False,
                                "deduped": True})

    pp.ensure_db()
    skill_name, desc, skill_tag = parse_skill_input(raw, pp)
    if skill_tag and not tag:
        tag = skill_tag
    conn = pp.get_db()
    row = conn.execute("SELECT MAX(position) as mp FROM tasks").fetchone()
    mx = row["mp"] if row["mp"] is not None else 0.0
    # Determine initial status: auto_execute=1 → in_progress, else pending
    initial_status = "in_progress" if auto_execute else "pending"
    started_at = now_str() if auto_execute else None
    cur = conn.execute(
        "INSERT INTO tasks (description,tag,status,position,created_at,started_at,skill,project_path,"
        "acceptance_type,acceptance_criteria,human_review,auto_execute,config_user,max_cost_usd,model,effort,interactive) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (desc, tag, initial_status, mx + 1.0, now_str(), started_at, skill_name, str(pp.root),
         'auto', acceptance_criteria, human_review, auto_execute, config_user, max_cost_usd, model, effort, interactive))
    conn.commit()
    tid = cur.lastrowid
    conn.close()

    # Record the dedup entry *before* starting the process — so a retry that
    # arrives while start_task is still running also collapses.
    _exp = _time.time() + _CREATE_DEDUP_TTL
    with _CREATE_DEDUP_LOCK:
        for k in dedup_keys:
            _CREATE_DEDUP[k] = (_exp, tid, skill_name)

    # Auto-execute: launch Claude Code process
    auto_started = False
    if auto_execute:
        auto_started = task_executor.start_task(tid, pp, desc, config_user=config_user, model=model, effort=effort)

    return jsonify({"ok": True, "id": tid, "skill": skill_name, "project_slug": slug,
                    "auto_execute": bool(auto_execute), "auto_started": auto_started})


@app.route("/api/tasks/<int:task_id>", methods=["PUT"])
def api_update_task(task_id):
    pp, _ = _get_pp_or_404()
    data = request.get_json(force=True)
    conn = pp.get_db()
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"ok": False, "error": "Not found"}), 404
    allowed = ["description", "tag", "notes", "conclusion", "skill", "config_user", "max_cost_usd", "model", "effort", "archived", "acceptance_criteria", "human_review", "auto_execute", "interactive"]
    # 与 Claude Code CLI 对齐：xhigh/max 仅 Opus 生效，否则强制降级到 high
    if "effort" in data:
        _eff = (data.get("effort") or "").strip() or "medium"
        if _eff not in ("low", "medium", "high", "xhigh", "max"):
            _eff = "medium"
        _mdl = (data.get("model") or row["model"] or "sonnet").strip()
        if _eff in ("xhigh", "max") and _mdl != "opus":
            _eff = "high"
        data["effort"] = _eff
    updates, values, warnings = [], [], []
    # Auto-detect skill from description if description is being updated
    if "description" in data and "skill" not in data:
        _skill_name, _, _skill_tag = parse_skill_input(data["description"], pp)
        if _skill_name:
            data["skill"] = _skill_tag
    for f in allowed:
        if f in data:
            updates.append(f"{f}=?"); values.append(data[f])
    if "status" in data:
        ns = data["status"]; os_ = row["status"]; force = data.get("force", False)
        if ns == "in_progress":
            bl = check_blocked(conn, task_id)
            if bl and not force:
                conn.close()
                return jsonify({"ok": False, "error": "blocked", "message": "被阻塞",
                                "blockers": [f"#{b['id']} {b['description']}" for b in bl]}), 409
            cf = check_conflicts_active(conn, task_id)
            if cf and not force:
                conn.close()
                return jsonify({"ok": False, "error": "conflict", "message": "有冲突",
                                "conflicts": [f"#{c['id']} {c['description']}" for c in cf]}), 409
            if bl and force: warnings.append(f"忽略 {len(bl)} 个阻塞")
            if cf and force: warnings.append(f"忽略 {len(cf)} 个冲突")
        updates.append("status=?"); values.append(ns)
        if ns == "in_progress" and os_ == "pending":
            updates.append("started_at=?"); values.append(now_str())
        elif ns == "completed":
            ca = now_str(); updates.append("completed_at=?"); values.append(ca)
            if row["started_at"]:
                try:
                    d = (datetime.strptime(ca, "%Y-%m-%d %H:%M") - datetime.strptime(row["started_at"], "%Y-%m-%d %H:%M")).total_seconds() / 60
                    updates.append("duration_minutes=?"); values.append(round(d, 1))
                except ValueError: pass
        elif ns == "pending":
            for k in ("started_at", "completed_at", "duration_minutes", "notes"):
                updates.append(f"{k}=?"); values.append(None)
    if not updates:
        conn.close()
        return jsonify({"ok": False, "error": "Nothing to update"}), 400
    values.append(task_id)
    conn.execute(f"UPDATE tasks SET {','.join(updates)} WHERE id=?", values)
    conn.commit(); conn.close()
    r = {"ok": True, "id": task_id}
    if warnings: r["warnings"] = warnings
    return jsonify(r)


@app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
def api_delete_task(task_id):
    pp, _ = _get_pp_or_404()
    conn = pp.get_db()
    conn.execute("DELETE FROM tasks WHERE id=?", (task_id,)); conn.commit(); conn.close()
    return jsonify({"ok": True})


@app.route("/api/tasks/<int:task_id>/archive", methods=["POST"])
def api_archive_task(task_id):
    """Toggle archived flag on a task."""
    pp, _ = _get_pp_or_404()
    data = request.get_json(force=True) if request.is_json else {}
    archived = 1 if data.get("archived", True) else 0
    conn = pp.get_db()
    conn.execute("UPDATE tasks SET archived=? WHERE id=?", (archived, task_id))
    conn.commit(); conn.close()
    return jsonify({"ok": True, "archived": bool(archived)})


@app.route("/api/tasks/<int:task_id>/retry", methods=["POST"])
def api_retry_task(task_id):
    pp, _ = _get_pp_or_404()
    conn = pp.get_db()
    # Log previous cost before resetting
    row = conn.execute("SELECT cost_usd, estimated_cost_usd FROM tasks WHERE id=?", (task_id,)).fetchone()
    prev_cost = None
    if row:
        prev_cost = row["cost_usd"] or row["estimated_cost_usd"] if "estimated_cost_usd" in row.keys() else row["cost_usd"]
    if prev_cost:
        add_task_message(conn, task_id, "system",
                         f"[info] 🔄 重试任务（上次成本: ${prev_cost:.4f}）", status="done")
    # Reset status AND cost counters — fresh start
    conn.execute("UPDATE tasks SET status='pending',started_at=NULL,completed_at=NULL,"
                 "duration_minutes=NULL,notes=NULL,"
                 "cost_usd=NULL,estimated_cost_usd=NULL,"
                 "total_input_tokens=NULL,total_output_tokens=NULL,"
                 "session_id=NULL WHERE id=?", (task_id,))
    conn.commit(); conn.close()
    return jsonify({"ok": True})


# ═══════════════════════════════════════════════════════════════════════════
# API — Relations
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/relations", methods=["POST"])
def api_create_relation():
    pp, _ = _get_pp_or_404()
    data = request.get_json(force=True)
    sid, tid, rt = data.get("source_id"), data.get("target_id"), data.get("relation_type")
    note = data.get("note", "").strip() or None
    if not all([sid, tid, rt]):
        return jsonify({"ok": False, "error": "Missing fields"}), 400
    if rt not in ("blocks", "conflicts", "related"):
        return jsonify({"ok": False, "error": "Invalid type"}), 400
    if sid == tid:
        return jsonify({"ok": False, "error": "Self-relation"}), 400
    conn = pp.get_db()
    for i in [sid, tid]:
        if not conn.execute("SELECT id FROM tasks WHERE id=?", (i,)).fetchone():
            conn.close(); return jsonify({"ok": False, "error": f"#{i} not found"}), 404
    if conn.execute("SELECT id FROM task_relations WHERE source_id=? AND target_id=? AND relation_type=?",
                    (sid, tid, rt)).fetchone():
        conn.close(); return jsonify({"ok": False, "error": "Already exists"}), 409
    if rt == "blocks" and _has_path(conn, tid, sid, "blocks"):
        conn.close(); return jsonify({"ok": False, "error": "循环依赖"}), 409
    conn.execute("INSERT INTO task_relations (source_id,target_id,relation_type,note) VALUES (?,?,?,?)",
                 (sid, tid, rt, note))
    conn.commit(); rid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]; conn.close()
    return jsonify({"ok": True, "id": rid})


@app.route("/api/relations/<int:rid>", methods=["DELETE"])
def api_delete_relation(rid):
    pp, _ = _get_pp_or_404()
    conn = pp.get_db()
    conn.execute("DELETE FROM task_relations WHERE id=?", (rid,)); conn.commit(); conn.close()
    return jsonify({"ok": True})


# ═══════════════════════════════════════════════════════════════════════════
# API — Context
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/context", methods=["GET"])
def api_get_context():
    pp, _ = _get_pp_or_404()
    conn = pp.get_db()
    entries = get_context_log(conn)
    conn.close()
    return jsonify({"entries": entries, "brief": read_context(pp)})


@app.route("/api/context", methods=["POST"])
def api_add_context():
    pp, _ = _get_pp_or_404()
    data = request.get_json(force=True)
    content = data.get("content", "").strip()
    etype = data.get("entry_type", "note")
    tid = data.get("task_id")
    if not content: return jsonify({"ok": False, "error": "Empty"}), 400
    conn = pp.get_db()
    conn.execute("INSERT INTO context_log (task_id,entry_type,content) VALUES (?,?,?)", (tid, etype, content))
    conn.commit(); conn.close()
    return jsonify({"ok": True})


@app.route("/api/context/brief", methods=["PUT"])
def api_update_brief():
    pp, _ = _get_pp_or_404()
    write_context(pp, request.get_json(force=True).get("content", ""))
    return jsonify({"ok": True})


# ═══════════════════════════════════════════════════════════════════════════
# API — Skills & Sync/Export
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/skills")
def api_skills():
    pp, _ = _get_pp_or_404()
    _skills_cache.pop(str(pp.root), None)
    return jsonify({"skills": get_skills(pp)})


@app.route("/api/sync", methods=["POST"])
def api_sync():
    pp, _ = _get_pp_or_404()
    if not pp.todo_file.exists():
        return jsonify({"ok": False, "error": "TODO_LIST.md not found"}), 404
    subprocess.run([sys.executable, str(TASK_MANAGER), "init"],
                   capture_output=True, text=True, cwd=str(pp.root))
    r = subprocess.run([sys.executable, str(TASK_MANAGER), "sync", "--file", "TODO_LIST.md"],
                       capture_output=True, text=True, cwd=str(pp.root))
    try: return jsonify(json.loads(r.stdout))
    except Exception: return jsonify({"ok": False, "error": r.stderr or r.stdout}), 500


@app.route("/api/export", methods=["POST"])
def api_export():
    pp, _ = _get_pp_or_404()
    r = subprocess.run([sys.executable, str(TASK_MANAGER), "export"],
                       capture_output=True, text=True, cwd=str(pp.root))
    try: return jsonify(json.loads(r.stdout))
    except Exception: return jsonify({"ok": False, "error": r.stderr or r.stdout}), 500


# ═══════════════════════════════════════════════════════════════════════════
# API — Task Messages (Plan A + B conversation support)
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/tasks/<int:task_id>/messages", methods=["GET"])
def api_get_messages(task_id):
    pp, _ = _get_pp_or_404()
    conn = pp.get_db()
    # Support incremental fetch: ?after=<id> returns only messages with id > after
    after = request.args.get("after", type=int)
    # Support backward pagination: ?before=<id>&limit=N returns N messages before id
    before = request.args.get("before", type=int)
    limit = request.args.get("limit", type=int, default=0)
    if after:
        rows = conn.execute(
            "SELECT * FROM task_messages WHERE task_id=? AND id>? ORDER BY id ASC",
            (task_id, after)).fetchall()
    elif before:
        _lim = limit if limit > 0 else 200
        rows = conn.execute(
            "SELECT * FROM task_messages WHERE task_id=? AND id<? ORDER BY id DESC LIMIT ?",
            (task_id, before, _lim)).fetchall()
        rows = list(reversed(rows))  # back to ASC
    else:
        rows = conn.execute(
            "SELECT * FROM task_messages WHERE task_id=? ORDER BY id ASC",
            (task_id,)).fetchall()
    conn.close()
    return jsonify({"messages": [row_to_dict(r) for r in rows]})


@app.route("/api/tasks/<int:task_id>/messages", methods=["POST"])
def api_post_message(task_id):
    """User posts a follow-up message to a task.
    If the task has a live execution thread (full-auto or agent), mark as
    pending_send so the message loop can --resume the session.
    Otherwise store as 'done' (will be injected as history on next execution).
    """
    pp, _ = _get_pp_or_404()
    data = request.get_json(force=True)
    content = data.get("content", "").strip()
    if not content:
        return jsonify({"ok": False, "error": "content required"}), 400
    conn = pp.get_db()
    task_row = conn.execute("SELECT agent_id, agent_status, status, interactive, session_id, model, effort, config_user, description FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not task_row:
        conn.close(); abort(404)
    # Check if task has an active execution thread (full-auto mode)
    thread_alive = task_executor.is_running(task_id, pp)
    # Or an agent (interactive mode)
    agent_alive = task_row["agent_status"] in ("running", "idle") and task_row["agent_id"]
    can_send = thread_alive or agent_alive

    # Interactive task with no executor thread (e.g. after server restart):
    # auto-resume the session so the user's message gets delivered.
    if not can_send and task_row["interactive"] and task_row["status"] == "in_progress":
        session_id = task_row["session_id"]
        model = task_row["model"]
        effort = task_row["effort"]
        config_user = task_row["config_user"]

        if session_id:
            # Resume existing session — store as pending_send for 3-phase delivery
            mid = add_task_message(conn, task_id, "user", content, status="pending_send")
            conn.close()
            task_executor.start_task(task_id, pp, "",
                                     config_user=config_user, model=model,
                                     effort=effort, resume_session_id=session_id)
            return jsonify({"ok": True, "id": mid, "status": "pending_send",
                            "queued_for_agent": True,
                            "auto_resumed": True})
        else:
            # Session was cleared (e.g. after context overflow recovery) —
            # start a brand new CC session with the user's message as prompt.
            mid = add_task_message(conn, task_id, "user", content, status="done")
            conn.close()
            task_executor.start_task(task_id, pp, content,
                                     config_user=config_user, model=model,
                                     effort=effort)
            return jsonify({"ok": True, "id": mid, "status": "done",
                            "queued_for_agent": True,
                            "auto_resumed": True,
                            "new_session": True})

    status = "pending_send" if can_send else "done"
    mid = add_task_message(conn, task_id, "user", content, status=status)
    conn.close()
    return jsonify({"ok": True, "id": mid, "status": status,
                    "queued_for_agent": can_send})


@app.route("/api/tasks/<int:task_id>/agent", methods=["PUT"])
def api_set_agent(task_id):
    """Called by Claude Code (autorun skill) to register a background agent for a task."""
    pp, _ = _get_pp_or_404()
    data = request.get_json(force=True)
    agent_id = data.get("agent_id", "").strip()
    agent_status = data.get("agent_status", "running")
    if not agent_id:
        return jsonify({"ok": False, "error": "agent_id required"}), 400
    conn = pp.get_db()
    conn.execute("UPDATE tasks SET agent_id=?, agent_status=? WHERE id=?",
                 (agent_id, agent_status, task_id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/tasks/<int:task_id>/agent-reply", methods=["POST"])
def api_agent_reply(task_id):
    """Called by the autorun skill when a background agent produces a reply."""
    pp, _ = _get_pp_or_404()
    data = request.get_json(force=True)
    content = data.get("content", "").strip()
    agent_status = data.get("agent_status", "idle")  # 'idle'=waiting for more, 'done'=finished
    if not content:
        return jsonify({"ok": False, "error": "content required"}), 400
    conn = pp.get_db()
    mid = add_task_message(conn, task_id, "agent", content, status="done")
    conn.execute("UPDATE tasks SET agent_status=? WHERE id=?", (agent_status, task_id))
    if agent_status == "done":
        conn.execute("UPDATE tasks SET agent_id=NULL WHERE id=?", (task_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "id": mid})


@app.route("/api/messages/pending", methods=["GET"])
def api_pending_messages():
    """Poll endpoint: returns all pending_send messages across all tasks for this project.
    The autorun /loop poller calls this, then uses SendMessage to forward them to agents.
    """
    pp, _ = _get_pp_or_404()
    conn = pp.get_db()
    msgs = get_pending_messages(conn)
    conn.close()
    return jsonify({"messages": msgs})


@app.route("/api/tasks/<int:task_id>", methods=["GET"])
def api_get_task(task_id):
    """Return task data. ?full=1 returns all fields (for duplication), otherwise lightweight."""
    pp, _ = _get_pp_or_404()
    conn = pp.get_db()
    full = request.args.get("full", "0") == "1"
    if full:
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    else:
        row = conn.execute(
            "SELECT id,status,agent_id,agent_status,started_at,completed_at,duration_minutes,auto_execute,interactive "
            "FROM tasks WHERE id=?", (task_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"ok": False, "error": "Not found"}), 404
    return jsonify(dict(row))


@app.route("/api/tasks/<int:task_id>/log", methods=["POST"])
def api_add_exec_log(task_id):
    """Called by autorun skill (or any agent) to stream execution events into the
    dashboard conversation panel in real time.

    Body: { "event": "phase|agent_start|agent_done|agent_fail|progress|error|review|info",
            "message": "Human-readable log text" }

    Writes a role='system' row to task_messages — frontend polls and renders these
    as coloured timeline pills.
    """
    pp, _ = _get_pp_or_404()
    data = request.get_json(force=True)
    event = data.get("event", "info").strip()
    message = data.get("message", "").strip()
    if not message:
        return jsonify({"ok": False, "error": "message required"}), 400
    valid_events = {"phase", "agent_start", "agent_done", "agent_fail",
                    "progress", "error", "review", "info"}
    if event not in valid_events:
        event = "info"
    content = f"[{event}] {message}"
    conn = pp.get_db()
    task_row = conn.execute("SELECT id FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not task_row:
        conn.close(); abort(404)
    mid = add_task_message(conn, task_id, "system", content, status="done")
    conn.close()
    return jsonify({"ok": True, "id": mid})


@app.route("/api/messages/<int:msg_id>/mark-sent", methods=["POST"])
def api_mark_message_sent(msg_id):
    """Mark a pending_send message as 'sending' to prevent double-dispatch."""
    pp, _ = _get_pp_or_404()
    conn = pp.get_db()
    conn.execute("UPDATE task_messages SET status='sending' WHERE id=? AND status='pending_send'",
                 (msg_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/tasks/<int:task_id>/execute", methods=["POST"])
def api_execute_task(task_id):
    """Manually trigger execution of a task. Works for pending, failed, or orphaned in_progress tasks."""
    pp, _ = _get_pp_or_404()
    pp.ensure_db()
    conn = pp.get_db()
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"ok": False, "error": "Not found"}), 404
    if task_executor.is_running(task_id, pp):
        conn.close()
        return jsonify({"ok": False, "error": "Task is already running"}), 409
    # Allow: pending, failed, completed, or orphaned in_progress (no active process)
    if row["status"] not in ("pending", "failed", "in_progress", "completed"):
        conn.close()
        return jsonify({"ok": False, "error": f"Cannot execute task with status '{row['status']}'"}), 400
    # Update status to in_progress + running
    conn.execute(
        "UPDATE tasks SET status='in_progress', agent_status='running', started_at=?, "
        "completed_at=NULL, duration_minutes=NULL, cost_usd=NULL, conclusion=NULL WHERE id=?",
        (now_str(), task_id))
    conn.commit()
    desc = row["description"]
    config_user = row["config_user"] if "config_user" in row.keys() else None
    model = row["model"] if "model" in row.keys() else None
    effort = row["effort"] if "effort" in row.keys() else None
    conn.close()
    started = task_executor.start_task(task_id, pp, desc, config_user=config_user, model=model, effort=effort)
    return jsonify({"ok": True, "started": started})


@app.route("/api/tasks/<int:task_id>/resume", methods=["POST"])
def api_resume_task(task_id):
    """Resume a failed or completed task using the same session.

    Works for:
    - failed tasks (e.g. after budget increase, or to continue after error)
    - completed tasks (e.g. interactive task wrongly marked as done, or
      user wants to continue the conversation)
    """
    pp, _ = _get_pp_or_404()
    pp.ensure_db()
    data = request.get_json(force=True) if request.is_json else {}
    conn = pp.get_db()
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"ok": False, "error": "Not found"}), 404
    if row["status"] not in ("failed", "completed"):
        conn.close()
        return jsonify({"ok": False, "error": "Only failed or completed tasks can be resumed"}), 400
    # Clean up stale thread registry
    with task_executor._lock:
        task_executor._threads.pop(task_id, None)

    session_id = row["session_id"] if "session_id" in row.keys() else None
    if not session_id:
        conn.close()
        return jsonify({"ok": False, "error": "No session to resume (task was not executed via autorun)"}), 400

    # Optionally update max_cost_usd
    if "max_cost_usd" in data:
        new_cost = float(data["max_cost_usd"])
        conn.execute("UPDATE tasks SET max_cost_usd=? WHERE id=?", (new_cost, task_id))

    # Determine if this is an interactive task
    is_interactive = bool(row["interactive"]) if "interactive" in row.keys() else False

    if is_interactive:
        # Interactive mode: just set back to in_progress/idle.
        # Don't launch CC yet — wait for user to send a message,
        # which will trigger auto-resume via api_post_message.
        conn.execute(
            "UPDATE tasks SET status='in_progress', agent_status='idle', "
            "completed_at=NULL, duration_minutes=NULL, conclusion=NULL WHERE id=?",
            (task_id,))
        conn.commit()
        conn.close()
        task_executor._log(pp, task_id, "info", "💬 会话已恢复，等待你的消息…")
        return jsonify({"ok": True, "started": False, "resumed_session": session_id,
                        "interactive": True})
    else:
        # Non-interactive: launch CC immediately with resume prompt
        conn.execute(
            "UPDATE tasks SET status='in_progress', agent_status='running', "
            "completed_at=NULL, duration_minutes=NULL, conclusion=NULL WHERE id=?",
            (task_id,))
        conn.commit()

        desc = row["description"]
        config_user = row["config_user"] if "config_user" in row.keys() else None
        model = row["model"] if "model" in row.keys() else None
        effort = row["effort"] if "effort" in row.keys() else None
        conn.close()

        resume_prompt = f"请继续完成之前的任务（之前因成本超限或错误被中断）。任务描述：{desc}"
        started = task_executor.start_task(task_id, pp, resume_prompt,
                                            config_user=config_user, model=model,
                                            effort=effort, resume_session_id=session_id)
        return jsonify({"ok": True, "started": started, "resumed_session": session_id,
                        "interactive": False})


@app.route("/api/tasks/<int:task_id>/stop", methods=["POST"])
def api_stop_task(task_id):
    """Stop a running Claude Code process for a task."""
    pp, _ = _get_pp_or_404()
    pp.ensure_db()
    if not task_executor.is_running(task_id, pp):
        return jsonify({"ok": False, "error": "Task is not running"}), 404
    stopped = task_executor.stop_task(task_id, pp)
    if stopped:
        conn = pp.get_db()
        add_task_message(conn, task_id, "system", "[info] ⏹️ 用户手动终止托管执行", status="done")
        conn.execute("UPDATE tasks SET status='failed' WHERE id=?", (task_id,))
        conn.commit()
        conn.close()
    return jsonify({"ok": True, "stopped": stopped})


@app.route("/api/tasks/<int:task_id>/execution-status", methods=["GET"])
def api_execution_status(task_id):
    """Real-time execution status for the task detail page status bar.

    Returns process liveness, JSONL activity, cost, and timing info
    so the UI can show whether CC is actively working, waiting for API,
    or stalled.
    """
    pp, _ = _get_pp_or_404()
    running = task_executor.is_running(task_id, pp)
    orphan = False
    pid = None
    info = task_executor._read_pid(pp, task_id)
    if info is not None:
        pid = info.get("pid")
        if pid is not None and not task_executor._pid_alive(pid):
            orphan = True
            pid = None  # dead

    # JSONL last-modified time (indicates CC is actively writing)
    jsonl_mtime = None
    jsonl_age_s = None
    try:
        conn = pp.get_db()
        row = conn.execute("SELECT session_id, status, agent_status, interactive, "
                           "estimated_cost_usd, max_cost_usd, started_at, model "
                           "FROM tasks WHERE id=?", (task_id,)).fetchone()
        conn.close()
        if row and row["session_id"]:
            import re as _re
            proj_slug = _re.sub(r'[^a-zA-Z0-9]', '-', str(pp.root))
            jsonl_path = Path.home() / ".claude-internal" / "projects" / proj_slug / f"{row['session_id']}.jsonl"
            if jsonl_path.exists():
                import time as _t
                mt = jsonl_path.stat().st_mtime
                jsonl_mtime = _t.strftime("%H:%M:%S", _t.localtime(mt))
                jsonl_age_s = round(_t.time() - mt)
    except Exception:
        row = None

    result = {
        "ok": True, "running": running, "orphan": orphan, "task_id": task_id,
        "pid": pid if running else None,
        "jsonl_last_activity": jsonl_mtime,
        "jsonl_age_seconds": jsonl_age_s,
        "status": row["status"] if row else None,
        "agent_status": row["agent_status"] if row else None,
        "interactive": bool(row["interactive"]) if row else False,
        "cost_usd": round(float(row["estimated_cost_usd"] or 0), 4) if row else 0,
        "max_cost_usd": float(row["max_cost_usd"] or 5) if row else 5,
        "model": row["model"] if row else None,
        "started_at": row["started_at"] if row else None,
    }
    return jsonify(result)


# ═══════════════════════════════════════════════════════════════════════════
# API — Claude Code Config (read from env + settings files)
# ═══════════════════════════════════════════════════════════════════════════

def _read_claude_config():
    """Collect Claude Code runtime configuration from env vars and settings files."""
    cfg = {}

    # Models from env
    cfg["model_sonnet"] = os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL", "")
    cfg["model_opus"]   = os.environ.get("ANTHROPIC_DEFAULT_OPUS_MODEL", "")
    cfg["model_haiku"]  = os.environ.get("ANTHROPIC_DEFAULT_HAIKU_MODEL", "")
    cfg["base_url"]     = os.environ.get("ANTHROPIC_BASE_URL", "")

    # Entrypoint / mode
    cfg["entrypoint"]   = os.environ.get("CLAUDE_CODE_ENTRYPOINT", "")
    cfg["is_internal"]  = bool(os.environ.get("CLAUDE_CODE_TEAMMATE_COMMAND"))

    # Version: extract from node path in teammate command
    teammate = os.environ.get("CLAUDE_CODE_TEAMMATE_COMMAND", "")
    m = re.search(r'node/(v[\d.]+)', teammate)
    cfg["version"] = m.group(1) if m else cfg["entrypoint"]

    # Settings files (global)
    settings_dir = Path(os.environ.get("CLAUDE_SETTINGS_DIR",
                         os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))))
    cfg["settings_dir"] = str(settings_dir)

    global_settings = {}
    for fname in ["settings.json", "settings.local.json"]:
        p = settings_dir / fname
        if p.exists():
            try:
                global_settings.update(json.loads(p.read_text()))
            except Exception:
                pass
    cfg["global_settings"] = global_settings

    # Extract commonly used fields
    cfg["model_override"]  = global_settings.get("model", "")
    cfg["theme"]           = global_settings.get("theme", "")
    cfg["notify"]          = global_settings.get("notify", None)
    cfg["max_thinking"]    = global_settings.get("maxThinkingTokens", None)
    cfg["small_fast_llm"]  = global_settings.get("smallFastLLM", "")

    # Active model: settings.json "model" field wins over env default
    cfg["active_model"] = cfg["model_override"] or cfg["model_sonnet"] or cfg["model_opus"] or "unknown"

    # Permissions summary
    permissions = global_settings.get("permissions", {})
    cfg["allow_list"] = permissions.get("allow", [])
    cfg["deny_list"]  = permissions.get("deny", [])

    # Hooks
    cfg["hooks"] = global_settings.get("hooks", {})

    # Active sessions (running instances)
    instances_dir = settings_dir / "runtime" / "instances"
    cfg["active_sessions"] = []
    if instances_dir.is_dir():
        try:
            for f in sorted(instances_dir.iterdir()):
                if f.suffix == ".json":
                    try:
                        cfg["active_sessions"].append(json.loads(f.read_text()))
                    except Exception:
                        pass
        except Exception:
            pass

    # Per-project settings
    projects_info = []
    projects_base = settings_dir / "projects"
    for proj in get_registered_projects():
        ppath = Path(proj["path"])
        import re as _re
        folder_name = _re.sub(r'[^a-zA-Z0-9]', '-', str(ppath))
        proj_settings = {}
        for candidate in [projects_base / folder_name, ppath / ".claude"]:
            for fname in ["settings.json", "settings.local.json"]:
                sp = candidate / fname
                if sp.exists():
                    try:
                        proj_settings.update(json.loads(sp.read_text()))
                    except Exception:
                        pass
        projects_info.append({"slug": proj["slug"], "name": proj["name"],
                               "path": proj["path"], "settings": proj_settings})
    cfg["projects"] = projects_info

    return cfg


@app.route("/api/claude-config")
def api_claude_config():
    return jsonify(_read_claude_config())


@app.route("/api/claude-config", methods=["PUT"])
def api_update_claude_config():
    """Update a Claude Code setting (writes to global settings.json)."""
    data = request.get_json(force=True)
    settings_dir = Path(os.environ.get("CLAUDE_SETTINGS_DIR",
                         os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))))
    settings_file = settings_dir / "settings.json"
    # Load existing
    try:
        current = json.loads(settings_file.read_text()) if settings_file.exists() else {}
    except Exception:
        current = {}
    # Apply updates — only allow safe keys
    allowed_keys = {"model", "theme", "smallFastLLM", "maxThinkingTokens",
                    "notify", "permissions"}
    updates = {k: v for k, v in data.items() if k in allowed_keys}
    if not updates:
        return jsonify({"ok": False, "error": "No valid keys to update"}), 400
    current.update(updates)
    try:
        settings_dir.mkdir(parents=True, exist_ok=True)
        settings_file.write_text(json.dumps(current, indent=2, ensure_ascii=False))
        return jsonify({"ok": True, "written": list(updates.keys())})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/taiji-token", methods=["GET"])
def api_get_taiji_token():
    token = get_taiji_token()
    # Mask for display: show first 4 and last 4 chars
    masked = ""
    if token:
        if len(token) > 10:
            masked = token[:4] + "***" + token[-4:]
        else:
            masked = "***"
    return jsonify({"ok": True, "has_token": bool(token), "masked": masked})


@app.route("/api/taiji-token", methods=["PUT"])
def api_set_taiji_token():
    data = request.get_json(force=True)
    token = data.get("token", "").strip()
    if not token:
        return jsonify({"ok": False, "error": "Token is required"}), 400
    set_taiji_token(token)
    return jsonify({"ok": True})


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def find_project_root_from_cwd():
    cwd = Path.cwd()
    for p in [cwd] + list(cwd.parents):
        if (p / ".claude").is_dir() or (p / ".git").is_dir():
            return p
    return cwd


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TODO Dashboard (multi-project)")
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--project", nargs="*", default=None,
                        help="Project root(s) to register. Default: auto-detect from cwd.")
    args = parser.parse_args()

    # Register initial project(s)
    if args.project:
        for p in args.project:
            ok, msg = register_project(p)
            if ok:
                pp = ProjectPaths(p)
                pp.ensure_db()
    else:
        # Auto-detect from cwd
        root = find_project_root_from_cwd()
        ok, msg = register_project(root)
        if ok:
            pp = ProjectPaths(root)
            pp.ensure_db()

    import socket
    try: ip = socket.gethostbyname(socket.gethostname())
    except Exception: ip = "0.0.0.0"

    projects = get_registered_projects()
    print(f"🚀 Orbit Dashboard (multi-project)")
    print(f"   http://{ip}:{args.port}")
    print(f"   Registered projects ({len(projects)}):")
    for p in projects:
        print(f"     [{p['slug']}] {p['path']}")

    # Load Taiji token into env on startup
    _taiji_tok = get_taiji_token()
    if _taiji_tok:
        os.environ["TOKEN"] = _taiji_tok
        print(f"   Taiji token: loaded ({_taiji_tok[:4]}***)")
    else:
        print("   Taiji token: not set")

    # Recover tasks whose processes survived a server restart
    print("   Recovering tasks...")
    task_executor.recover_tasks()

    # threaded=True: frontend polls /api/stats every ~5s with 6 concurrent requests;
    # serial Flask would queue them and multiply dop-fuse latency.
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)

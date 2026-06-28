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
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

from flask import Flask, render_template, request, jsonify, abort, redirect, url_for

SCRIPT_DIR = Path(__file__).resolve().parent
TASK_MANAGER = SCRIPT_DIR / "task_manager.py"
META_DIR = Path.home() / ".claude-dashboard"
PROJECTS_FILE = META_DIR / "projects.json"

app = Flask(__name__, template_folder=str(SCRIPT_DIR / "templates"))


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
    """All paths for a given project, computed on the fly."""
    def __init__(self, root_str):
        self.root = Path(root_str).resolve()
        self.name = self.root.name
        self.db = self.root / ".claude" / "autorun-tasks.db"
        self.skills_dir = self.root / ".claude" / "skills"
        self.todo_file = self.root / "TODO_LIST.md"
        self.context_file = self.root / ".claude" / "project_context.md"

    def ensure_db(self):
        self.db.parent.mkdir(parents=True, exist_ok=True)
        conn = self.get_db()
        conn.executescript(_CREATE_TABLES_SQL)
        # Migration for older schemas
        for col in ("skill", "project_path"):
            try:
                conn.execute(f"SELECT {col} FROM tasks LIMIT 1")
            except sqlite3.OperationalError:
                conn.execute(f"ALTER TABLE tasks ADD COLUMN {col} TEXT")
        conn.commit()
        conn.close()

    def get_db(self):
        conn = sqlite3.connect(str(self.db))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
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
    project_path    TEXT
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
"""


def _get_pp():
    """Get ProjectPaths for the current request's ?p= parameter."""
    slug = request.args.get("p") or request.form.get("p")
    if not slug:
        # Try cookie
        slug = request.cookies.get("last_project")
    if slug:
        proj = find_project_by_slug(slug)
        if proj:
            return ProjectPaths(proj["path"]), slug
    # Fallback: first registered project
    projects = get_registered_projects()
    if projects:
        return ProjectPaths(projects[0]["path"]), projects[0]["slug"]
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
# Skill discovery
# ═══════════════════════════════════════════════════════════════════════════

_skills_cache = {}  # keyed by project path


def scan_skills(skills_dir):
    skills = []
    if not skills_dir.is_dir():
        return skills
    for d in sorted(skills_dir.iterdir()):
        if not d.is_dir(): continue
        md = d / "SKILL.md"
        if not md.exists(): continue
        info = {"name": d.name, "description": "", "short_desc": d.name}
        try:
            text = md.read_text(encoding="utf-8", errors="replace")
            fm_m = re.match(r'^---\s*\n(.*?)\n---', text, re.DOTALL)
            if fm_m:
                fm = yaml.safe_load(fm_m.group(1))
                if isinstance(fm, dict):
                    info["description"] = fm.get("description", "").strip()
                    info["short_desc"] = info["description"].split("\n")[0][:120]
        except Exception:
            pass
        skills.append(info)
    return skills


def get_skills(pp):
    key = str(pp.root)
    if key not in _skills_cache:
        _skills_cache[key] = scan_skills(pp.skills_dir)
    return _skills_cache[key]


def parse_skill_input(text, pp):
    m = re.match(r'^/(\S+)\s*(.*)', text.strip())
    if m:
        name = m.group(1)
        known = {s["name"] for s in get_skills(pp)}
        if name in known:
            return name, m.group(2).strip() or f"执行 /{name}", name
    return None, text.strip(), None


# ═══════════════════════════════════════════════════════════════════════════
# Context file helpers
# ═══════════════════════════════════════════════════════════════════════════

def read_context(pp):
    if pp.context_file.exists():
        return pp.context_file.read_text(encoding="utf-8")
    return ""


def write_context(pp, content):
    pp.context_file.parent.mkdir(parents=True, exist_ok=True)
    pp.context_file.write_text(content, encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════
# Common template context
# ═══════════════════════════════════════════════════════════════════════════

def _base_ctx(pp, slug):
    """Common variables injected into every template."""
    return {
        "project_root": str(pp.root),
        "project_name": pp.name,
        "project_slug": slug,
        "all_projects": get_registered_projects(),
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
    conn = pp.get_db()
    counts = get_counts(conn)
    tasks = get_tasks(conn, status_filter)
    for t in tasks:
        t["_is_blocked"] = len(check_blocked(conn, t["id"])) > 0
        t["_has_active_conflict"] = len(check_conflicts_active(conn, t["id"])) > 0
    relations = get_all_relations(conn)
    ctx_entries = get_context_log(conn, limit=10)
    conn.close()

    resp = app.make_response(render_template("index.html",
        tasks=tasks, counts=counts, current_filter=status_filter,
        todo_file_exists=pp.todo_file.exists(), relations=relations,
        skills=get_skills(pp), context_entries=ctx_entries,
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
    all_tasks = [row_to_dict(r) for r in conn.execute(
        "SELECT id,description,tag,status FROM tasks WHERE id!=? ORDER BY position ASC", (task_id,)).fetchall()]
    conn.close()
    return render_template("detail.html",
        task=task, parent=parent, subtasks=subs, relations=rels,
        blockers=blockers, conflicts_active=conflicts, all_tasks=all_tasks,
        task_context=task_ctx, skills=get_skills(pp),
        **_base_ctx(pp, slug))


@app.route("/skills")
def skills_page():
    pp, slug = _get_pp_or_404()
    return render_template("skills.html", skills=get_skills(pp), **_base_ctx(pp, slug))


@app.route("/context")
def context_page():
    pp, slug = _get_pp_or_404()
    conn = pp.get_db()
    entries = get_context_log(conn, limit=200)
    conn.close()
    return render_template("context.html", entries=entries, context_md=read_context(pp),
                           **_base_ctx(pp, slug))


# ═══════════════════════════════════════════════════════════════════════════
# API — Projects
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/projects", methods=["GET"])
def api_list_projects():
    projects = get_registered_projects()
    # Annotate with task counts
    for proj in projects:
        pp = ProjectPaths(proj["path"])
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
        # Ensure DB exists for the new project
        pp = ProjectPaths(path)
        pp.ensure_db()
        return jsonify({"ok": True, "slug": msg if msg != "已注册" else _project_slug(path)})
    return jsonify({"ok": False, "error": msg}), 400


@app.route("/api/projects/<slug>", methods=["DELETE"])
def api_remove_project(slug):
    unregister_project(slug)
    return jsonify({"ok": True})


# ═══════════════════════════════════════════════════════════════════════════
# API — Tasks (all project-scoped via ?p=slug)
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/stats")
def api_stats():
    pp, slug = _get_pp_or_404()
    status_filter = request.args.get("status", "all")
    conn = pp.get_db()
    counts = get_counts(conn)
    tasks = get_tasks(conn, status_filter)
    for t in tasks:
        t["_is_blocked"] = len(check_blocked(conn, t["id"])) > 0
        t["_has_active_conflict"] = len(check_conflicts_active(conn, t["id"])) > 0
    rels = get_all_relations(conn)
    conn.close()
    return jsonify({"counts": counts, "tasks": tasks, "relations": rels, "project": slug})


@app.route("/api/tasks", methods=["POST"])
def api_create_task():
    pp, slug = _get_pp_or_404()
    data = request.get_json(force=True)
    raw = data.get("description", "").strip()
    tag = data.get("tag", "").strip() or None
    if not raw:
        return jsonify({"ok": False, "error": "Description is required"}), 400
    skill_name, desc, skill_tag = parse_skill_input(raw, pp)
    if skill_tag and not tag:
        tag = skill_tag
    conn = pp.get_db()
    row = conn.execute("SELECT MAX(position) as mp FROM tasks").fetchone()
    mx = row["mp"] if row["mp"] is not None else 0.0
    cur = conn.execute(
        "INSERT INTO tasks (description,tag,status,position,created_at,skill,project_path) VALUES (?,?,'pending',?,?,?,?)",
        (desc, tag, mx + 1.0, now_str(), skill_name, str(pp.root)))
    conn.commit()
    tid = cur.lastrowid
    conn.close()
    return jsonify({"ok": True, "id": tid, "skill": skill_name})


@app.route("/api/tasks/<int:task_id>", methods=["PUT"])
def api_update_task(task_id):
    pp, _ = _get_pp_or_404()
    data = request.get_json(force=True)
    conn = pp.get_db()
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"ok": False, "error": "Not found"}), 404
    allowed = ["description", "tag", "notes", "conclusion", "skill"]
    updates, values, warnings = [], [], []
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


@app.route("/api/tasks/<int:task_id>/retry", methods=["POST"])
def api_retry_task(task_id):
    pp, _ = _get_pp_or_404()
    conn = pp.get_db()
    conn.execute("UPDATE tasks SET status='pending',started_at=NULL,completed_at=NULL,"
                 "duration_minutes=NULL,notes=NULL WHERE id=?", (task_id,))
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
    print(f"🚀 TODO Dashboard (multi-project)")
    print(f"   http://{ip}:{args.port}")
    print(f"   Registered projects ({len(projects)}):")
    for p in projects:
        print(f"     [{p['slug']}] {p['path']}")
    app.run(host=args.host, port=args.port, debug=args.debug)

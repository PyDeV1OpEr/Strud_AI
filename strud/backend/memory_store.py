# memory_store.py
#
# Strud AI — persistent memory layer (SQLite via stdlib sqlite3).
#
# Three-layer memory solution:
#   A. conversations      — chat history, durable across backend restarts
#   B. user_memory        — cross-chat facts and study preferences (user-scoped)
#   C. quiz_sessions/attempts — structured quiz scoring, never LLM-recalled
#   D. projects/profile   — sidebar projects and per-user display profile
#
# Isolation rule: user_id is ALWAYS part of the lookup key, so one
# user's memory can never be served to another user's session.
# Anonymous frontend users get a stable per-browser user_id ("local").

from __future__ import annotations

import calendar
import json
import sqlite3
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = ZoneInfo("Asia/Colombo")

_TABLES = [
    """CREATE TABLE IF NOT EXISTS chats (
        user_id TEXT NOT NULL,
        chat_id TEXT NOT NULL,
        title TEXT NOT NULL DEFAULT 'New chat',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (user_id, chat_id)
    )""",
    # --- D) projects and profile ---------------------------------
    """CREATE TABLE IF NOT EXISTS projects (
        user_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (user_id, project_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_projects_user ON projects (user_id, updated_at)",
    """CREATE TABLE IF NOT EXISTS profiles (
        user_id TEXT PRIMARY KEY,
        display_name TEXT NOT NULL DEFAULT 'Student',
        avatar TEXT NOT NULL DEFAULT 'emerald',
        response_style TEXT NOT NULL DEFAULT 'balanced',
        explanation_detail TEXT NOT NULL DEFAULT 'standard',
        study_focus TEXT NOT NULL DEFAULT 'exam',
        memory_enabled INTEGER NOT NULL DEFAULT 1,
        custom_instructions TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    # --- A) per-conversation message history -------------------
    """CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        chat_id TEXT NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
        content TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_chat_user ON conversations (chat_id, user_id)",
    "CREATE INDEX IF NOT EXISTS idx_chat_order ON conversations (chat_id, id)",

    # --- B) user-level memory (cross-chat) --------------------
    """CREATE TABLE IF NOT EXISTS user_memory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        content TEXT NOT NULL,
        source TEXT NOT NULL DEFAULT 'conversation',  -- 'explicit' | 'conversation' | 'corrected'
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE (user_id, content)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_memory_user ON user_memory (user_id, id)",

    # --- C) structured quiz state -----------------------------
    """CREATE TABLE IF NOT EXISTS quiz_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        quiz_id TEXT NOT NULL UNIQUE,          -- UUID per quiz session
        chat_id TEXT NOT NULL,                 -- chat that started it
        topic TEXT NOT NULL DEFAULT '',
        question_count INTEGER NOT NULL DEFAULT 0,
        correct_count INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'completed', 'abandoned')),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_quiz_user_chat ON quiz_sessions (user_id, chat_id, status)",
    """CREATE TABLE IF NOT EXISTS quiz_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        quiz_id TEXT NOT NULL,
        chat_id TEXT NOT NULL,
        question_id TEXT NOT NULL,
        question_text TEXT NOT NULL,
        options_json TEXT NOT NULL DEFAULT '{}',
        correct_answer TEXT NOT NULL,
        submitted_answer TEXT NOT NULL,
        is_correct INTEGER NOT NULL,
        points_awarded REAL NOT NULL DEFAULT 1.0,
        max_points REAL NOT NULL DEFAULT 1.0,
        attempt_status TEXT NOT NULL DEFAULT 'answered',  -- answered | skipped | pending | corrected | retracted
        created_at TEXT NOT NULL,
        UNIQUE (quiz_id, question_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_attempts_quiz ON quiz_attempts (user_id, quiz_id)",

    # --- F) AI usage and analytics ----------------------------
    """CREATE TABLE IF NOT EXISTS ai_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        chat_id TEXT,
        model_id TEXT NOT NULL,
        input_tokens INTEGER NOT NULL DEFAULT 0,
        output_tokens INTEGER NOT NULL DEFAULT 0,
        total_tokens INTEGER NOT NULL DEFAULT 0,
        token_counting_method TEXT NOT NULL DEFAULT 'provider',  -- 'provider' | 'tiktoken_cl100k' | 'estimated' | 'unavailable'
        request_status TEXT NOT NULL DEFAULT 'success',          -- 'success' | 'failed'
        duration_ms INTEGER,
        created_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_usage_user_date ON ai_usage (user_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_usage_chat ON ai_usage (chat_id)",
]

_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    # Foreign keys aren't strictly needed (schema has no FKs), but
    # enabling them is harmless and future-proof.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ============================================================
# MEMORY STORE
# ============================================================

class MemoryStore:
    """
    One persistent SQLite store backing all three memory layers.

    Instantiated ONCE by the FastAPI app and shared by every chat
    session. Single-writer per thread via a process-level lock —
    FastAPI runs sync routes on the CLI pipeline which is already
    serialized behind _app_lock, so this doesn't deadlock. Each
    operation opens a fresh connection in a short transaction, so
    failures never wedge the store.
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self._init_schema()

    def _init_schema(self) -> None:
        with _LOCK, self._conn() as conn:
            for stmt in _TABLES:
                conn.execute(stmt)
            # SQLite migrations for installations created before attachments.
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(conversations)")}
            if "attachments_json" not in columns:
                conn.execute(
                    "ALTER TABLE conversations ADD COLUMN attachments_json TEXT NOT NULL DEFAULT '[]'"
                )
            chat_columns = {row["name"] for row in conn.execute("PRAGMA table_info(chats)")}
            if "deleted_at" not in chat_columns:
                conn.execute("ALTER TABLE chats ADD COLUMN deleted_at TEXT")
            if "project_id" not in chat_columns:
                conn.execute("ALTER TABLE chats ADD COLUMN project_id TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chats_deleted ON chats (user_id, deleted_at, updated_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_chats_project ON chats (user_id, project_id, updated_at)")
            # Preserve conversations created before chat metadata existed.
            conn.execute(
                "INSERT OR IGNORE INTO chats (user_id, chat_id, title, created_at, updated_at) "
                "SELECT user_id, chat_id, 'New chat', MIN(created_at), MAX(created_at) "
                "FROM conversations GROUP BY user_id, chat_id"
            )
            # Profile personalization columns migration
            profile_columns = {row["name"] for row in conn.execute("PRAGMA table_info(profiles)")}
            if "avatar" not in profile_columns:
                conn.execute("ALTER TABLE profiles ADD COLUMN avatar TEXT NOT NULL DEFAULT 'emerald'")
            if "response_style" not in profile_columns:
                conn.execute("ALTER TABLE profiles ADD COLUMN response_style TEXT NOT NULL DEFAULT 'balanced'")
            if "explanation_detail" not in profile_columns:
                conn.execute("ALTER TABLE profiles ADD COLUMN explanation_detail TEXT NOT NULL DEFAULT 'standard'")
            if "study_focus" not in profile_columns:
                conn.execute("ALTER TABLE profiles ADD COLUMN study_focus TEXT NOT NULL DEFAULT 'exam'")
            if "memory_enabled" not in profile_columns:
                conn.execute("ALTER TABLE profiles ADD COLUMN memory_enabled INTEGER NOT NULL DEFAULT 1")
            if "custom_instructions" not in profile_columns:
                conn.execute("ALTER TABLE profiles ADD COLUMN custom_instructions TEXT NOT NULL DEFAULT ''")

    def _conn(self) -> sqlite3.Connection:
        return _connect(self.db_path)

    # --------------------------------------------------------
    # A) CONVERSATIONS
    # --------------------------------------------------------

    def append_message(
        self,
        chat_id: str,
        user_id: str,
        role: str,
        content: str,
        attachments: Optional[list[dict]] = None,
    ) -> int:
        with _LOCK, self._conn() as conn:
            cursor = conn.execute(
                "INSERT INTO conversations (user_id, chat_id, role, content, attachments_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, chat_id, role, (content or "").strip(), json.dumps(attachments or []), _now()),
            )
            return cursor.lastrowid or 0

    def get_history(
        self,
        chat_id: str,
        user_id: str,
        limit: int = 200,
    ) -> list[dict]:
        with _LOCK, self._conn() as conn:
            rows = conn.execute(
                "SELECT role, content, attachments_json, created_at FROM conversations "
                "WHERE chat_id = ? AND user_id = ? ORDER BY id DESC LIMIT ?",
                (chat_id, user_id, limit),
            ).fetchall()
        rows.reverse()
        return [
            {"role": r["role"], "content": r["content"], "attachments": json.loads(r["attachments_json"] or "[]"), "created_at": r["created_at"]}
            for r in rows
        ]

    def ensure_chat(
        self,
        chat_id: str,
        user_id: str,
        title: str = "",
        project_id: Optional[str] = None,
    ) -> None:
        """Create chat metadata once; never replace a meaningful title or project."""
        now = _now()
        fallback = ((title or "New chat").strip() or "New chat")[:80]
        resolved_project = (project_id or None)  # empty string means unassigned
        with _LOCK, self._conn() as conn:
            conn.execute(
                "INSERT INTO chats (user_id, chat_id, title, project_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(user_id, chat_id) DO UPDATE SET updated_at = excluded.updated_at, "
                "title = CASE WHEN chats.title IN ('', 'New chat', 'New Chat', 'Untitled') "
                "AND excluded.title NOT IN ('', 'New chat', 'New Chat', 'Untitled') THEN excluded.title ELSE chats.title END",
                (user_id, chat_id, fallback, resolved_project, now, now),
            )

    def update_chat_title(self, chat_id: str, user_id: str, title: str) -> None:
        title = (title or "").strip()[:80]
        if not title:
            return
        self.ensure_chat(chat_id, user_id, title)
        with _LOCK, self._conn() as conn:
            conn.execute("UPDATE chats SET title = ?, updated_at = ? WHERE user_id = ? AND chat_id = ?", (title, _now(), user_id, chat_id))

    def list_chats(self, user_id: str, deleted: bool = False) -> list[dict]:
        with _LOCK, self._conn() as conn:
            rows = conn.execute(
                "SELECT chat_id, title, project_id, created_at, updated_at, deleted_at FROM chats "
                "WHERE user_id = ? AND deleted_at IS " + ("NOT NULL" if deleted else "NULL") + " "
                "ORDER BY " + ("deleted_at DESC" if deleted else "updated_at DESC"),
                (user_id,),
            ).fetchall()
        result = []
        for row in rows:
            result.append({**dict(row), "messages": self.get_history(row["chat_id"], user_id)})
        return result

    def is_chat_deleted(self, chat_id: str, user_id: str) -> bool:
        with _LOCK, self._conn() as conn:
            row = conn.execute("SELECT deleted_at FROM chats WHERE user_id = ? AND chat_id = ?", (user_id, chat_id)).fetchone()
        return row is not None and row["deleted_at"] is not None

    def move_chat_to_bin(self, chat_id: str, user_id: str) -> bool:
        with _LOCK, self._conn() as conn:
            cursor = conn.execute(
                "UPDATE chats SET deleted_at = ?, updated_at = ? WHERE user_id = ? AND chat_id = ? AND deleted_at IS NULL",
                (_now(), _now(), user_id, chat_id),
            )
            return cursor.rowcount > 0

    def restore_chat(self, chat_id: str, user_id: str) -> bool:
        with _LOCK, self._conn() as conn:
            cursor = conn.execute(
                "UPDATE chats SET deleted_at = NULL, updated_at = ? WHERE user_id = ? AND chat_id = ? AND deleted_at IS NOT NULL",
                (_now(), user_id, chat_id),
            )
            return cursor.rowcount > 0

    def permanently_delete_chat(self, chat_id: str, user_id: str) -> list[dict] | None:
        """Remove a bin item and return its owned attachment references."""
        with _LOCK, self._conn() as conn:
            row = conn.execute("SELECT 1 FROM chats WHERE user_id = ? AND chat_id = ? AND deleted_at IS NOT NULL", (user_id, chat_id)).fetchone()
            if row is None:
                return None
            rows = conn.execute("SELECT attachments_json FROM conversations WHERE user_id = ? AND chat_id = ?", (user_id, chat_id)).fetchall()
            attachments = [item for row in rows for item in json.loads(row["attachments_json"] or "[]")]
            conn.execute("DELETE FROM conversations WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
            conn.execute("DELETE FROM chats WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
            return attachments

    def empty_bin(self, user_id: str) -> list[dict]:
        attachments: list[dict] = []
        for chat in self.list_chats(user_id, deleted=True):
            attachments.extend(self.permanently_delete_chat(chat["chat_id"], user_id) or [])
        return attachments

    def set_chat_project(self, chat_id: str, user_id: str, project_id: Optional[str]) -> bool:
        """Move one chat into a project (or out, with project_id=None)."""
        with _LOCK, self._conn() as conn:
            cursor = conn.execute(
                "UPDATE chats SET project_id = ?, updated_at = ? "
                "WHERE user_id = ? AND chat_id = ? AND deleted_at IS NULL",
                (project_id or None, _now(), user_id, chat_id),
            )
            return cursor.rowcount > 0

    # --------------------------------------------------------
    # D) PROJECTS
    # --------------------------------------------------------

    def create_project(self, user_id: str, name: str, description: str = "") -> Optional[dict]:
        name = (name or "").strip()[:80]
        if not name:
            return None
        project_id = str(uuid.uuid4())
        now = _now()
        with _LOCK, self._conn() as conn:
            conn.execute(
                "INSERT INTO projects (user_id, project_id, name, description, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, project_id, name, (description or "").strip()[:500], now, now),
            )
        return {"project_id": project_id, "name": name, "description": (description or "").strip()[:500], "created_at": now, "updated_at": now}

    def list_projects(self, user_id: str) -> list[dict]:
        """All projects for a user, newest first, with durable chat counts."""
        with _LOCK, self._conn() as conn:
            rows = conn.execute(
                "SELECT project_id, name, description, created_at, updated_at FROM projects "
                "WHERE user_id = ? ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
            counts: dict[str, int] = {}
            for chat in conn.execute(
                "SELECT project_id, COUNT(*) AS n FROM chats "
                "WHERE user_id = ? AND project_id IS NOT NULL AND deleted_at IS NULL GROUP BY project_id",
                (user_id,),
            ).fetchall():
                counts[chat["project_id"]] = int(chat["n"])
        return [
            {**dict(row), "chat_count": counts.get(row["project_id"], 0)}
            for row in rows
        ]

    def project_exists(self, user_id: str, project_id: str) -> bool:
        with _LOCK, self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM projects WHERE user_id = ? AND project_id = ?",
                (user_id, project_id),
            ).fetchone()
        return row is not None

    def update_project(self, user_id: str, project_id: str, name: str, description: str) -> bool:
        name = (name or "").strip()[:80]
        if not name:
            return False
        with _LOCK, self._conn() as conn:
            cursor = conn.execute(
                "UPDATE projects SET name = ?, description = ?, updated_at = ? "
                "WHERE user_id = ? AND project_id = ?",
                (name, (description or "").strip()[:500], _now(), user_id, project_id),
            )
            return cursor.rowcount > 0

    def delete_project(self, user_id: str, project_id: str) -> int:
        """Remove the project and unassign its chats (they become ordinary)."""
        with _LOCK, self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM projects WHERE user_id = ? AND project_id = ?",
                (user_id, project_id),
            ).fetchone()
            if row is None:
                return -1
            unassigned = conn.execute(
                "UPDATE chats SET project_id = NULL, updated_at = ? WHERE user_id = ? AND project_id = ?",
                (_now(), user_id, project_id),
            )
            conn.execute(
                "DELETE FROM projects WHERE user_id = ? AND project_id = ?",
                (user_id, project_id),
            )
            return unassigned.rowcount

    # --------------------------------------------------------
    # E) PROFILE
    # --------------------------------------------------------

    def get_profile(self, user_id: str) -> dict:
        with _LOCK, self._conn() as conn:
            row = conn.execute(
                "SELECT display_name, avatar, response_style, explanation_detail, "
                "study_focus, memory_enabled, custom_instructions, created_at, updated_at "
                "FROM profiles WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if row is None:
            return {
                "display_name": "Student",
                "avatar": "emerald",
                "response_style": "balanced",
                "explanation_detail": "standard",
                "study_focus": "exam",
                "memory_enabled": True,
                "custom_instructions": "",
            }
        data = dict(row)
        data["memory_enabled"] = bool(data.get("memory_enabled", 1))
        return data

    def set_profile(
        self,
        user_id: str,
        display_name: str,
        avatar: Optional[str] = None,
        response_style: Optional[str] = None,
        explanation_detail: Optional[str] = None,
        study_focus: Optional[str] = None,
        memory_enabled: Optional[bool] = None,
        custom_instructions: Optional[str] = None,
    ) -> dict:
        current = self.get_profile(user_id)
        name = (display_name or "").strip()[:60] or current["display_name"]
        res_avatar = str(avatar)[:40] if avatar is not None else current.get("avatar", "emerald")
        res_style = str(response_style)[:40] if response_style is not None else current.get("response_style", "balanced")
        res_detail = str(explanation_detail)[:40] if explanation_detail is not None else current.get("explanation_detail", "standard")
        res_focus = str(study_focus)[:40] if study_focus is not None else current.get("study_focus", "exam")
        res_mem = int(memory_enabled if memory_enabled is not None else current.get("memory_enabled", True))
        res_inst = str(custom_instructions)[:1000] if custom_instructions is not None else current.get("custom_instructions", "")

        now = _now()
        with _LOCK, self._conn() as conn:
            conn.execute(
                "INSERT INTO profiles (user_id, display_name, avatar, response_style, "
                "explanation_detail, study_focus, memory_enabled, custom_instructions, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET "
                "display_name = excluded.display_name, "
                "avatar = excluded.avatar, "
                "response_style = excluded.response_style, "
                "explanation_detail = excluded.explanation_detail, "
                "study_focus = excluded.study_focus, "
                "memory_enabled = excluded.memory_enabled, "
                "custom_instructions = excluded.custom_instructions, "
                "updated_at = excluded.updated_at",
                (user_id, name, res_avatar, res_style, res_detail, res_focus, res_mem, res_inst, now, now),
            )
        return self.get_profile(user_id)

    def clear_conversation(self, chat_id: str, user_id: str) -> int:
        with _LOCK, self._conn() as conn:
            cursor = conn.execute(
                "DELETE FROM conversations WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id),
            )
            return cursor.rowcount

    # --------------------------------------------------------
    # B) USER MEMORY (cross-chat)
    # --------------------------------------------------------

    def remember(
        self,
        user_id: str,
        content: str,
        source: str = "conversation",
    ) -> int:
        content = (content or "").strip()
        if not content:
            return 0
        with _LOCK, self._conn() as conn:
            try:
                cursor = conn.execute(
                    "INSERT INTO user_memory (user_id, content, source, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (user_id, content, source, _now(), _now()),
                )
                return cursor.lastrowid or 0
            except sqlite3.IntegrityError:
                # Same fact already stored — consolidation, not duplication.
                conn.execute(
                    "UPDATE user_memory SET updated_at = ?, source = ? "
                    "WHERE user_id = ? AND content = ?",
                    (_now(), source, user_id, content),
                )
                return 0

    def recall(
        self,
        user_id: str,
        query: str = "",
        limit: int = 20,
    ) -> list[dict]:
        """
        Retrieve the user's memory facts. Ordered by recency, newest
        first. `query` is currently unused — semantic search over
        memory is a future enhancement; the model filters relevance.
        Keeping the parameter preserves the API shape.
        """
        with _LOCK, self._conn() as conn:
            rows = conn.execute(
                "SELECT id, content, source, created_at, updated_at FROM user_memory "
                "WHERE user_id = ? ORDER BY updated_at DESC, id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [
            {
                "id": r["id"],
                "content": r["content"],
                "source": r["source"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]

    def forget(self, user_id: str, content: str) -> int:
        content = (content or "").strip()
        if not content:
            return 0
        with _LOCK, self._conn() as conn:
            cursor = conn.execute(
                "DELETE FROM user_memory WHERE user_id = ? AND content LIKE ?",
                (user_id, f"%{content}%"),
            )
            return cursor.rowcount

    def forget_by_id(self, user_id: str, memory_id: int) -> int:
        with _LOCK, self._conn() as conn:
            cursor = conn.execute(
                "DELETE FROM user_memory WHERE user_id = ? AND id = ?",
                (user_id, memory_id),
            )
            return cursor.rowcount

    def delete_all_memories(self, user_id: str) -> int:
        with _LOCK, self._conn() as conn:
            cursor = conn.execute(
                "DELETE FROM user_memory WHERE user_id = ?",
                (user_id,),
            )
            return cursor.rowcount

    def correct(
        self,
        user_id: str,
        old_content: str,
        new_content: str,
    ) -> int:
        """Replace a stored fact with its corrected version atomically."""
        old = (old_content or "").strip()
        new = (new_content or "").strip()
        with _LOCK, self._conn() as conn:
            cursor = conn.execute(
                "UPDATE user_memory SET content = ?, source = 'corrected', updated_at = ? "
                "WHERE user_id = ? AND content LIKE ?",
                (new, _now(), user_id, f"%{old}%"),
            )
            return cursor.rowcount

    # --------------------------------------------------------
    # C) QUIZ SESSIONS & ATTEMPTS
    # --------------------------------------------------------

    def start_quiz_session(
        self,
        user_id: str,
        chat_id: str,
        topic: str = "",
    ) -> str:
        """Creates a quiz session and returns its quiz_id."""
        quiz_id = str(uuid.uuid4())
        now = _now()
        with _LOCK, self._conn() as conn:
            conn.execute(
                "INSERT INTO quiz_sessions (user_id, quiz_id, chat_id, topic, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 'active', ?, ?)",
                (user_id, quiz_id, chat_id, topic, now, now),
            )
            # Only one active quiz per user/chat: an older active session
            # in the SAME chat is auto-completed. Other chats' sessions
            # stay active (a user can continue a quiz started elsewhere).
            conn.execute(
                "UPDATE quiz_sessions SET status = 'completed', updated_at = ? "
                "WHERE user_id = ? AND chat_id = ? AND status = 'active' AND quiz_id != ?",
                (now, user_id, chat_id, quiz_id),
            )
            return quiz_id

    def active_quiz_session(self, user_id: str, chat_id: str) -> Optional[dict]:
        with _LOCK, self._conn() as conn:
            row = conn.execute(
                "SELECT quiz_id, topic, created_at, question_count, correct_count "
                "FROM quiz_sessions WHERE user_id = ? AND chat_id = ? AND status = 'active' "
                "ORDER BY created_at DESC LIMIT 1",
                (user_id, chat_id),
            ).fetchone()
        if row is None:
            return None
        return dict(row)

    def get_quiz_session(self, user_id: str, quiz_id: str) -> Optional[dict]:
        with _LOCK, self._conn() as conn:
            row = conn.execute(
                "SELECT quiz_id, chat_id, topic, question_count, correct_count, status, created_at, updated_at "
                "FROM quiz_sessions WHERE user_id = ? AND quiz_id = ?",
                (user_id, quiz_id),
            ).fetchone()
        if row is None:
            return None
        return dict(row)

    def all_quiz_sessions(self, user_id: str, include_completed: bool = True) -> list[dict]:
        sql = (
            "SELECT quiz_id, chat_id, topic, question_count, correct_count, status, created_at, updated_at "
            "FROM quiz_sessions WHERE user_id = ?"
        )
        if not include_completed:
            sql += " AND status = 'active'"
        sql += " ORDER BY created_at DESC"
        with _LOCK, self._conn() as conn:
            rows = conn.execute(sql, (user_id,)).fetchall()
        return [dict(r) for r in rows]

    def find_quiz_sessions(
        self,
        user_id: str,
        topic_substring: str = "",
        limit: int = 5,
    ) -> list[dict]:
        """Cross-chat quiz lookup by topic; never scoped by chat_id."""
        sql = (
            "SELECT quiz_id, chat_id, topic, question_count, correct_count, status, created_at, updated_at "
            "FROM quiz_sessions WHERE user_id = ? AND status != 'abandoned'"
        )
        params: list[Any] = [user_id]
        if topic_substring:
            sql += " AND topic LIKE ?"
            params.append(f"%{topic_substring}%")
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with _LOCK, self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def record_attempt(
        self,
        user_id: str,
        quiz_id: str,
        chat_id: str,
        question_id: str,
        question_text: str,
        correct_answer: str,
        submitted_answer: str,
        is_correct: bool,
        options: Optional[dict] = None,
        points_awarded: float = 1.0,
        max_points: float = 1.0,
        attempt_status: str = "answered",
    ) -> int:
        """
        Records ONE answered attempt. Idempotent per (quiz_id,
        question_id): a retry overwrites the earlier attempt (UPDATE in
        place), and question_count/correct_count on the parent session
        are always recomputed from attempts (never incremented twice).
        """
        now = _now()
        with _LOCK, self._conn() as conn:
            cursor = conn.execute(
                "INSERT INTO quiz_attempts (user_id, quiz_id, chat_id, question_id, question_text, "
                "options_json, correct_answer, submitted_answer, is_correct, points_awarded, "
                "max_points, attempt_status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (quiz_id, question_id) DO UPDATE SET "
                "submitted_answer = excluded.submitted_answer, "
                "is_correct = excluded.is_correct, "
                "points_awarded = excluded.points_awarded, "
                "attempt_status = excluded.attempt_status, "
                "created_at = excluded.created_at",
                (
                    user_id, quiz_id, chat_id, question_id, question_text,
                    json.dumps(options or {}), correct_answer, submitted_answer,
                    int(is_correct), points_awarded, max_points, attempt_status, now,
                ),
            )

            # Recompute counters from attempts — never double-count.
            # Pending (asked, unanswered) attempts are not scored yet.
            counts = conn.execute(
                "SELECT COUNT(*) AS total, SUM(is_correct) AS right FROM quiz_attempts "
                "WHERE user_id = ? AND quiz_id = ? AND attempt_status = 'answered'",
                (user_id, quiz_id),
            ).fetchone()
            target_status = 'active'
            session = conn.execute(
                "SELECT status FROM quiz_sessions WHERE user_id = ? AND quiz_id = ?",
                (user_id, quiz_id),
            ).fetchone()
            if session is not None and session["status"] != 'abandoned':
                conn.execute(
                    "UPDATE quiz_sessions SET question_count = ?, correct_count = ?, updated_at = ? "
                    "WHERE user_id = ? AND quiz_id = ?",
                    (
                        counts["total"] or 0,
                        counts["right"] or 0,
                        now,
                        user_id, quiz_id,
                    ),
                )
            return cursor.lastrowid or 0

    def register_pending_question(
        self,
        user_id: str,
        quiz_id: str,
        chat_id: str,
        question_id: str,
        question_text: str,
        options: Optional[dict] = None,
        correct_answer: str = "",
    ) -> int:
        """
        Marks a question as asked but not yet answered. The answer
        becomes a real attempt only when graded against a verified
        key (the tutor's own feedback or the model's answer key).
        """
        now = _now()
        with _LOCK, self._conn() as conn:
            cursor = conn.execute(
                "INSERT INTO quiz_attempts (user_id, quiz_id, chat_id, question_id, question_text, "
                "options_json, correct_answer, submitted_answer, is_correct, points_awarded, "
                "max_points, attempt_status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?) "
                "ON CONFLICT (quiz_id, question_id) DO NOTHING",
                (
                    user_id, quiz_id, chat_id, question_id, question_text,
                    json.dumps(options or {}), correct_answer, "", 0, 0.0,
                    1.0, now,
                ),
            )
            return cursor.lastrowid or 0

    def grade_pending_attempt(
        self,
        user_id: str,
        quiz_id: str,
        question_id: str,
        submitted_answer: str,
        is_correct: Optional[bool],
    ) -> None:
        """
        Grading Time: fills in the pending attempt's submitted answer
        and correctness. is_correct=None means the key was never
        verified — record the attempt honestly as unverifiable.
        """
        if is_correct is None:
            with _LOCK, self._conn() as conn:
                conn.execute(
                    "UPDATE quiz_attempts SET submitted_answer = ?, attempt_status = 'skipped' "
                    "WHERE user_id = ? AND quiz_id = ? AND question_id = ? AND attempt_status = 'pending'",
                    (submitted_answer, user_id, quiz_id, question_id),
                )
            return
        with _LOCK, self._conn() as conn:
            conn.execute(
                "UPDATE quiz_attempts SET submitted_answer = ?, is_correct = ?, "
                "points_awarded = CASE WHEN ? THEN 1.0 ELSE 0.0 END, "
                "attempt_status = 'answered' "
                "WHERE user_id = ? AND quiz_id = ? AND question_id = ? AND attempt_status = 'pending'",
                (submitted_answer, int(is_correct), int(is_correct), user_id, quiz_id, question_id),
            )

    def get_attempts(self, user_id: str, quiz_id: str) -> list[dict]:
        with _LOCK, self._conn() as conn:
            rows = conn.execute(
                "SELECT question_id, question_text, options_json, correct_answer, submitted_answer, "
                "is_correct, points_awarded, max_points, attempt_status, created_at "
                "FROM quiz_attempts WHERE user_id = ? AND quiz_id = ? ORDER BY id",
                (user_id, quiz_id),
            ).fetchall()
        return [
            {
                **{
                    k: dict(r)[k] for k in (
                        "question_id", "question_text", "correct_answer",
                        "submitted_answer", "is_correct", "points_awarded",
                        "max_points", "attempt_status", "created_at",
                    )
                },
                "options": json.loads(r["options_json"]),
            }
            for r in rows
        ]

    def score_quiz(self, user_id: str, quiz_id: str) -> Optional[dict]:
        """
        Deterministic scoring from stored attempts. Never consults an
        LLM or the live conversation.
        """
        with _LOCK, self._conn() as conn:
            row = conn.execute(
                "SELECT question_count, correct_count, topic, chat_id, status, created_at, updated_at "
                "FROM quiz_sessions WHERE user_id = ? AND quiz_id = ?",
                (user_id, quiz_id),
            ).fetchone()
            if row is None:
                return None
            attempts = conn.execute(
                "SELECT COUNT(*) AS total, "
                "SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) AS right, "
                "SUM(points_awarded) AS points, SUM(max_points) AS max_points "
                "FROM quiz_attempts WHERE user_id = ? AND quiz_id = ? "
                "AND attempt_status = 'answered'",
                (user_id, quiz_id),
            ).fetchone()
        total = int(attempts["total"] or 0)
        right = int(attempts["right"] or 0)
        max_points = float(attempts["max_points"] or 0.0)
        points = float(attempts["points"] or 0.0)
        percentage = (100.0 * right / total) if total else 0.0
        return {
            "quiz_id": quiz_id,
            "topic": row["topic"],
            "chat_id": row["chat_id"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "attempted": total,
            "correct": right,
            "percentage": round(percentage, 1),
            "points": round(points, 1),
            "max_points": round(max_points, 1),
        }

    def mark_quiz_completed(self, user_id: str, quiz_id: str) -> bool:
        with _LOCK, self._conn() as conn:
            cursor = conn.execute(
                "UPDATE quiz_sessions SET status = 'completed', updated_at = ? "
                "WHERE user_id = ? AND quiz_id = ? AND status = 'active'",
                (_now(), user_id, quiz_id),
            )
            return cursor.rowcount > 0

    def abandon_quiz_session(self, user_id: str, quiz_id: str) -> bool:
        with _LOCK, self._conn() as conn:
            cursor = conn.execute(
                "UPDATE quiz_sessions SET status = 'abandoned', updated_at = ? "
                "WHERE user_id = ? AND quiz_id = ?",
                (_now(), user_id, quiz_id),
            )
            return cursor.rowcount > 0

    def delete_quiz_session(self, user_id: str, quiz_id: str) -> bool:
        with _LOCK, self._conn() as conn:
            conn.execute(
                "DELETE FROM quiz_attempts WHERE user_id = ? AND quiz_id = ?",
                (user_id, quiz_id),
            )
            cursor = conn.execute(
                "DELETE FROM quiz_sessions WHERE user_id = ? AND quiz_id = ?",
                (user_id, quiz_id),
            )
            return cursor.rowcount > 0

    # --------------------------------------------------------
    # F) AI USAGE & ANALYTICS
    # --------------------------------------------------------

    def record_usage(
        self,
        user_id: str,
        chat_id: Optional[str],
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        token_counting_method: str = "provider",
        request_status: str = "success",
        duration_ms: Optional[int] = None,
        created_at: Optional[str] = None,
    ) -> int:
        """
        Record a model request's token usage.
        Does not log prompts, answers, or credentials.
        """
        now = created_at or _now()
        total = max(0, int(input_tokens)) + max(0, int(output_tokens))
        with _LOCK, self._conn() as conn:
            cursor = conn.execute(
                "INSERT INTO ai_usage (user_id, chat_id, model_id, input_tokens, output_tokens, "
                "total_tokens, token_counting_method, request_status, duration_ms, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    user_id,
                    chat_id,
                    model_id,
                    max(0, int(input_tokens)),
                    max(0, int(output_tokens)),
                    total,
                    token_counting_method,
                    request_status,
                    duration_ms,
                    now,
                ),
            )
            return cursor.lastrowid or 0

    def get_first_recorded_usage_date(self, user_id: str, tz: ZoneInfo = DEFAULT_TIMEZONE) -> Optional[str]:
        """Returns earliest tracking date in Asia/Colombo YYYY-MM-DD, or None."""
        with _LOCK, self._conn() as conn:
            row = conn.execute(
                "SELECT MIN(created_at) as first_dt FROM ai_usage WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if not row or not row["first_dt"]:
            return None
        try:
            dt = datetime.fromisoformat(row["first_dt"].replace("Z", "+00:00"))
            return dt.astimezone(tz).strftime("%Y-%m-%d")
        except Exception:
            return None

    def get_usage_summary(
        self,
        user_id: str,
        range_key: str = "last_30_days",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        tz: ZoneInfo = DEFAULT_TIMEZONE,
    ) -> dict:
        """
        Calculates summary metrics:
        Tokens today, this week, this month, last month (fixed periods).
        Plus period-filtered input/output/total tokens, requests count, average tokens, average latency.
        """
        now_local = datetime.now(tz)

        today_start = datetime(now_local.year, now_local.month, now_local.day, tzinfo=tz)
        week_start = today_start - timedelta(days=now_local.weekday())
        month_start = datetime(now_local.year, now_local.month, 1, tzinfo=tz)
        if now_local.month == 1:
            last_month_start = datetime(now_local.year - 1, 12, 1, tzinfo=tz)
            last_month_end = datetime(now_local.year, 1, 1, tzinfo=tz)
        else:
            last_month_start = datetime(now_local.year, now_local.month - 1, 1, tzinfo=tz)
            last_month_end = datetime(now_local.year, now_local.month, 1, tzinfo=tz)

        if range_key == "today":
            filter_start = today_start
            filter_end = today_start + timedelta(days=1)
        elif range_key == "last_7_days":
            filter_start = today_start - timedelta(days=6)
            filter_end = today_start + timedelta(days=1)
        elif range_key == "last_30_days":
            filter_start = today_start - timedelta(days=29)
            filter_end = today_start + timedelta(days=1)
        elif range_key == "this_month":
            filter_start = month_start
            filter_end = today_start + timedelta(days=1)
        elif range_key == "last_month":
            filter_start = last_month_start
            filter_end = last_month_end
        elif range_key == "this_year":
            filter_start = datetime(now_local.year, 1, 1, tzinfo=tz)
            filter_end = today_start + timedelta(days=1)
        elif range_key == "custom" and start_date and end_date:
            try:
                sd = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=tz)
                ed = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=tz) + timedelta(days=1)
                filter_start, filter_end = sd, ed
            except Exception:
                filter_start = today_start - timedelta(days=29)
                filter_end = today_start + timedelta(days=1)
        else:
            filter_start = today_start - timedelta(days=29)
            filter_end = today_start + timedelta(days=1)

        with _LOCK, self._conn() as conn:
            rows = conn.execute(
                "SELECT id, input_tokens, output_tokens, total_tokens, request_status, duration_ms, created_at "
                "FROM ai_usage WHERE user_id = ? ORDER BY id ASC",
                (user_id,),
            ).fetchall()

        tokens_today = 0
        tokens_this_week = 0
        tokens_this_month = 0
        tokens_last_month = 0

        filtered_input = 0
        filtered_output = 0
        filtered_total = 0
        filtered_requests = 0
        filtered_successful = 0
        filtered_failed = 0
        latencies: list[int] = []

        for r in rows:
            try:
                dt_utc = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
                dt_local = dt_utc.astimezone(tz)
            except Exception:
                continue

            tot = r["total_tokens"]
            is_success = (r["request_status"] == "success")

            if is_success:
                if dt_local >= today_start:
                    tokens_today += tot
                if dt_local >= week_start:
                    tokens_this_week += tot
                if dt_local >= month_start:
                    tokens_this_month += tot
                if last_month_start <= dt_local < last_month_end:
                    tokens_last_month += tot

            if filter_start <= dt_local < filter_end:
                filtered_requests += 1
                if is_success:
                    filtered_successful += 1
                    filtered_input += r["input_tokens"]
                    filtered_output += r["output_tokens"]
                    filtered_total += tot
                    if r["duration_ms"] is not None:
                        latencies.append(r["duration_ms"])
                else:
                    filtered_failed += 1

        avg_tokens = (round(filtered_total / filtered_successful, 1)) if filtered_successful > 0 else 0.0
        avg_latency = (round(sum(latencies) / len(latencies), 1)) if latencies else None

        return {
            "tokens_today": tokens_today,
            "tokens_this_week": tokens_this_week,
            "tokens_this_month": tokens_this_month,
            "tokens_last_month": tokens_last_month,
            "input_tokens": filtered_input,
            "output_tokens": filtered_output,
            "total_tokens": filtered_total,
            "total_requests": filtered_requests,
            "successful_requests": filtered_successful,
            "failed_requests": filtered_failed,
            "avg_tokens_per_request": avg_tokens,
            "avg_latency_ms": avg_latency,
            "range": range_key,
            "start_date": filter_start.strftime("%Y-%m-%d"),
            "end_date": (filter_end - timedelta(days=1)).strftime("%Y-%m-%d"),
            "timezone": tz.key,
        }

    def get_usage_calendar(
        self,
        user_id: str,
        year: Optional[int] = None,
        tz: ZoneInfo = DEFAULT_TIMEZONE,
    ) -> dict:
        """
        GitHub-style contribution calendar for an entire year.
        Generates all calendar days Jan 1 - Dec 31.
        Intensity scale:
          0: 0 tokens
          1: 1 – 2,500 tokens
          2: 2,501 – 10,000 tokens
          3: 10,001 – 30,000 tokens
          4: > 30,000 tokens
        Days before first tracked usage are marked 'unavailable'.
        """
        now_local = datetime.now(tz)
        target_year = int(year) if year else now_local.year
        first_tracked_date = self.get_first_recorded_usage_date(user_id, tz)

        with _LOCK, self._conn() as conn:
            rows = conn.execute(
                "SELECT input_tokens, output_tokens, total_tokens, request_status, created_at "
                "FROM ai_usage WHERE user_id = ? ORDER BY id ASC",
                (user_id,),
            ).fetchall()

        daily_data: dict[str, dict] = {}
        for r in rows:
            try:
                dt_utc = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
                dt_local = dt_utc.astimezone(tz)
            except Exception:
                continue

            if dt_local.year != target_year:
                continue

            d_str = dt_local.strftime("%Y-%m-%d")
            if d_str not in daily_data:
                daily_data[d_str] = {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                    "request_count": 0,
                    "successful_requests": 0,
                }
            daily_data[d_str]["input_tokens"] += r["input_tokens"]
            daily_data[d_str]["output_tokens"] += r["output_tokens"]
            daily_data[d_str]["total_tokens"] += r["total_tokens"]
            daily_data[d_str]["request_count"] += 1
            if r["request_status"] == "success":
                daily_data[d_str]["successful_requests"] += 1

        def _calc_intensity(tokens: int) -> int:
            if tokens <= 0:
                return 0
            if tokens <= 2500:
                return 1
            if tokens <= 10000:
                return 2
            if tokens <= 30000:
                return 3
            return 4

        start_d = date(target_year, 1, 1)
        end_d = date(target_year, 12, 31)
        delta = timedelta(days=1)
        curr = start_d

        days: list[dict] = []
        year_total_tokens = 0
        year_total_requests = 0

        while curr <= end_d:
            d_str = curr.strftime("%Y-%m-%d")
            entry = daily_data.get(d_str)

            if entry:
                tot = entry["total_tokens"]
                in_tok = entry["input_tokens"]
                out_tok = entry["output_tokens"]
                req_cnt = entry["request_count"]
                intensity = _calc_intensity(tot)
                status = "tracked"
                year_total_tokens += tot
                year_total_requests += req_cnt
            else:
                tot = 0
                in_tok = 0
                out_tok = 0
                req_cnt = 0
                intensity = 0
                if first_tracked_date and d_str < first_tracked_date:
                    status = "unavailable"
                elif first_tracked_date is None:
                    status = "unavailable"
                else:
                    status = "tracked"

            days.append({
                "date": d_str,
                "weekday": curr.weekday(),
                "month": curr.month,
                "day": curr.day,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "total_tokens": tot,
                "request_count": req_cnt,
                "intensity": intensity,
                "status": status,
            })
            curr += delta

        return {
            "year": target_year,
            "timezone": tz.key,
            "total_tokens": year_total_tokens,
            "total_requests": year_total_requests,
            "first_tracked_date": first_tracked_date,
            "days": days,
            "intensity_scale": {
                "0": "0 tokens",
                "1": "1 – 2,500 tokens",
                "2": "2,501 – 10,000 tokens",
                "3": "10,001 – 30,000 tokens",
                "4": "> 30,000 tokens",
            },
        }

    def get_usage_timeseries(
        self,
        user_id: str,
        range_key: str = "last_30_days",
        tz: ZoneInfo = DEFAULT_TIMEZONE,
    ) -> list[dict]:
        """Daily points for token trends in the specified range."""
        now_local = datetime.now(tz)
        today_start = datetime(now_local.year, now_local.month, now_local.day, tzinfo=tz)

        if range_key == "today":
            filter_start = today_start
            days_count = 1
        elif range_key == "last_7_days":
            filter_start = today_start - timedelta(days=6)
            days_count = 7
        elif range_key == "this_month":
            filter_start = datetime(now_local.year, now_local.month, 1, tzinfo=tz)
            days_count = (today_start - filter_start).days + 1
        elif range_key == "this_year":
            filter_start = datetime(now_local.year, 1, 1, tzinfo=tz)
            days_count = (today_start - filter_start).days + 1
        else:
            filter_start = today_start - timedelta(days=29)
            days_count = 30

        daily: dict[str, dict] = {}
        for i in range(days_count):
            d = (filter_start + timedelta(days=i)).strftime("%Y-%m-%d")
            daily[d] = {"date": d, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "requests": 0}

        with _LOCK, self._conn() as conn:
            rows = conn.execute(
                "SELECT input_tokens, output_tokens, total_tokens, request_status, created_at "
                "FROM ai_usage WHERE user_id = ? ORDER BY id ASC",
                (user_id,),
            ).fetchall()

        for r in rows:
            try:
                dt_utc = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
                d_str = dt_utc.astimezone(tz).strftime("%Y-%m-%d")
            except Exception:
                continue

            if d_str in daily:
                daily[d_str]["input_tokens"] += r["input_tokens"]
                daily[d_str]["output_tokens"] += r["output_tokens"]
                daily[d_str]["total_tokens"] += r["total_tokens"]
                daily[d_str]["requests"] += 1

        return sorted(daily.values(), key=lambda x: x["date"])

    def get_usage_by_model(
        self,
        user_id: str,
        range_key: str = "last_30_days",
        tz: ZoneInfo = DEFAULT_TIMEZONE,
    ) -> list[dict]:
        """Token breakdown by model ID."""
        with _LOCK, self._conn() as conn:
            rows = conn.execute(
                "SELECT model_id, SUM(input_tokens) as input_tokens, SUM(output_tokens) as output_tokens, "
                "SUM(total_tokens) as total_tokens, COUNT(*) as request_count, "
                "SUM(CASE WHEN request_status = 'success' THEN 1 ELSE 0 END) as successful_requests "
                "FROM ai_usage WHERE user_id = ? GROUP BY model_id ORDER BY total_tokens DESC",
                (user_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_recent_requests(
        self,
        user_id: str,
        limit: int = 25,
        tz: ZoneInfo = DEFAULT_TIMEZONE,
    ) -> list[dict]:
        """Recent request log."""
        with _LOCK, self._conn() as conn:
            rows = conn.execute(
                "SELECT id, chat_id, model_id, input_tokens, output_tokens, total_tokens, "
                "token_counting_method, request_status, duration_ms, created_at "
                "FROM ai_usage WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()

        result = []
        for r in rows:
            item = dict(r)
            try:
                dt_utc = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
                item["created_at_local"] = dt_utc.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                item["created_at_local"] = r["created_at"]
            result.append(item)
        return result

    def export_usage_records(self, user_id: str) -> list[dict]:
        """All usage records for export."""
        with _LOCK, self._conn() as conn:
            rows = conn.execute(
                "SELECT id, chat_id, model_id, input_tokens, output_tokens, total_tokens, "
                "token_counting_method, request_status, duration_ms, created_at "
                "FROM ai_usage WHERE user_id = ? ORDER BY id ASC",
                (user_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    # --------------------------------------------------------
    # G) STORAGE & PRIVACY MANAGEMENT
    # --------------------------------------------------------

    def get_storage_stats(
        self,
        user_id: str,
        uploads_dir: Path,
        cache_dir: Path,
    ) -> dict:
        """Calculates real filesystem and database storage usage."""
        db_size = self.db_path.stat().st_size if self.db_path.exists() else 0
        ckpt_path = cache_dir / "strud_checkpoints.db"
        ckpt_size = ckpt_path.stat().st_size if ckpt_path.exists() else 0

        uploads_size = 0
        uploads_count = 0
        if uploads_dir.exists() and uploads_dir.is_dir():
            for f in uploads_dir.iterdir():
                if f.is_file():
                    uploads_count += 1
                    uploads_size += f.stat().st_size

        with _LOCK, self._conn() as conn:
            chats_active = conn.execute("SELECT COUNT(*) FROM chats WHERE user_id = ? AND deleted_at IS NULL", (user_id,)).fetchone()[0]
            chats_deleted = conn.execute("SELECT COUNT(*) FROM chats WHERE user_id = ? AND deleted_at IS NOT NULL", (user_id,)).fetchone()[0]
            messages_cnt = conn.execute("SELECT COUNT(*) FROM conversations WHERE user_id = ?", (user_id,)).fetchone()[0]
            memories_cnt = conn.execute("SELECT COUNT(*) FROM user_memory WHERE user_id = ?", (user_id,)).fetchone()[0]
            quizzes_cnt = conn.execute("SELECT COUNT(*) FROM quiz_sessions WHERE user_id = ?", (user_id,)).fetchone()[0]
            usage_cnt = conn.execute("SELECT COUNT(*) FROM ai_usage WHERE user_id = ?", (user_id,)).fetchone()[0]

        return {
            "database_size_bytes": db_size,
            "checkpoints_size_bytes": ckpt_size,
            "uploads_size_bytes": uploads_size,
            "uploads_count": uploads_count,
            "active_chats_count": chats_active,
            "deleted_chats_count": chats_deleted,
            "messages_count": messages_cnt,
            "memories_count": memories_cnt,
            "quiz_sessions_count": quizzes_cnt,
            "usage_records_count": usage_cnt,
        }

    def clean_orphaned_uploads(self, uploads_dir: Path) -> dict:
        """Deletes files in uploads_dir that are no longer referenced in conversations."""
        if not uploads_dir.exists():
            return {"removed_count": 0, "freed_bytes": 0}

        referenced_filenames: set[str] = set()
        with _LOCK, self._conn() as conn:
            rows = conn.execute("SELECT attachments_json FROM conversations WHERE attachments_json IS NOT NULL").fetchall()
        for r in rows:
            try:
                atts = json.loads(r["attachments_json"] or "[]")
                for att in atts:
                    fname = Path(str(att.get("url", ""))).name
                    if fname:
                        referenced_filenames.add(fname)
            except Exception:
                continue

        removed_count = 0
        freed_bytes = 0
        for f in uploads_dir.iterdir():
            if f.is_file() and f.name not in referenced_filenames:
                try:
                    size = f.stat().st_size
                    f.unlink()
                    removed_count += 1
                    freed_bytes += size
                except Exception:
                    pass

        return {"removed_count": removed_count, "freed_bytes": freed_bytes}

    def export_full_data(self, user_id: str) -> dict:
        """Exports all chats, messages, profile, memories, and usage as a complete user archive."""
        return {
            "version": "1.0",
            "exported_at": _now(),
            "user_id": user_id,
            "profile": self.get_profile(user_id),
            "chats": self.list_chats(user_id, deleted=False),
            "deleted_chats": self.list_chats(user_id, deleted=True),
            "memories": self.recall(user_id, limit=200),
            "quizzes": self.all_quiz_sessions(user_id, include_completed=True),
            "usage": self.export_usage_records(user_id),
        }

    def clear_all_chats(self, user_id: str, move_to_bin: bool = True) -> int:
        """Moves all active chats to bin, or deletes them permanently."""
        now = _now()
        with _LOCK, self._conn() as conn:
            if move_to_bin:
                cursor = conn.execute(
                    "UPDATE chats SET deleted_at = ?, updated_at = ? WHERE user_id = ? AND deleted_at IS NULL",
                    (now, now, user_id),
                )
                return cursor.rowcount
            else:
                cursor = conn.execute("DELETE FROM chats WHERE user_id = ?", (user_id,))
                conn.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))
                return cursor.rowcount


# ============================================================
# MODULE-LEVEL SINGLETON
# ============================================================

_store: Optional[MemoryStore] = None
_store_lock = threading.Lock()


def get_memory_store(db_path: Optional[Path] = None) -> MemoryStore:
    """Module-level singleton so every chat session shares one store."""
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                from config import CACHE_DIR
                resolved = Path(db_path) if db_path else CACHE_DIR / "strud_memory_v3.db"
                _store = MemoryStore(resolved)
    return _store

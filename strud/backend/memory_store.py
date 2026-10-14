# memory_store.py
#
# Strud AI — persistent memory layer (SQLite via stdlib sqlite3).
#
#三层 memory solution:
#   A. conversations      — chat history, durable across backend restarts
#   B. user_memory        — cross-chat facts and study preferences (user-scoped)
#   C. quiz_sessions/attempts — structured quiz scoring, never LLM-recalled
#
# Isolation rule: user_id is ALWAYS part of the lookup key, so one
# user's memory can never be served to another user's session.
# Anonymous frontend users get a stable per-browser user_id ("local").

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_TABLES = [
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
    ) -> int:
        with _LOCK, self._conn() as conn:
            cursor = conn.execute(
                "INSERT INTO conversations (user_id, chat_id, role, content, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, chat_id, role, (content or "").strip(), _now()),
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
                "SELECT role, content, created_at FROM conversations "
                "WHERE chat_id = ? AND user_id = ? ORDER BY id DESC LIMIT ?",
                (chat_id, user_id, limit),
            ).fetchall()
        rows.reverse()
        return [
            {"role": r["role"], "content": r["content"], "created_at": r["created_at"]}
            for r in rows
        ]

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

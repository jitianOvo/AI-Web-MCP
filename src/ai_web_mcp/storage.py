"""Small SQLite store for conversations, messages, and task state."""

from __future__ import annotations

import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS targets (
  target_id TEXT PRIMARY KEY,
  browser TEXT NOT NULL DEFAULT '',
  tab_id INTEGER,
  title TEXT NOT NULL DEFAULT '',
  url TEXT NOT NULL DEFAULT '',
  ready INTEGER NOT NULL DEFAULT 0,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS conversations (
  conversation_id TEXT PRIMARY KEY,
  target_id TEXT NOT NULL DEFAULT '',
  title TEXT NOT NULL DEFAULT '',
  url TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
  sequence INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id TEXT NOT NULL,
  conversation_id TEXT NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  observed_at REAL NOT NULL,
  UNIQUE(conversation_id, message_id)
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_sequence
  ON messages(conversation_id, sequence);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_hash
  ON messages(conversation_id, content_hash);
CREATE TABLE IF NOT EXISTS tasks (
  request_id TEXT PRIMARY KEY,
  conversation_id TEXT NOT NULL DEFAULT '',
  target_id TEXT NOT NULL DEFAULT '',
  persona_id TEXT NOT NULL DEFAULT '',
  task_group_id TEXT NOT NULL DEFAULT '',
  state TEXT NOT NULL,
  prompt TEXT NOT NULL DEFAULT '',
  result TEXT NOT NULL DEFAULT '',
  error_code TEXT NOT NULL DEFAULT '',
  error_message TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS personas (
  persona_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  system_prompt TEXT NOT NULL DEFAULT '',
  config_json TEXT NOT NULL DEFAULT '{}',
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS task_groups (
  task_group_id TEXT PRIMARY KEY,
  title TEXT NOT NULL DEFAULT '',
  state TEXT NOT NULL DEFAULT 'created',
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
"""


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._session() as conn:
            conn.executescript(SCHEMA)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
            for name in ("target_id", "persona_id", "task_group_id"):
                if name not in columns:
                    conn.execute(f"ALTER TABLE tasks ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_group ON tasks(task_group_id, created_at)")
            if "stage" not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN stage TEXT NOT NULL DEFAULT 'CREATED'")
            if "fingerprint" not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN fingerprint TEXT NOT NULL DEFAULT ''")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_target ON tasks(target_id, state, created_at)")
            self._migrate_message_hash_constraint(conn)
            conn.execute(
                """UPDATE tasks SET state='interrupted',error_code='BRIDGE_RESTART',
                   error_message='Bridge 在任务完成前重启',updated_at=?
                   WHERE state IN ('queued','running')""",
                (time.time(),),
            )
            conn.execute(
                "UPDATE task_groups SET state='interrupted',updated_at=? WHERE state='running'",
                (time.time(),),
            )

    @staticmethod
    def _migrate_message_hash_constraint(conn: sqlite3.Connection) -> None:
        schema_row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='messages'"
        ).fetchone()
        schema_sql = str(schema_row[0] or "") if schema_row else ""
        compact = "".join(schema_sql.lower().split())
        if "unique(conversation_id,content_hash)" not in compact:
            return
        conn.execute("DROP INDEX IF EXISTS idx_messages_conversation_sequence")
        conn.execute("DROP INDEX IF EXISTS idx_messages_conversation_hash")
        conn.execute(
            """CREATE TABLE messages_migrated (
               sequence INTEGER PRIMARY KEY AUTOINCREMENT,
               message_id TEXT NOT NULL,
               conversation_id TEXT NOT NULL,
               role TEXT NOT NULL,
               content TEXT NOT NULL,
               content_hash TEXT NOT NULL,
               observed_at REAL NOT NULL,
               UNIQUE(conversation_id, message_id)
            )"""
        )
        conn.execute(
            """INSERT OR IGNORE INTO messages_migrated
               (sequence,message_id,conversation_id,role,content,content_hash,observed_at)
               SELECT sequence,message_id,conversation_id,role,content,content_hash,observed_at FROM messages"""
        )
        conn.execute("DROP TABLE messages")
        conn.execute("ALTER TABLE messages_migrated RENAME TO messages")
        conn.execute("CREATE INDEX idx_messages_conversation_sequence ON messages(conversation_id, sequence)")
        conn.execute("CREATE INDEX idx_messages_conversation_hash ON messages(conversation_id, content_hash)")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _session(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def upsert_target(self, target_id: str, browser: str, tab_id: int | None, title: str, url: str, ready: bool) -> None:
        now = time.time()
        with self._session() as conn:
            conn.execute(
                """INSERT INTO targets(target_id,browser,tab_id,title,url,ready,updated_at)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(target_id) DO UPDATE SET browser=excluded.browser,
                   tab_id=excluded.tab_id,title=excluded.title,url=excluded.url,
                   ready=excluded.ready,updated_at=excluded.updated_at""",
                (target_id, browser, tab_id, title[:200], url[:500], int(ready), now),
            )

    def upsert_conversation(self, conversation_id: str, target_id: str, title: str = "", url: str = "") -> None:
        now = time.time()
        with self._session() as conn:
            conn.execute(
                """INSERT INTO conversations(conversation_id,target_id,title,url,created_at,updated_at)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(conversation_id) DO UPDATE SET target_id=excluded.target_id,
                   title=excluded.title,url=excluded.url,updated_at=excluded.updated_at""",
                (conversation_id, target_id, title[:200], url[:500], now, now),
            )

    def append_message(
        self, conversation_id: str, message_id: str, role: str, content: str,
        content_hash: str, observed_at: float | None = None,
    ) -> bool:
        with self._session() as conn:
            message_id = message_id or uuid.uuid4().hex
            existing = conn.execute(
                "SELECT content_hash,content FROM messages WHERE conversation_id=? AND message_id=?",
                (conversation_id, message_id),
            ).fetchone()
            if existing:
                if existing["content_hash"] == content_hash and existing["content"] == content:
                    return False
                conn.execute(
                    """UPDATE messages SET role=?,content=?,content_hash=?,observed_at=?
                       WHERE conversation_id=? AND message_id=?""",
                    (role, content, content_hash, observed_at or time.time(), conversation_id, message_id),
                )
                return True
            conn.execute(
                """INSERT INTO messages
                   (message_id,conversation_id,role,content,content_hash,observed_at)
                   VALUES(?,?,?,?,?,?)""",
                (message_id, conversation_id, role, content, content_hash, observed_at or time.time()),
            )
            return True

    def get_conversation(self, conversation_id: str) -> dict[str, Any] | None:
        with self._session() as conn:
            row = conn.execute(
                "SELECT conversation_id,target_id,title,url,created_at,updated_at FROM conversations WHERE conversation_id=?", (conversation_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_messages(self, conversation_id: str, after_sequence: int = 0, limit: int = 100) -> list[dict[str, Any]]:

        with self._session() as conn:
            rows = conn.execute(
                """SELECT sequence,message_id,conversation_id,role,content,observed_at
                   FROM messages WHERE conversation_id=? AND sequence>? ORDER BY sequence LIMIT ?""",
                (conversation_id, max(0, int(after_sequence)), max(1, min(1000, int(limit)))),
            ).fetchall()
        return [dict(row) for row in rows]

    def search_messages(
        self, conversation_id: str = "", query: str = "", role: str = "", limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if conversation_id:
            clauses.append("conversation_id=?")
            params.append(conversation_id)
        if query:
            clauses.append("content LIKE ?")
            params.append(f"%{query}%")
        if role:
            clauses.append("role=?")
            params.append(role)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(1000, int(limit))))
        with self._session() as conn:
            rows = conn.execute(
                """SELECT sequence,message_id,conversation_id,role,content,observed_at
                   FROM messages""" + where + " ORDER BY sequence DESC LIMIT ?",
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def count_messages_before(self, cutoff: float, conversation_id: str = "") -> int:
        clauses = ["observed_at < ?"]
        params: list[Any] = [float(cutoff)]
        if conversation_id:
            clauses.append("conversation_id=?")
            params.append(conversation_id)
        with self._session() as conn:
            row = conn.execute(f"SELECT COUNT(*) AS count FROM messages WHERE {' AND '.join(clauses)}", params).fetchone()
        return int(row["count"])

    def prune_messages_before(self, cutoff: float, conversation_id: str = "") -> int:
        clauses = ["observed_at < ?"]
        params: list[Any] = [float(cutoff)]
        if conversation_id:
            clauses.append("conversation_id=?")
            params.append(conversation_id)
        with self._session() as conn:
            cursor = conn.execute(f"DELETE FROM messages WHERE {' AND '.join(clauses)}", params)
        return int(cursor.rowcount)

    def upsert_persona(self, persona_id: str, name: str, system_prompt: str = "", config_json: str = "{}") -> None:
        now = time.time()
        with self._session() as conn:
            conn.execute(
                """INSERT INTO personas(persona_id,name,system_prompt,config_json,created_at,updated_at)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(persona_id) DO UPDATE SET name=excluded.name,
                   system_prompt=excluded.system_prompt,config_json=excluded.config_json,
                   updated_at=excluded.updated_at""",
                (persona_id, name[:120], system_prompt, config_json, now, now),
            )

    def get_persona(self, persona_id: str) -> dict[str, Any] | None:
        with self._session() as conn:
            row = conn.execute("SELECT persona_id,name,system_prompt,config_json,created_at,updated_at FROM personas WHERE persona_id=?", (persona_id,)).fetchone()
        return dict(row) if row else None

    def list_personas(self) -> list[dict[str, Any]]:
        with self._session() as conn:
            rows = conn.execute("SELECT persona_id,name,system_prompt,config_json,created_at,updated_at FROM personas ORDER BY name,persona_id").fetchall()
        return [dict(row) for row in rows]

    def create_task_group(self, task_group_id: str, title: str = "") -> None:
        now = time.time()
        with self._session() as conn:
            conn.execute(
                """INSERT INTO task_groups(task_group_id,title,state,created_at,updated_at)
                   VALUES(?,?,?, ?,?)
                   ON CONFLICT(task_group_id) DO UPDATE SET title=excluded.title,updated_at=excluded.updated_at""",
                (task_group_id, title[:200], "created", now, now),
            )

    def update_task_group(self, task_group_id: str, state: str) -> None:
        with self._session() as conn:
            conn.execute("UPDATE task_groups SET state=?,updated_at=? WHERE task_group_id=?", (state, time.time(), task_group_id))

    def get_task_group(self, task_group_id: str) -> dict[str, Any] | None:
        with self._session() as conn:
            group = conn.execute("SELECT task_group_id,title,state,created_at,updated_at FROM task_groups WHERE task_group_id=?", (task_group_id,)).fetchone()
            if not group:
                return None
            tasks = conn.execute(
                """SELECT request_id,conversation_id,target_id,persona_id,task_group_id,state,prompt,result,error_code,error_message,created_at,updated_at
               ,stage
                   FROM tasks WHERE task_group_id=? ORDER BY created_at,request_id""",
                (task_group_id,),
            ).fetchall()
        result = dict(group)
        result["tasks"] = [dict(row) for row in tasks]
        return result

    def create_task(
        self, request_id: str, conversation_id: str, prompt: str, state: str = "queued",
        target_id: str = "", persona_id: str = "", task_group_id: str = "", fingerprint: str = "",
    ) -> None:
        now = time.time()
        with self._session() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO tasks
                   (request_id,conversation_id,target_id,persona_id,task_group_id,state,prompt,created_at,updated_at,fingerprint)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (request_id, conversation_id, target_id, persona_id, task_group_id, state, prompt, now, now, fingerprint),
            )

    def list_tasks(self, task_group_id: str) -> list[dict[str, Any]]:
        group = self.get_task_group(task_group_id)
        return list(group.get("tasks", [])) if group else []

    def get_task(self, request_id: str) -> dict[str, Any] | None:
        with self._session() as conn:
            row = conn.execute(
                """SELECT request_id,conversation_id,target_id,persona_id,task_group_id,state,
                   prompt,result,error_code,error_message,created_at,updated_at
                   ,stage,fingerprint
                   FROM tasks WHERE request_id=?""",
                (request_id,),
            ).fetchone()
        return dict(row) if row else None

    def update_task(self, request_id: str, state: str, result: str = "", error_code: str = "", error_message: str = "", stage: str = "") -> None:
        with self._session() as conn:
            if stage:
                conn.execute(
                    """UPDATE tasks SET state=?,stage=?,result=?,error_code=?,error_message=?,updated_at=?
                       WHERE request_id=?""",
                    (state, stage, result, error_code, error_message, time.time(), request_id),
                )
            else:
                conn.execute(
                    """UPDATE tasks SET state=?,result=?,error_code=?,error_message=?,updated_at=?
                       WHERE request_id=?""",
                    (state, result, error_code, error_message, time.time(), request_id),
                )

    def set_task_conversation(self, request_id: str, conversation_id: str) -> None:
        with self._session() as conn:
            conn.execute("UPDATE tasks SET conversation_id=? WHERE request_id=?", (conversation_id, request_id))

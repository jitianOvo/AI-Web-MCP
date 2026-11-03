import tempfile
import unittest
import sqlite3
from pathlib import Path

from gpt_web_mcp.storage import Store


class StorageTests(unittest.TestCase):
    def test_image_identity_and_conversation_survive_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "vision.sqlite3"
            store = Store(path)
            store.create_task("img1", "current", "describe", fingerprint="sha256-image-question")
            store.set_task_conversation("img1", "actual-conversation")
            store.update_task("img1", "completed", result="blue frame")
            reopened = Store(path).get_task("img1")
            self.assertEqual(reopened["fingerprint"], "sha256-image-question")
            self.assertEqual(reopened["conversation_id"], "actual-conversation")
            self.assertEqual(reopened["result"], "blue frame")
            self.assertEqual(reopened["state"], "completed")

    def test_message_append_is_deduplicated(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "test.sqlite3")
            store.upsert_conversation("current", "bound-tab")
            self.assertTrue(store.append_message("current", "m1", "assistant", "hello", "hash-1"))
            self.assertFalse(store.append_message("current", "m1", "assistant", "hello", "hash-1"))
            messages = store.list_messages("current")
            self.assertEqual(len(messages), 1)
            self.assertEqual(messages[0]["content"], "hello")

    def test_sequence_cursor(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "test.sqlite3")
            store.append_message("current", "m1", "user", "one", "hash-1")
            store.append_message("current", "m2", "assistant", "two", "hash-2")
            all_messages = store.list_messages("current")
            self.assertEqual(len(all_messages), 2)
            self.assertEqual(len(store.list_messages("current", all_messages[0]["sequence"])), 1)

    def test_streaming_message_updates_in_place(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "test.sqlite3")
            self.assertTrue(store.append_message("current", "m1", "assistant", "hel", "hash-1"))
            self.assertTrue(store.append_message("current", "m1", "assistant", "hello", "hash-2"))
            messages = store.list_messages("current")
            self.assertEqual(len(messages), 1)
            self.assertEqual(messages[0]["content"], "hello")

    def test_same_content_can_be_two_distinct_messages(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "test.sqlite3")
            self.assertTrue(store.append_message("current", "m1", "user", "重复", "same-hash"))
            self.assertTrue(store.append_message("current", "m2", "user", "重复", "same-hash"))
            self.assertEqual(len(store.list_messages("current")), 2)

    def test_legacy_schema_migrates_before_new_indexes_are_created(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.sqlite3"
            conn = sqlite3.connect(path)
            conn.executescript("""
                CREATE TABLE tasks (
                  request_id TEXT PRIMARY KEY,
                  conversation_id TEXT NOT NULL DEFAULT '',
                  state TEXT NOT NULL,
                  prompt TEXT NOT NULL DEFAULT '',
                  result TEXT NOT NULL DEFAULT '',
                  error_code TEXT NOT NULL DEFAULT '',
                  error_message TEXT NOT NULL DEFAULT '',
                  created_at REAL NOT NULL,
                  updated_at REAL NOT NULL
                );
                CREATE TABLE messages (
                  sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                  message_id TEXT NOT NULL,
                  conversation_id TEXT NOT NULL,
                  role TEXT NOT NULL,
                  content TEXT NOT NULL,
                  content_hash TEXT NOT NULL,
                  observed_at REAL NOT NULL,
                  UNIQUE(conversation_id, message_id),
                  UNIQUE(conversation_id, content_hash)
                );
            """)
            conn.execute("INSERT INTO messages(message_id,conversation_id,role,content,content_hash,observed_at) VALUES('old','current','assistant','old text','old hash',1)")
            conn.commit()
            conn.close()
            store = Store(path)
            self.assertEqual(store.list_messages("current")[0]["content"], "old text")
            self.assertTrue(store.append_message("current", "new", "assistant", "old text", "old hash"))
            migrated = sqlite3.connect(path)
            try:
                columns = {row[1] for row in migrated.execute("PRAGMA table_info(tasks)").fetchall()}
            finally:
                migrated.close()
            self.assertTrue({"target_id", "persona_id", "task_group_id"}.issubset(columns))

    def test_search_filters_text_and_role(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "test.sqlite3")
            store.append_message("one", "u1", "user", "alpha plan", "h1")
            store.append_message("one", "a1", "assistant", "alpha answer", "h2")
            store.append_message("two", "a2", "assistant", "alpha other", "h3")
            found = store.search_messages("one", "answer", "assistant")
            self.assertEqual([item["message_id"] for item in found], ["a1"])

    def test_restart_marks_incomplete_tasks_interrupted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "restart.sqlite3"
            first = Store(path)
            first.create_task("restart-1", "current", "pending", state="running")
            second = Store(path)
            task = second.get_task("restart-1")
            self.assertEqual(task["state"], "interrupted")
            self.assertEqual(task["error_code"], "BRIDGE_RESTART")

    def test_message_retention_filters_by_cutoff_and_conversation(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / "retention.sqlite3")
            store.append_message("old", "m1", "user", "old", "h1", observed_at=10)
            store.append_message("keep", "m2", "user", "keep", "h2", observed_at=100)
            self.assertEqual(store.count_messages_before(50), 1)
            self.assertEqual(store.count_messages_before(200, "keep"), 1)
            self.assertEqual(store.prune_messages_before(50, "old"), 1)
            self.assertEqual(store.list_messages("old"), [])
            self.assertEqual(len(store.list_messages("keep")), 1)


if __name__ == "__main__":
    unittest.main()

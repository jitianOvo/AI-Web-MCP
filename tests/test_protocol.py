import unittest

from gpt_web_mcp.protocol import make_message, text_hash


class ProtocolTests(unittest.TestCase):
    def test_message_has_protocol_envelope(self):
        message = make_message("status", ready=True)
        self.assertEqual(message["type"], "status")
        self.assertEqual(message["ready"], True)
        self.assertIn("protocol_version", message)
        self.assertIn("timestamp", message)

    def test_text_hash_is_stable_and_role_sensitive(self):
        self.assertEqual(text_hash("assistant", "ok"), text_hash("assistant", "ok"))
        self.assertNotEqual(text_hash("assistant", "ok"), text_hash("user", "ok"))


if __name__ == "__main__":
    unittest.main()

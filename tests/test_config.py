import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gpt_web_mcp import config


class ConfigTests(unittest.TestCase):
    def test_first_load_generates_token_and_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_dir = root / "config"
            config_path = config_dir / "config.json"
            with patch.object(config, "CONFIG_DIR", config_dir), patch.object(config, "CONFIG_PATH", config_path):
                value = config.load_config()
            self.assertTrue(value["bridge_token"])
            self.assertEqual(json.loads(config_path.read_text(encoding="utf-8"))["bridge_token"], value["bridge_token"])

    def test_generated_extension_token_matches_local_config(self):
        root = Path(__file__).resolve().parents[1]
        config_path = root / "config" / "config.json"
        extension_path = root / "extension" / "config.js"
        if not config_path.exists() or not extension_path.exists():
            self.skipTest("generated local config is not present")
        config = json.loads(config_path.read_text(encoding="utf-8"))
        extension = extension_path.read_text(encoding="utf-8")
        self.assertIn(str(config["bridge_token"]), extension)


if __name__ == "__main__":
    unittest.main()

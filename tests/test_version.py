import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("bump_version", ROOT / "scripts/bump_version.py")
VERSION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERSION)


class VersionTests(unittest.TestCase):
    def setUp(self):
        temporary = ROOT / "tmp"
        temporary.mkdir(exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=temporary)
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.contents = {
            "pyproject.toml": '[project]\r\nname = "fixture"\r\nversion = "1.0.0"\r\n',
            "src/gpt_web_mcp/__init__.py": '__version__ = "1.0.0"\nPROTOCOL_VERSION = "1.0"\n',
            "extension/manifest.json": '{"manifest_version": 3, "version": "1.0.0"}\n',
            "launcher/main.cpp": 'const auto text = L"版本 1.0.0\\r\\n\\r\\n";\r\n',
        }
        for filename, content in self.contents.items():
            target = self.root / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content.encode("utf-8"))

    def test_project_versions_are_consistent(self):
        version, _ = VERSION.inspect_versions(ROOT)
        VERSION.parse_version(version)

    def test_check_is_read_only(self):
        self.assertEqual(VERSION.inspect_versions(self.root)[0], "1.0.0")
        for filename, content in self.contents.items():
            self.assertEqual((self.root / filename).read_bytes(), content.encode("utf-8"))

    def test_patch_and_minor_update_all_fields_and_preserve_other_text(self):
        self.assertEqual(VERSION.bump_version("patch", self.root), "1.0.1")
        self.assertEqual(VERSION.inspect_versions(self.root)[0], "1.0.1")
        self.assertEqual(VERSION.bump_version("minor", self.root), "1.1.0")
        for filename, original in self.contents.items():
            self.assertEqual((self.root / filename).read_bytes(), original.replace("1.0.0", "1.1.0").encode("utf-8"))

    def test_mismatch_and_overflow_do_not_write_files(self):
        target = self.root / "extension/manifest.json"
        target.write_text('{"version": "1.0.1"}', encoding="utf-8")
        before = {filename: (self.root / filename).read_bytes() for filename in self.contents}
        with self.assertRaisesRegex(ValueError, "版本不一致"):
            VERSION.bump_version("minor", self.root)
        self.assertEqual(before, {filename: (self.root / filename).read_bytes() for filename in self.contents})
        for filename, content in self.contents.items():
            (self.root / filename).write_bytes(content.replace("1.0.0", "1.65535.65535").encode("utf-8"))
        with self.assertRaises(ValueError):
            VERSION.bump_version("minor", self.root)
        with self.assertRaises(ValueError):
            VERSION.bump_version("patch", self.root)
        self.assertEqual(VERSION.inspect_versions(self.root)[0], "1.65535.65535")

    def test_invalid_pep440_chrome_versions_are_rejected(self):
        for version in ("1.0", "1.0.0.0", "01.0.0", "1.0.0rc1", "1.0.0+local", "-1.0.0", "1.65536.0", "0.0.0"):
            with self.subTest(version=version), self.assertRaises(ValueError):
                VERSION.parse_version(version)


if __name__ == "__main__":
    unittest.main()

"""Keep the package, bridge, extension and launcher on one release version."""

from __future__ import annotations

import argparse
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
VERSION_FIELDS = {
    "pyproject.toml": re.compile(r'(?m)^(version\s*=\s*")([^"\r\n]+)(")'),
    "src/gpt_web_mcp/__init__.py": re.compile(r'(?m)^(__version__\s*=\s*")([^"\r\n]+)(")'),
    "extension/manifest.json": re.compile(r'("version"\s*:\s*")([^"\r\n]+)(")'),
    "launcher/main.cpp": re.compile(r'(L"版本 )([^\\"\r\n]+)(\\r\\n\\r\\n")'),
}


def parse_version(version: str) -> tuple[int, int, int]:
    """The canonical three-integer subset is valid for PEP 440 and Chrome."""
    if not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version):
        raise ValueError(f"版本必须为无前导零的三段整数：{version!r}")
    parts = tuple(int(part) for part in version.split("."))
    if any(part > 65535 for part in parts) or not any(parts):
        raise ValueError(f"Chrome 版本每段须为 0..65535，且不能全为零：{version}")
    return parts


def inspect_versions(root: Path = ROOT) -> tuple[str, dict[str, str]]:
    contents: dict[str, str] = {}
    versions: dict[str, str] = {}
    for filename, pattern in VERSION_FIELDS.items():
        # Byte I/O preserves the original CRLF/LF convention during updates.
        contents[filename] = (root / filename).read_bytes().decode("utf-8")
        matches = list(pattern.finditer(contents[filename]))
        if len(matches) != 1:
            raise ValueError(f"{filename} 必须恰好包含一个版本字段，实际 {len(matches)} 个")
        versions[filename] = matches[0].group(2)
        parse_version(versions[filename])
    if len(set(versions.values())) != 1:
        raise ValueError("版本不一致，未写入任何文件：" + ", ".join(f"{name}={value}" for name, value in versions.items()))
    return next(iter(versions.values())), contents


def bump_version(kind: str, root: Path = ROOT) -> str:
    current, contents = inspect_versions(root)
    major, minor, patch = parse_version(current)
    if kind == "minor":
        new_version = f"{major}.{minor + 1}.0"
    elif kind == "patch":
        new_version = f"{major}.{minor}.{patch + 1}"
    else:
        raise ValueError("升版类型必须为 minor 或 patch")
    parse_version(new_version)
    updates = {
        filename: VERSION_FIELDS[filename].sub(lambda match: match.group(1) + new_version + match.group(3), content)
        for filename, content in contents.items()
    }
    for filename, content in updates.items():
        (root / filename).write_bytes(content.encode("utf-8"))
    return new_version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", nargs="?", choices=("minor", "patch"), help="普通交付用 minor；临时小错误用 patch")
    parser.add_argument("--check", action="store_true", help="只检查四处版本一致与格式，不修改文件")
    args = parser.parse_args(argv)
    if bool(args.kind) == args.check:
        parser.error("指定 minor、patch 或 --check 中的一项")
    try:
        version = inspect_versions()[0] if args.check else bump_version(args.kind)
    except (OSError, UnicodeError, ValueError) as error:
        print(f"version_check=failed: {error}")
        return 1
    print(f"version={version} {'check=passed' if args.check else 'updated=4'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

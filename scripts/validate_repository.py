#!/usr/bin/env python3
"""Deterministic repository checks for Zari Robot Project Builder."""

from __future__ import annotations

import argparse
import math
import re
import sys
from html import unescape as html_unescape
from pathlib import Path
from urllib.parse import unquote, urlsplit


REQUIRED_ROOT_FILES = (
    "README.md",
    "LICENSE",
    "CONTRIBUTING.md",
    "SECURITY.md",
    ".gitignore",
    ".github/workflows/validate.yml",
    "tests/forward-tests.md",
    "tests/forward-test-report.md",
    "tests/adversarial-review-report.md",
    "tests/test_validate_repository.py",
)

REQUIRED_SKILL_FILES = (
    "SKILL.md",
    "agents/openai.yaml",
    "references/discovery-interview.md",
    "references/project-scaffolding.md",
    "references/roadmap-selection.md",
    "references/sourcing-and-compatibility.md",
    "references/robotics-safety.md",
    "references/beginner-hardware-guidance.md",
    "references/validation.md",
    "assets/templates/project-brief.md",
    "assets/templates/hardware-inventory.md",
    "assets/templates/compatibility-matrix.md",
    "assets/templates/roadmap.md",
    "assets/templates/safety-plan.md",
    "assets/templates/next-step-walkthrough.md",
)

PORTABILITY_PATTERNS = {
    "client name Codex": re.compile(r"\bcodex\b", re.IGNORECASE),
    "client name Claude": re.compile(r"\bclaude\b", re.IGNORECASE),
    "client name Gemini": re.compile(r"\bgemini\b", re.IGNORECASE),
    "client name Copilot": re.compile(r"\bcopilot\b", re.IGNORECASE),
    "Codex-specific path": re.compile(r"\.codex(?:/|\\\\)"),
    "Claude-specific path": re.compile(r"\.claude(?:/|\\\\)"),
    "Gemini-specific path": re.compile(r"\.gemini(?:/|\\\\)"),
    "client-specific user-input tool": re.compile(r"\b(?:request_user_input|get_user_input)\b"),
    "machine-specific macOS path": re.compile(r"/Users/[^/\s]+/"),
    "machine-specific Linux path": re.compile(r"(?:/home/[^/\s]+/|/root/)"),
    "machine-specific Windows path": re.compile(r"[A-Za-z]:\\Users\\", re.IGNORECASE),
    "shell-specific preapproval syntax": re.compile(r"\bBash\([^\n]*\)"),
}

SECRET_PATTERNS = {
    "OpenAI-style secret": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "GitHub fine-grained token": re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "Slack token": re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b"),
    "Slack webhook": re.compile(r"https://hooks\.slack\.com/services/[A-Za-z0-9/_-]{20,}"),
    "OAuth access token": re.compile(r"\bya29\.[0-9A-Za-z_-]{20,}\b"),
    "JWT": re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}

MARKDOWN_REFERENCE_DEFINITION = re.compile(
    r"(?m)^[ \t]{0,3}\[(?!\^)[^\]\n]+\]:[ \t]*(<[^>\n]+>|[^\s\n]+)"
)
MARKDOWN_FENCE_START = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")
MARKDOWN_ATX_HEADING = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+(.+?)\s*$")
MARKDOWN_SETEXT_HEADING = re.compile(r"^[ \t]{0,3}(?:=+|-+)[ \t]*$")
MARKDOWN_HTML_TAG = re.compile(r"<[A-Za-z][^<>]*>", re.DOTALL)
MARKDOWN_HTML_ANCHOR = re.compile(
    r"""(?<![\w:-])(?:id|name)\s*=\s*(?:(["'])(.*?)\1|([^\s"'=<>`]+))""",
    re.IGNORECASE | re.DOTALL,
)
MARKDOWN_HTML_TARGET = re.compile(
    r"""(?<![\w:-])(?:href|src)\s*=\s*(?:(["'])(.*?)\1|([^\s"'=<>`]+))""",
    re.IGNORECASE | re.DOTALL,
)
MARKDOWN_BACKSLASH_ESCAPE = re.compile(
    r"""\\([!"#$%&'()*+,\-./:;<=>?@\[\]\\^_`{|}~])"""
)
URI_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
IGNORED_DIRECTORY_NAMES = frozenset({".git", ".pytest_cache", ".venv", "__pycache__", "venv"})


def parse_frontmatter(path: Path) -> tuple[dict[str, str], str, list[str]]:
    """Parse the intentionally simple scalar YAML frontmatter used by this skill."""

    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        return {}, text, [f"{path}: frontmatter must start on line 1"]

    try:
        end = lines.index("---", 1)
    except ValueError:
        return {}, text, [f"{path}: closing frontmatter delimiter is missing"]

    data: dict[str, str] = {}
    for line_number, line in enumerate(lines[1:end], start=2):
        if not line.strip():
            continue
        if ":" not in line or line.startswith((" ", "\t", "-")):
            errors.append(f"{path}:{line_number}: unsupported or invalid frontmatter line")
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value:
            errors.append(f"{path}:{line_number}: frontmatter key and value must be non-empty")
            continue
        if key in data:
            errors.append(f"{path}:{line_number}: duplicate frontmatter key {key!r}")
            continue
        if value[:1] == value[-1:] and value[:1] in {"'", '"'}:
            value = value[1:-1]
        data[key] = value

    body = "\n".join(lines[end + 1 :])
    return data, body, errors


def is_ignored_repository_path(path: Path, root: Path) -> bool:
    """Return whether a path belongs to generated repository-local state."""

    return any(part in IGNORED_DIRECTORY_NAMES for part in path.relative_to(root).parts)


def markdown_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in {".md", ".markdown"}
        and not is_ignored_repository_path(path, root)
    )


def markdown_searchable_text(text: str, *, mask_inline_code: bool = True) -> str:
    """Mask literal Markdown regions while preserving offsets and line structure."""

    characters = list(text)
    lines_with_endings = text.splitlines(keepends=True)
    if lines_with_endings and lines_with_endings[0].strip() == "---":
        offset = len(lines_with_endings[0])
        frontmatter_end = 0
        for line in lines_with_endings[1:]:
            offset += len(line)
            if line.strip() in {"---", "..."}:
                frontmatter_end = offset
                break
        for index in range(frontmatter_end):
            if characters[index] not in "\r\n":
                characters[index] = " "

    offset = 0
    fence_character: str | None = None
    fence_length = 0

    for line in text.splitlines(keepends=True):
        content = line.rstrip("\r\n")
        if fence_character is None:
            match = MARKDOWN_FENCE_START.match(content)
            if match:
                fence = match.group(1)
                fence_character = fence[0]
                fence_length = len(fence)
        else:
            closing_fence = re.compile(
                rf"^[ \t]{{0,3}}{re.escape(fence_character)}{{{fence_length},}}[ \t]*$"
            )
            if closing_fence.match(content):
                fence_character = None
                fence_length = 0

        if fence_character is not None or MARKDOWN_FENCE_START.match(content):
            for index in range(offset, offset + len(line)):
                if characters[index] not in "\r\n":
                    characters[index] = " "
        offset += len(line)

    literal_characters = characters.copy()
    masked = "".join(literal_characters)
    index = 0
    while index < len(masked):
        if masked[index] != "`":
            index += 1
            continue
        run_end = index
        while run_end < len(masked) and masked[run_end] == "`":
            run_end += 1
        delimiter = masked[index:run_end]
        search_from = run_end
        closing = -1
        while True:
            candidate = masked.find(delimiter, search_from)
            if candidate == -1:
                break
            before_is_tick = candidate > 0 and masked[candidate - 1] == "`"
            after = candidate + len(delimiter)
            after_is_tick = after < len(masked) and masked[after] == "`"
            if not before_is_tick and not after_is_tick:
                closing = candidate
                break
            search_from = candidate + len(delimiter)
        if closing == -1:
            index = run_end
            continue
        for position in range(index, closing + len(delimiter)):
            if literal_characters[position] not in "\r\n":
                literal_characters[position] = " "
        index = closing + len(delimiter)
        masked = "".join(literal_characters)

    if mask_inline_code:
        characters = literal_characters.copy()

    for comment in re.finditer(r"<!--.*?(?:-->|$)", masked, re.DOTALL):
        for position in range(comment.start(), comment.end()):
            if characters[position] not in "\r\n":
                characters[position] = " "

    for index, character in enumerate(characters):
        if character not in {"[", "<"}:
            continue
        preceding_backslashes = 0
        cursor = index - 1
        while cursor >= 0 and characters[cursor] == "\\":
            preceding_backslashes += 1
            cursor -= 1
        if preceding_backslashes % 2 == 1:
            characters[index] = " "

    return "".join(characters)


def html_attribute_values(text: str, pattern: re.Pattern[str]) -> list[str]:
    """Collect matching HTML attribute values from rendered raw tags."""

    values: list[str] = []
    for tag in MARKDOWN_HTML_TAG.finditer(text):
        for attribute in pattern.finditer(tag.group(0)):
            value = attribute.group(2) if attribute.group(1) else attribute.group(3)
            values.append(value)
    return values


def markdown_label_end(text: str, start: int) -> int | None:
    """Find a label's closing bracket while respecting nested image/link labels."""

    depth = 1
    index = start + 1
    while index < len(text):
        character = text[index]
        if character == "\\":
            index += 2
            continue
        if character == "[":
            depth += 1
        elif character == "]":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def markdown_destination_end(text: str, opening: int) -> tuple[str, int] | None:
    """Extract a parenthesized destination with balanced nested parentheses."""

    start = opening + 1
    index = start
    depth = 1
    in_angle_destination = False
    title_quote: str | None = None

    while index < len(text):
        character = text[index]
        if character == "\\":
            index += 2
            continue
        if in_angle_destination:
            if character == ">":
                in_angle_destination = False
            index += 1
            continue
        if title_quote:
            if character == title_quote:
                title_quote = None
            index += 1
            continue
        if character == "<" and not text[start:index].strip():
            in_angle_destination = True
        elif character in {'"', "'"} and index > start and text[index - 1].isspace():
            title_quote = character
        elif character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return text[start:index], index
        index += 1
    return None


def markdown_link_targets(text: str) -> list[tuple[str, bool]]:
    """Extract Markdown and rendered raw-HTML destinations."""

    text = markdown_searchable_text(text)
    targets: list[tuple[str, bool]] = []
    for label_start, character in enumerate(text):
        if character != "[":
            continue
        label_end = markdown_label_end(text, label_start)
        if label_end is None or label_end + 1 >= len(text) or text[label_end + 1] != "(":
            continue
        destination = markdown_destination_end(text, label_end + 1)
        if destination is not None:
            targets.append((destination[0], True))

    targets.extend(
        (target, True) for target in MARKDOWN_REFERENCE_DEFINITION.findall(text)
    )
    targets.extend(
        (target, False) for target in html_attribute_values(text, MARKDOWN_HTML_TARGET)
    )
    return targets


def github_heading_slug(heading: str) -> str:
    """Approximate GitHub's generated heading IDs for ordinary Markdown headings."""

    heading = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", heading)
    heading = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", heading)
    heading = re.sub(r"<[^>]+>", "", heading)
    heading = re.sub(r"[\*_~`]", "", heading).lower()
    characters = [
        character
        for character in heading
        if character.isalnum() or character in {"-", "_"} or character.isspace()
    ]
    return re.sub(r"\s+", "-", "".join(characters).strip())


def markdown_heading_fragments(text: str) -> set[str]:
    """Collect generated heading fragments and explicit HTML anchors outside fences."""

    fragments: set[str] = set()
    used_slugs: set[str] = set()
    setext_candidate: str | None = None

    def add_heading(heading: str) -> None:
        heading = re.sub(r"[ \t]+#+[ \t]*$", "", heading)
        base = github_heading_slug(heading)
        if not base:
            return
        candidate = base
        duplicate_index = 0
        while candidate in used_slugs:
            duplicate_index += 1
            candidate = f"{base}-{duplicate_index}"
        used_slugs.add(candidate)
        fragments.add(candidate)

    lines = text.splitlines()
    searchable_text = markdown_searchable_text(text)
    structure_lines = markdown_searchable_text(text, mask_inline_code=False).splitlines()
    for anchor in html_attribute_values(searchable_text, MARKDOWN_HTML_ANCHOR):
        fragments.add(html_unescape(anchor))
    content_start = 0
    if lines and lines[0].strip() == "---":
        for line_index, line in enumerate(lines[1:], start=1):
            if line.strip() in {"---", "..."}:
                content_start = line_index + 1
                break

    for line_index, line in enumerate(lines[content_start:], start=content_start):
        structure_line = structure_lines[line_index]
        atx_heading = MARKDOWN_ATX_HEADING.match(structure_line)
        if atx_heading:
            raw_heading = MARKDOWN_ATX_HEADING.match(line)
            add_heading(raw_heading.group(1) if raw_heading else atx_heading.group(1))
            setext_candidate = None
            continue
        if MARKDOWN_SETEXT_HEADING.match(structure_line) and setext_candidate:
            add_heading(setext_candidate)
            setext_candidate = None
            continue
        setext_candidate = line.strip() if structure_line.strip() else None

    return fragments


def find_broken_links(root: Path) -> list[str]:
    errors: list[str] = []
    skill_root = (root / "build-robot-project").resolve()
    fragment_cache: dict[Path, set[str]] = {}
    for path in markdown_files(root):
        text = path.read_text(encoding="utf-8")
        for raw_target, is_markdown in markdown_link_targets(text):
            target = raw_target.strip()
            if is_markdown:
                if target.startswith("<") and ">" in target:
                    target = target[1 : target.index(">")]
                else:
                    target = target.split(maxsplit=1)[0]
                target = MARKDOWN_BACKSLASH_ESCAPE.sub(r"\1", target)
            target = html_unescape(target)
            if not target or target.startswith("//") or URI_SCHEME.match(target):
                continue
            parsed_target = urlsplit(target)
            path_target = unquote(parsed_target.path)
            fragment = unquote(parsed_target.fragment)
            resolved = (path.parent / path_target).resolve() if path_target else path.resolve()
            if path.resolve().is_relative_to(skill_root) and not resolved.is_relative_to(skill_root):
                errors.append(
                    f"{path.relative_to(root)}: relative link escapes distributable skill "
                    f"directory {raw_target!r}"
                )
                continue
            if not resolved.exists():
                errors.append(f"{path.relative_to(root)}: broken relative link {raw_target!r}")
                continue
            if fragment and resolved.is_file() and resolved.suffix.lower() in {".md", ".markdown"}:
                if resolved not in fragment_cache:
                    fragment_cache[resolved] = markdown_heading_fragments(
                        resolved.read_text(encoding="utf-8")
                    )
                if fragment not in fragment_cache[resolved]:
                    errors.append(
                        f"{path.relative_to(root)}: broken Markdown fragment "
                        f"#{fragment!s} in {raw_target!r}"
                    )
    return errors


def find_portability_violations(skill_root: Path) -> list[str]:
    errors: list[str] = []
    portable_paths = [skill_root / "SKILL.md"]
    portable_paths.extend((skill_root / "references").rglob("*"))
    portable_paths.extend((skill_root / "assets").rglob("*"))
    portable_paths.extend((skill_root / "scripts").rglob("*"))
    for path in sorted(path for path in portable_paths if path.is_file()):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in PORTABILITY_PATTERNS.items():
            match = pattern.search(text)
            if match:
                line = text.count("\n", 0, match.start()) + 1
                errors.append(f"{path.relative_to(skill_root)}:{line}: {label} in portable core")
    return errors


def find_secret_like_content(root: Path) -> list[str]:
    errors: list[str] = []
    for path in sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and not is_ignored_repository_path(path, root)
        and not is_ignored_secret_file(path)
    ):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                errors.append(f"{path.relative_to(root)}: possible {label}")
    return errors


def is_ignored_secret_file(path: Path) -> bool:
    """Return whether a local credential file is explicitly excluded from version control."""

    name = path.name
    return (
        name == ".env"
        or (name.startswith(".env.") and name != ".env.example")
        or path.suffix.lower() in {".key", ".pem"}
    )


def find_empty_resources(root: Path) -> list[str]:
    errors: list[str] = []
    for path in sorted(
        path for path in root.rglob("*") if not is_ignored_repository_path(path, root)
    ):
        if path.is_file() and path.stat().st_size == 0:
            errors.append(f"empty file: {path.relative_to(root)}")
        if path.is_dir() and not any(path.iterdir()):
            errors.append(f"empty directory: {path.relative_to(root)}")
    return errors


def validate_repository(root: Path) -> list[str]:
    errors: list[str] = []
    skill_root = root / "build-robot-project"

    for relative in REQUIRED_ROOT_FILES:
        if not (root / relative).is_file():
            errors.append(f"missing required repository file: {relative}")
    for relative in REQUIRED_SKILL_FILES:
        if not (skill_root / relative).is_file():
            errors.append(f"missing required skill file: build-robot-project/{relative}")

    skill_file = skill_root / "SKILL.md"
    if skill_file.is_file():
        data, body, frontmatter_errors = parse_frontmatter(skill_file)
        errors.extend(frontmatter_errors)
        if set(data) != {"name", "description"}:
            errors.append("SKILL.md frontmatter must contain only name and description")
        name = data.get("name", "")
        description = data.get("description", "")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
            errors.append("SKILL.md name must use lowercase letters, digits, and interior hyphens")
        if name != skill_root.name:
            errors.append("SKILL.md name must match its parent directory")
        if not 1 <= len(name) <= 64:
            errors.append("SKILL.md name must be 1-64 characters")
        if not 1 <= len(description) <= 1024:
            errors.append("SKILL.md description must be 1-1024 characters")
        line_count = len(skill_file.read_text(encoding="utf-8").splitlines())
        if line_count >= 500:
            errors.append(f"SKILL.md must stay below 500 lines; found {line_count}")
        estimated_tokens = math.ceil(len(body) / 4)
        if estimated_tokens >= 5000:
            errors.append(f"SKILL.md estimated token count must stay below 5000; found {estimated_tokens}")

    errors.extend(find_empty_resources(root))
    errors.extend(find_broken_links(root))
    if skill_root.is_dir():
        errors.extend(find_portability_violations(skill_root))
    errors.extend(find_secret_like_content(root))
    return sorted(set(errors))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (defaults to this script's parent repository)",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()
    errors = validate_repository(root)
    if errors:
        print(f"Validation failed with {len(errors)} issue(s):")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Repository validation passed:")
    print("- required repository and skill files exist")
    print("- SKILL.md metadata, name, and size budgets pass")
    print("- relative Markdown links resolve")
    print("- portable core contains no known client-specific assumptions")
    print("- no empty resources or lightweight secret patterns were found (Gitleaks runs in CI)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

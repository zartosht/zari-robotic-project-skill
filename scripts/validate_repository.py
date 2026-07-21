#!/usr/bin/env python3
"""Deterministic repository checks for Zari Robot Project Builder."""

from __future__ import annotations

import argparse
import math
import re
import sys
import unicodedata
from bisect import bisect_left, bisect_right
from html import unescape as html_unescape
from html.entities import html5 as HTML5_ENTITIES
from html.parser import HTMLParser
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
    "machine-specific macOS path": re.compile(
        r"/Users/[^/\s]+(?=/|[\s)\]}>.,;:!?]|$)"
    ),
    "machine-specific Linux path": re.compile(
        r"(?:/home/[^/\s]+(?=/|[\s)\]}>.,;:!?]|$)|"
        r"/root(?=/|[\s)\]}>.,;:!?]|$))"
    ),
    "machine-specific Windows path": re.compile(
        r"[A-Za-z]:[\\/]Users[\\/]", re.IGNORECASE
    ),
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
    r"(?m)^[ \t]{0,3}\[(?!\^)(?P<label>(?:\\.|[^\[\]\\\n]|\n(?![ \t]*\n))+)\]:[ \t]*"
    r"(?:\n[ \t]{0,3})?"
    r"(?P<target><(?:\\.|[^<>\\\n])*>|(?:\\.|[^\s\\<>])+)"
    r"(?:(?:[ \t]+|\n[ \t]{0,3})(?:"
    r"\"(?:\\.|[^\"\\\n]|\n(?=[ \t]*\S))*\"|"
    r"'(?:\\.|[^'\\\n]|\n(?=[ \t]*\S))*'|"
    r"\((?:\\.|[^()\\\n]|\n(?=[ \t]*\S))*\)))?[ \t]*(?=\n|$)"
)
MARKDOWN_FOOTNOTE_DEFINITION = re.compile(
    r"(?m)^[ \t]{0,3}\[\^(?P<label>(?:\\.|[^\]\\\r\n])+)\]:"
)
MARKDOWN_FOOTNOTE_REFERENCE = re.compile(
    r"\[\^(?P<label>(?:\\.|[^\]\\\r\n])+)\](?!:)"
)
MARKDOWN_BLOCKQUOTE_PREFIX = re.compile(r"^ {0,3}>[ \t]?")
MARKDOWN_LIST_PREFIX = re.compile(
    r"^(?P<indent> {0,3})(?P<marker>[*+-]|\d{1,9}[.)])"
    r"(?P<padding>[ \t]+|$)"
)
MARKDOWN_INDENTED_CODE = re.compile(r"^(?: {4,}| {0,3}\t)")
MARKDOWN_FENCE_START = re.compile(r"^ {0,3}(`{3,}|~{3,})")
MARKDOWN_ATX_HEADING = re.compile(
    r"^[ \t]{0,3}#{1,6}(?:[ \t]+(.*?))?[ \t]*$"
)
MARKDOWN_SETEXT_HEADING = re.compile(r"^[ \t]{0,3}(?:=+|-+)[ \t]*$")
MARKDOWN_THEMATIC_BREAK = re.compile(
    r"^[ \t]{0,3}(?:(?:\*[ \t]*){3,}|(?:_[ \t]*){3,}|(?:-[ \t]*){3,})$"
)
MARKDOWN_HTML_ATTRIBUTE_NAME = r"[A-Za-z_:][A-Za-z0-9_.:-]*"
MARKDOWN_HTML_ATTRIBUTE_VALUE = r'''(?:[^\s"'=<>`]+|"[^"]*"|'[^']*')'''
MARKDOWN_HTML_TAG = re.compile(
    rf"<[A-Za-z][A-Za-z0-9-]*"
    rf"(?:[ \t\r\n]+{MARKDOWN_HTML_ATTRIBUTE_NAME}"
    rf"(?:[ \t\r\n]*=[ \t\r\n]*{MARKDOWN_HTML_ATTRIBUTE_VALUE})?)*"
    rf"[ \t\r\n]*/?>"
)
MARKDOWN_HTML_TAG_OR_CLOSING = re.compile(
    rf"(?:{MARKDOWN_HTML_TAG.pattern}|</[A-Za-z][A-Za-z0-9-]*[ \t\r\n]*>)"
)
MARKDOWN_HTML_RAW_TEXT_OR_RCDATA_TAGS = frozenset(
    {
        "iframe",
        "noembed",
        "noframes",
        "script",
        "style",
        "textarea",
        "title",
        "xmp",
    }
)
MARKDOWN_RAW_HTML_TYPE_1 = re.compile(
    r"^[ \t]{0,3}<(?P<tag>script|pre|style|textarea)(?=[\s>]|\Z)", re.IGNORECASE
)
MARKDOWN_RAW_HTML_TYPE_6 = re.compile(
    r"^[ \t]{0,3}</?(?:address|article|aside|base|basefont|blockquote|body|caption|"
    r"center|col|colgroup|dd|details|dialog|dir|div|dl|dt|fieldset|figcaption|"
    r"figure|footer|form|frame|frameset|h[1-6]|head|header|hr|html|iframe|legend|"
    r"li|link|main|menu|menuitem|nav|noframes|ol|optgroup|option|p|param|search|"
    r"section|summary|table|tbody|td|tfoot|th|thead|title|tr|track|ul)(?=[\s/>]|\Z)",
    re.IGNORECASE,
)
MARKDOWN_RAW_HTML_TYPE_7 = re.compile(
    rf"^[ \t]{{0,3}}(?:"
    rf"<[A-Za-z][A-Za-z0-9-]*(?:[ \t]+{MARKDOWN_HTML_ATTRIBUTE_NAME}"
    rf"(?:[ \t]*=[ \t]*{MARKDOWN_HTML_ATTRIBUTE_VALUE})?)*[ \t]*/?>|"
    rf"</[A-Za-z][A-Za-z0-9-]*[ \t]*>)[ \t]*$"
)
MARKDOWN_CODE_SPAN_LT = "\ue000"
MARKDOWN_CODE_SPAN_GT = "\ue001"
MARKDOWN_ESCAPED_LBRACKET = "\ue002"
MARKDOWN_ESCAPED_LT = "\ue003"
MARKDOWN_AUTOLINK = re.compile(
    r"<((?:[A-Za-z][A-Za-z0-9+.-]{1,31}:[^<>\s]*)|(?:[^<>\s@]+@[^<>\s@]+))>"
)
MARKDOWN_HTML_ID_ATTRIBUTES = frozenset({"id"})
MARKDOWN_HTML_NAME_ATTRIBUTES = frozenset({"name"})
MARKDOWN_HTML_LEGACY_ANCHOR_TAGS = frozenset({"a"})
MARKDOWN_HTML_HREF_ATTRIBUTES = frozenset({"href"})
MARKDOWN_HTML_HREF_TAGS = frozenset({"a", "area", "link"})
MARKDOWN_HTML_SRC_ATTRIBUTES = frozenset({"src"})
MARKDOWN_HTML_SRC_TAGS = frozenset(
    {
        "audio",
        "embed",
        "frame",
        "iframe",
        "img",
        "script",
        "source",
        "track",
        "video",
    }
)
MARKDOWN_HTML_INPUT_TAGS = frozenset({"input"})
MARKDOWN_HTML_IMAGE_INPUT_TYPES = frozenset({"image"})
MARKDOWN_HTML_DATA_ATTRIBUTES = frozenset({"data"})
MARKDOWN_HTML_DATA_TAGS = frozenset({"object"})
MARKDOWN_HTML_POSTER_ATTRIBUTES = frozenset({"poster"})
MARKDOWN_HTML_POSTER_TAGS = frozenset({"video"})
MARKDOWN_HTML_SRCSET_ATTRIBUTES = frozenset({"srcset"})
MARKDOWN_HTML_SRCSET_TAGS = frozenset({"img", "source"})
MARKDOWN_HTML_SRCDOC_ATTRIBUTES = frozenset({"srcdoc"})
MARKDOWN_HTML_SRCDOC_TAGS = frozenset({"iframe"})
MARKDOWN_BACKSLASH_ESCAPE = re.compile(
    r"""\\([!"#$%&'()*+,\-./:;<=>?@\[\]\\^_`{|}~])"""
)
MARKDOWN_CHARACTER_REFERENCE = re.compile(
    r"&(?:#[xX][0-9A-Fa-f]{1,8}|#[0-9]{1,8}|[A-Za-z][A-Za-z0-9]{1,31});"
)
MARKDOWN_PARAGRAPH_BOUNDARY = re.compile(
    r"(?:\r\n|\r(?!\n)|\n)[ \t]*(?:\r\n|\r(?!\n)|\n)"
)
MARKDOWN_REFERENCE_LABEL_MAX_LENGTH = 999
HTML_NUMERIC_CHARACTER_REFERENCE = re.compile(
    r"&#(?:[xX][0-9A-Fa-f]+|[0-9]+);?"
)
HTML_FLOATING_POINT_NUMBER = re.compile(
    r"-?(?:(?:[0-9]+(?:\.[0-9]+)?)|(?:\.[0-9]+))"
    r"(?:[eE][+-]?[0-9]+)?"
)
HTML_ASCII_WHITESPACE = frozenset("\t\n\f\r ")
HTML_CHARACTER_REFERENCE_MAX_LENGTH = max(len(name) for name in HTML5_ENTITIES)
URI_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
CSS_IMPORT_RULE = re.compile(r"@import(?![-_A-Za-z0-9])", re.IGNORECASE)
CSS_URL_FUNCTION = re.compile(r"url\(", re.IGNORECASE)
IGNORED_DIRECTORY_NAMES = frozenset({".git", ".pytest_cache", ".venv", "__pycache__", "venv"})
MARKDOWN_SUFFIXES = frozenset(
    {
        ".md",
        ".markdown",
        ".mdown",
        ".mdtext",
        ".mdtxt",
        ".mdwn",
        ".mkd",
        ".mkdn",
        ".mkdown",
    }
)
PORTABLE_TEXT_SUFFIXES = frozenset(
    {
        ".cfg",
        ".csv",
        ".ini",
        ".js",
        ".json",
        ".ps1",
        ".psm1",
        ".py",
        ".sh",
        ".toml",
        ".ts",
        ".txt",
        ".yaml",
        ".yml",
    }
) | MARKDOWN_SUFFIXES


def parse_frontmatter(path: Path) -> tuple[dict[str, str], str, list[str]]:
    """Parse the intentionally simple scalar YAML frontmatter used by this skill."""

    errors: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return {}, "", [f"{path}: SKILL.md must be valid UTF-8"]
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


def path_resolves_within(path: Path, root: Path) -> bool:
    """Return whether a path resolves inside the expected repository boundary."""

    try:
        return path.resolve().is_relative_to(root.resolve())
    except (OSError, RuntimeError):
        return False


def find_escaping_skill_symlinks(skill_root: Path) -> list[str]:
    """Reject distributable symlinks that resolve outside the skill directory."""

    expected_boundary = skill_root.parent.resolve() / skill_root.name
    if skill_root.is_symlink():
        entries = [skill_root]
    elif skill_root.is_dir():
        entries = list(skill_root.rglob("*"))
    else:
        return []

    errors: list[str] = []
    for path in sorted(entry for entry in entries if entry.is_symlink()):
        relative = path.relative_to(skill_root.parent)
        try:
            target = path.readlink()
        except OSError:
            errors.append(f"{relative}: symlink target cannot be read")
            continue
        if not path.exists():
            errors.append(f"{relative}: symlink target does not exist")
            continue
        try:
            resolves_within_skill = path.resolve().is_relative_to(expected_boundary)
        except (OSError, RuntimeError):
            resolves_within_skill = False
        if not resolves_within_skill:
            errors.append(
                f"{relative}: symlink resolves outside distributable skill directory"
            )
        elif target.is_absolute():
            errors.append(f"{relative}: symlink target is absolute and not portable")
    return errors


def decode_text_data(data: bytes) -> str | None:
    """Decode UTF-8 or BOM-marked Unicode text without guessing binary data."""

    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        for byte_order_mark, encoding in (
            (b"\xff\xfe\x00\x00", "utf-32"),
            (b"\x00\x00\xfe\xff", "utf-32"),
            (b"\xff\xfe", "utf-16"),
            (b"\xfe\xff", "utf-16"),
        ):
            if data.startswith(byte_order_mark):
                try:
                    return data.decode(encoding)
                except UnicodeDecodeError:
                    return None
        return None


def data_looks_binary(data: bytes) -> bool:
    """Detect binary payloads without misclassifying BOM-marked Unicode text."""

    unicode_boms = (b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff", b"\xff\xfe", b"\xfe\xff")
    if data.startswith(unicode_boms):
        return False
    sample = data[:8192]
    if b"\x00" in sample:
        return True
    control_bytes = sum(
        byte < 32 and byte not in {8, 9, 10, 12, 13} for byte in sample
    )
    return bool(sample) and control_bytes / len(sample) > 0.3


def markdown_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and path_resolves_within(path, root)
        and path.suffix.lower() in MARKDOWN_SUFFIXES
        and not is_ignored_repository_path(path, root)
    )


def markdown_list_prefix_end(match: re.Match[str]) -> int:
    """Return the content offset for a CommonMark list marker."""

    padding = match.group("padding")
    padding_start = match.start("padding")
    start_column = len(match.string[:padding_start].expandtabs(4))
    padding_columns = (
        len((" " * start_column + padding).expandtabs(4)) - start_column
    )
    consumed_padding = 1 if padding_columns > 4 else len(padding)
    return match.start("padding") + consumed_padding


def markdown_list_prefix_columns(match: re.Match[str]) -> int:
    """Return the visual content column after a CommonMark list marker."""

    return len(match.string[: markdown_list_prefix_end(match)].expandtabs(4))


def markdown_strip_indent_columns(text: str, required_columns: int) -> str | None:
    """Remove required leading columns, expanding tabs at four-column stops."""

    index = 0
    columns = 0
    while index < len(text) and text[index] in " \t" and columns < required_columns:
        if text[index] == "\t":
            columns += 4 - (columns % 4)
        else:
            columns += 1
        index += 1
    if columns < required_columns:
        return None
    return (" " * (columns - required_columns)) + text[index:]


def markdown_blockquote_content(line: str) -> tuple[tuple[str, ...], str]:
    """Remove direct blockquote prefixes while retaining their container context."""

    containers: list[str] = []
    content = line
    while blockquote := MARKDOWN_BLOCKQUOTE_PREFIX.match(content):
        containers.append("blockquote")
        content = content[blockquote.end() :]
    return tuple(containers), content


def markdown_line_starts_list_item(line: str) -> bool:
    """Return whether a line directly opens a list item, including in blockquotes."""

    _, content = markdown_blockquote_content(line)
    return MARKDOWN_LIST_PREFIX.match(content) is not None


def markdown_container_content(line: str) -> tuple[tuple[str, ...], str]:
    """Remove directly expressed blockquote and list container prefixes."""

    containers: list[str] = []
    content = line
    while content:
        blockquote = MARKDOWN_BLOCKQUOTE_PREFIX.match(content)
        if blockquote:
            containers.append("blockquote")
            content = content[blockquote.end() :]
            continue
        list_item = MARKDOWN_LIST_PREFIX.match(content)
        if list_item:
            containers.append("list")
            content = content[markdown_list_prefix_end(list_item) :]
            continue
        break
    return tuple(containers), content


def markdown_container_lines(lines: list[str]) -> list[tuple[tuple[str, ...], str]]:
    """Normalize direct containers and nested-list continuation indentation."""

    normalized: list[tuple[tuple[str, ...], str]] = []
    active_list_indents: list[int] = []
    active_list_parent: tuple[str, ...] | None = None
    for line in lines:
        parent_containers, parent_content = markdown_blockquote_content(line)
        continuation_content: str | None = None
        continuation_depth = 0
        if active_list_parent == parent_containers and parent_content.strip():
            for depth in range(len(active_list_indents), 0, -1):
                candidate = markdown_strip_indent_columns(
                    parent_content, active_list_indents[depth - 1]
                )
                if candidate is not None:
                    continuation_content = candidate
                    continuation_depth = depth
                    break
        is_continuation = (
            continuation_depth > 0
            and active_list_parent == parent_containers
            and continuation_content is not None
            and bool(parent_content.strip())
        )
        if is_continuation:
            active_list_indents = active_list_indents[:continuation_depth]
            nested_containers, content = markdown_container_content(continuation_content)
            normalized.append(
                (
                    (
                        *parent_containers,
                        *("list" for _ in range(continuation_depth)),
                        *nested_containers,
                    ),
                    content,
                )
            )
        else:
            normalized.append(markdown_container_content(line))

        list_item = MARKDOWN_LIST_PREFIX.match(parent_content)
        if list_item:
            active_list_indents = [markdown_list_prefix_columns(list_item)]
            active_list_parent = parent_containers
        elif is_continuation and continuation_content is not None:
            nested_list_item = MARKDOWN_LIST_PREFIX.match(continuation_content)
            if nested_list_item:
                active_list_indents.append(
                    active_list_indents[-1]
                    + markdown_list_prefix_columns(nested_list_item)
                )
        elif parent_content.strip() and not is_continuation:
            active_list_indents = []
            active_list_parent = None

    return normalized


def markdown_fence_container_spec(
    line: str, containers: tuple[str, ...], content: str
) -> tuple[tuple[str, int], ...] | None:
    """Record how each opening container consumes its raw line prefix."""

    prefix_end = len(line) - len(content)
    cursor = 0
    spec: list[tuple[str, int]] = []
    for container in containers:
        remaining = line[cursor:]
        if container == "blockquote":
            blockquote = MARKDOWN_BLOCKQUOTE_PREFIX.match(remaining)
            if not blockquote:
                return None
            cursor += blockquote.end()
            spec.append((container, 0))
            continue
        list_item = MARKDOWN_LIST_PREFIX.match(remaining)
        if list_item:
            raw_indent = markdown_list_prefix_end(list_item)
            indent = markdown_list_prefix_columns(list_item)
        else:
            raw_indent = min(
                len(remaining) - len(remaining.lstrip(" \t")), prefix_end - cursor
            )
            indent = len(remaining[:raw_indent].expandtabs(4))
        if indent <= 0:
            return None
        cursor += raw_indent
        spec.append((container, indent))
    return tuple(spec) if cursor == prefix_end else None


def markdown_fence_container_content(
    line: str, spec: tuple[tuple[str, int], ...]
) -> str | None:
    """Return fence content after only its opening containers are removed."""

    content = line
    for index, (container, indent) in enumerate(spec):
        if container == "blockquote":
            blockquote = MARKDOWN_BLOCKQUOTE_PREFIX.match(content)
            if not blockquote:
                return None
            content = content[blockquote.end() :]
            continue
        if not content.strip():
            if any(kind == "blockquote" for kind, _ in spec[index + 1 :]):
                return None
            return ""
        stripped = markdown_strip_indent_columns(content, indent)
        if stripped is None:
            return None
        content = stripped
    return content


def markdown_fence_opening(content: str) -> re.Match[str] | None:
    """Return a valid CommonMark fenced-code opener, if present."""

    match = MARKDOWN_FENCE_START.match(content)
    if not match:
        return None
    fence = match.group(1)
    info_string = content[match.end() :]
    if fence[0] == "`" and "`" in info_string:
        return None
    return match


def mask_markdown_raw_html_blocks(
    characters: list[str],
    reference_definition_lines: set[int] | None = None,
    style_content_spans: list[tuple[int, int]] | None = None,
) -> None:
    """Mask CommonMark raw HTML block bodies while retaining opening tags."""

    text = "".join(characters)
    lines_with_endings = text.splitlines(keepends=True)
    lines = [line.rstrip("\r\n") for line in lines_with_endings]
    container_lines = markdown_container_lines(lines)
    if reference_definition_lines is None:
        _, reference_definition_lines = markdown_reference_definitions_with_lines(
            lines, container_lines
        )
    line_offsets: list[int] = []
    running_offset = 0
    for line in lines_with_endings:
        line_offsets.append(running_offset)
        running_offset += len(line)
    offset = 0
    skip_until = 0
    blank_block_start: int | None = None
    blank_block_end = len(text)
    open_paragraph_containers: tuple[str, ...] | None = None

    def mask(start: int, end: int) -> None:
        for position in range(start, end):
            if characters[position] not in "\r\n":
                characters[position] = " "

    def mask_except_html_tags(start: int, end: int) -> None:
        quoted_spans: list[tuple[int, int]] = []
        cursor = start
        while cursor < end:
            tag_start = text.find("<", cursor, end)
            if tag_start < 0:
                break
            name_start = tag_start + 1
            if name_start < end and text[name_start] == "/":
                name_start += 1
            if name_start >= end or not (
                text[name_start].isascii() and text[name_start].isalpha()
            ):
                cursor = tag_start + 1
                continue

            index = name_start + 1
            while index < end:
                character = text[index]
                if character in {'"', "'"}:
                    quote = character
                    value_start = index
                    index += 1
                    while index < end and text[index] != quote:
                        index += 1
                    if index >= end:
                        quoted_spans.append((value_start, end))
                        cursor = end
                        break
                    index += 1
                    quoted_spans.append((value_start, index))
                    continue
                if character == ">":
                    cursor = index + 1
                    break
                index += 1
            else:
                cursor = end

        inert_spans = quoted_spans.copy()
        cursor = start
        quote_index = 0
        while cursor < end:
            special_start = text.find("<", cursor, end)
            if special_start < 0:
                break
            while (
                quote_index < len(quoted_spans)
                and quoted_spans[quote_index][1] <= special_start
            ):
                quote_index += 1
            if (
                quote_index < len(quoted_spans)
                and quoted_spans[quote_index][0] <= special_start
            ):
                cursor = quoted_spans[quote_index][1]
                continue
            if text.startswith("<!--", special_start):
                opener_length, closer = 4, "-->"
            elif text.startswith("<?", special_start):
                opener_length, closer = 2, "?>"
            elif text.startswith("<![CDATA[", special_start):
                opener_length = 9
                closer = "]]>"
            elif (
                special_start + 2 < end
                and text.startswith("<!", special_start)
                and "A" <= text[special_start + 2] <= "Z"
            ):
                opener_length, closer = 3, ">"
            else:
                cursor = special_start + 1
                continue
            special_end = text.find(closer, special_start + opener_length, end)
            if special_end < 0:
                inert_spans.append((special_start, end))
                break
            special_end += len(closer)
            inert_spans.append((special_start, special_end))
            cursor = special_end

        merged_spans: list[tuple[int, int]] = []
        for span_start, span_end in sorted(inert_spans):
            if merged_spans and span_start <= merged_spans[-1][1]:
                merged_spans[-1] = (
                    merged_spans[-1][0],
                    max(merged_spans[-1][1], span_end),
                )
            else:
                merged_spans.append((span_start, span_end))

        cursor = start
        span_index = 0
        for tag in MARKDOWN_HTML_TAG_OR_CLOSING.finditer(text, start, end):
            while (
                span_index < len(merged_spans)
                and merged_spans[span_index][1] <= tag.start()
            ):
                span_index += 1
            if (
                span_index < len(merged_spans)
                and merged_spans[span_index][0] <= tag.start()
            ):
                continue
            mask(cursor, tag.start())
            cursor = tag.end()
        mask(cursor, end)

    def container_end(line_index: int, containers: tuple[str, ...]) -> int:
        if not containers:
            return len(text)
        for next_index in range(line_index + 1, len(container_lines)):
            next_containers = container_lines[next_index][0]
            if next_containers[: len(containers)] != containers:
                return line_offsets[next_index]
        return len(text)

    def line_end_after(start: int, limit: int) -> int:
        line_ending = re.search(r"\r\n?|\n", text[start:limit])
        return limit if line_ending is None else start + line_ending.end()

    for line_index, (line, (containers, content)) in enumerate(
        zip(lines_with_endings, container_lines)
    ):
        line_body = line.rstrip("\r\n")
        content_start = offset + len(line_body) - len(content)
        content_end = offset + len(line_body)

        if offset < skip_until:
            open_paragraph_containers = None
            offset += len(line)
            continue

        if blank_block_start is not None:
            if offset >= blank_block_end:
                mask_except_html_tags(blank_block_start, blank_block_end)
                blank_block_start = None
            elif not content.strip():
                mask_except_html_tags(blank_block_start, content_start)
                blank_block_start = None
            else:
                open_paragraph_containers = None
                offset += len(line)
                continue

        stripped = content.lstrip(" \t")
        type_1 = MARKDOWN_RAW_HTML_TYPE_1.match(content)
        special_end: tuple[str, int] | None = None
        if stripped.startswith("<!--"):
            special_end = (r"-->", content.find("<!--"))
        elif stripped.startswith("<?"):
            special_end = (r"\?>", content.find("<?"))
        elif stripped.startswith("<![CDATA["):
            special_end = (r"\]\]>", content.find("<![CDATA["))
        elif re.match(r"<![A-Z]", stripped):
            special_end = (r">", content.find("<!"))

        if type_1:
            raw_container_end = container_end(line_index, containers)
            tag_name = type_1.group("tag").casefold()
            tag_start = content_start + len(content) - len(content.lstrip(" \t"))
            opening_tag = MARKDOWN_HTML_TAG.match(
                text, tag_start, raw_container_end
            )
            closing = re.compile(
                rf"</{re.escape(tag_name)}[ \t]*>", re.IGNORECASE
            )
            closing_match = closing.search(
                text,
                opening_tag.end() if opening_tag else content_start + type_1.end(),
                raw_container_end,
            )
            raw_end = closing_match.end() if closing_match else raw_container_end
            if style_content_spans is not None and tag_name == "style" and opening_tag:
                style_content_spans.append(
                    (
                        opening_tag.end(),
                        closing_match.start() if closing_match else raw_container_end,
                    )
                )
            skip_until = line_end_after(raw_end, raw_container_end)
            if opening_tag is None:
                mask(content_start, skip_until)
            elif tag_name == "pre":
                mask_except_html_tags(opening_tag.end(), skip_until)
            else:
                mask(opening_tag.end(), skip_until)
            open_paragraph_containers = None
        elif special_end:
            marker, block_start = special_end
            absolute_start = content_start + block_start
            raw_container_end = container_end(line_index, containers)
            marker_match = re.compile(marker).search(
                text, absolute_start, raw_container_end
            )
            raw_end = marker_match.end() if marker_match else raw_container_end
            skip_until = line_end_after(raw_end, raw_container_end)
            mask(absolute_start, skip_until)
            open_paragraph_containers = None
        else:
            type_6 = MARKDOWN_RAW_HTML_TYPE_6.match(content)
            type_7 = (
                MARKDOWN_RAW_HTML_TYPE_7.match(content)
                if open_paragraph_containers != containers
                else None
            )
            raw_tag = type_6 or type_7
            if raw_tag:
                raw_container_end = container_end(line_index, containers)
                tag_start = content_start + len(content) - len(content.lstrip(" \t"))
                opening_tag = MARKDOWN_HTML_TAG.match(
                    text, tag_start, raw_container_end
                )
                body_start = opening_tag.end() if opening_tag else content_start
                opening_name = (
                    re.match(r"<([A-Za-z][A-Za-z0-9-]*)", opening_tag.group(0))
                    if opening_tag
                    else None
                )
                tag_name = opening_name.group(1).casefold() if opening_name else None
                if tag_name in MARKDOWN_HTML_RAW_TEXT_OR_RCDATA_TAGS:
                    closing = re.compile(
                        rf"</{re.escape(tag_name)}[ \t]*>", re.IGNORECASE
                    )
                    closing_match = closing.search(text, body_start, raw_container_end)
                    raw_end = (
                        closing_match.end() if closing_match else raw_container_end
                    )
                    skip_until = line_end_after(raw_end, raw_container_end)
                    mask(body_start, skip_until)
                else:
                    blank_block_start = body_start
                    blank_block_end = raw_container_end
                open_paragraph_containers = None
            elif not content.strip():
                open_paragraph_containers = None
            elif (
                MARKDOWN_ATX_HEADING.match(content)
                or MARKDOWN_SETEXT_HEADING.match(content)
                or MARKDOWN_THEMATIC_BREAK.match(content)
                or line_index in reference_definition_lines
            ):
                open_paragraph_containers = None
            else:
                open_paragraph_containers = containers

        offset += len(line)

    if blank_block_start is not None:
        mask_except_html_tags(blank_block_start, blank_block_end)


def markdown_frontmatter_end(lines_with_endings: list[str]) -> int:
    """Return the end offset of recognized scalar frontmatter, if present."""

    if not lines_with_endings or lines_with_endings[0].strip() != "---":
        return 0

    offset = len(lines_with_endings[0])
    keys: set[str] = set()
    for line in lines_with_endings[1:]:
        offset += len(line)
        stripped = line.strip()
        if stripped in {"---", "..."}:
            return offset if keys else 0
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in line or line.startswith((" ", "\t", "-")):
            return 0
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value or key in keys:
            return 0
        keys.add(key)
    return 0


def markdown_searchable_text(
    text: str,
    *,
    mask_inline_code: bool = True,
    style_content_spans: list[tuple[int, int]] | None = None,
) -> str:
    """Mask literal Markdown regions while preserving offsets and line structure."""

    characters = list(text)
    lines_with_endings = text.splitlines(keepends=True)
    frontmatter_end = markdown_frontmatter_end(lines_with_endings)
    if frontmatter_end:
        for index in range(frontmatter_end):
            if characters[index] not in "\r\n":
                characters[index] = " "

    offset = 0
    fence_character: str | None = None
    fence_length = 0
    fence_container_spec: tuple[tuple[str, int], ...] = ()
    open_paragraph_containers: tuple[str, ...] | None = None

    lines = [line.rstrip("\r\n") for line in lines_with_endings]
    container_lines = markdown_container_lines(lines)
    _, reference_definition_lines = markdown_reference_definitions_with_lines(
        lines, container_lines
    )
    for line_index, (line, (containers, container_content)) in enumerate(
        zip(lines_with_endings, container_lines)
    ):
        line_body = line.rstrip("\r\n")
        indented_candidate = MARKDOWN_INDENTED_CODE.match(container_content) is not None
        indented_code = (
            indented_candidate
            and (
                open_paragraph_containers != containers
                or markdown_line_starts_list_item(line_body)
            )
        )
        active_fence_content: str | None = None
        if fence_character is not None:
            active_fence_content = markdown_fence_container_content(
                line_body, fence_container_spec
            )
            if active_fence_content is None:
                fence_character = None
                fence_length = 0
                fence_container_spec = ()
        fence_line = fence_character is not None
        if fence_character is None:
            match = None if indented_code else markdown_fence_opening(container_content)
            if match:
                fence = match.group(1)
                fence_character = fence[0]
                fence_length = len(fence)
                fence_container_spec = markdown_fence_container_spec(
                    line_body, containers, container_content
                ) or ()
                fence_line = True
        else:
            closing_fence = re.compile(
                rf"^ {{0,3}}{re.escape(fence_character)}{{{fence_length},}}[ \t]*$"
            )
            if active_fence_content is not None and closing_fence.match(
                active_fence_content
            ):
                fence_character = None
                fence_length = 0
                fence_container_spec = ()

        literal_block = indented_code or fence_line
        if literal_block:
            for index in range(offset, offset + len(line)):
                if characters[index] not in "\r\n":
                    characters[index] = " "

        stripped_content = container_content.lstrip(" \t")
        type_7_block = (
            open_paragraph_containers != containers
            and MARKDOWN_RAW_HTML_TYPE_7.match(container_content) is not None
        )
        raw_html_block = (
            MARKDOWN_RAW_HTML_TYPE_1.match(container_content) is not None
            or MARKDOWN_RAW_HTML_TYPE_6.match(container_content) is not None
            or type_7_block
            or stripped_content.startswith(("<!--", "<?", "<![CDATA["))
            or re.match(r"<![A-Z]", stripped_content) is not None
        )
        if (
            not container_content.strip()
            or literal_block
            or raw_html_block
            or MARKDOWN_ATX_HEADING.match(container_content)
            or MARKDOWN_SETEXT_HEADING.match(container_content)
            or MARKDOWN_THEMATIC_BREAK.match(container_content)
            or line_index in reference_definition_lines
        ):
            open_paragraph_containers = None
        else:
            open_paragraph_containers = containers
        offset += len(line)

    mask_markdown_raw_html_blocks(
        characters, reference_definition_lines, style_content_spans
    )

    literal_characters = characters.copy()
    masked = "".join(literal_characters)
    inline_context = markdown_inline_block_context(masked)
    index = 0
    while index < len(masked):
        if masked[index] != "`":
            index += 1
            continue
        if markdown_character_is_escaped(masked, index):
            index += 1
            continue
        run_end = index
        while run_end < len(masked) and masked[run_end] == "`":
            run_end += 1
        delimiter = masked[index:run_end]
        search_from = run_end
        inline_block_end = markdown_inline_block_end(masked, index, inline_context)
        closing = -1
        while True:
            candidate = masked.find(delimiter, search_from, inline_block_end)
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

    comment_characters = list(masked)
    for tag in MARKDOWN_HTML_TAG.finditer(masked):
        if markdown_character_is_escaped(masked, tag.start()):
            continue
        for position in range(*tag.span()):
            if comment_characters[position] not in "\r\n":
                comment_characters[position] = " "
    comment_search_text = "".join(comment_characters)
    for start, end in markdown_inline_html_special_spans(comment_search_text):
        if markdown_character_is_escaped(masked, start):
            continue
        for position in range(start, end):
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
            characters[index] = (
                MARKDOWN_ESCAPED_LBRACKET
                if character == "["
                else MARKDOWN_ESCAPED_LT
            )

    return "".join(characters)


def markdown_character_is_escaped(text: str, index: int) -> bool:
    """Return whether a Markdown punctuation character has an odd escape prefix."""

    preceding_backslashes = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        preceding_backslashes += 1
        cursor -= 1
    return preceding_backslashes % 2 == 1


def markdown_paragraph_end(text: str, start: int) -> int:
    """Return the first blank-line boundary after an inline construct."""

    boundary = MARKDOWN_PARAGRAPH_BOUNDARY.search(text, start)
    return len(text) if boundary is None else boundary.start()


def markdown_paragraph_boundaries(text: str) -> tuple[int, ...]:
    """Index blank-line boundaries once for repeated inline HTML scans."""

    return tuple(match.start() for match in MARKDOWN_PARAGRAPH_BOUNDARY.finditer(text))


def markdown_html_tag_is_rendered(
    text: str,
    tag: re.Match[str],
    paragraph_boundaries: tuple[int, ...] | None = None,
) -> bool:
    """Return whether an HTML tag is inline or a type-1 raw-block opener."""

    if paragraph_boundaries is None:
        paragraph_end = markdown_paragraph_end(text, tag.start())
    else:
        boundary_index = bisect_left(paragraph_boundaries, tag.start())
        paragraph_end = (
            len(text)
            if boundary_index >= len(paragraph_boundaries)
            else paragraph_boundaries[boundary_index]
        )
    if tag.end() <= paragraph_end:
        return True

    line_start = max(
        text.rfind("\n", 0, tag.start()), text.rfind("\r", 0, tag.start())
    )
    line_start += 1
    type_1 = MARKDOWN_RAW_HTML_TYPE_1.match(text[line_start:])
    if type_1 is None:
        return False
    return line_start + type_1.group(0).find("<") == tag.start()


def markdown_inline_html_special_spans(text: str) -> list[tuple[int, int]]:
    """Return complete inline HTML special constructs within one paragraph."""

    spans: list[tuple[int, int]] = []
    index = 0
    while index < len(text):
        start = text.find("<", index)
        if start < 0:
            break
        if text.startswith("<!--", start):
            opener_length, closer = 4, "-->"
        elif text.startswith("<?", start):
            opener_length, closer = 2, "?>"
        elif text.startswith("<![CDATA[", start):
            opener_length, closer = 9, "]]>"
        elif re.match(r"<![A-Z]", text[start:]):
            opener_length, closer = 3, ">"
        else:
            index = start + 1
            continue

        paragraph_end = markdown_paragraph_end(text, start)
        closing = text.find(closer, start + opener_length, paragraph_end)
        if closing < 0:
            index = start + opener_length
            continue
        end = closing + len(closer)
        if text.startswith("<!--", start):
            content = text[start + opener_length : closing]
            if (
                content.startswith((">", "->"))
                or content.endswith("-")
                or "--" in content
            ):
                index = start + opener_length
                continue
        spans.append((start, end))
        index = end
    return spans


def markdown_unescape(text: str) -> str:
    """Decode only semicolon-terminated CommonMark character references."""

    return MARKDOWN_CHARACTER_REFERENCE.sub(
        lambda match: html_unescape(match.group(0)), text
    )


def markdown_restore_escaped_openers(text: str) -> str:
    """Restore escaped punctuation protected from structural Markdown scans."""

    return text.replace(MARKDOWN_ESCAPED_LBRACKET, "[").replace(
        MARKDOWN_ESCAPED_LT, "<"
    )


def markdown_normalize_reference_label(label: str) -> str:
    """Normalize a reference label for case-insensitive CommonMark matching."""

    label = MARKDOWN_BACKSLASH_ESCAPE.sub(r"\1", label)
    label = re.sub(r"[ \t\r\n]+", " ", markdown_unescape(label))
    return label.strip(" ").casefold()


def markdown_inline_whitespace_end(
    text: str, start: int, limit: int | None = None
) -> int | None:
    """Consume inline whitespace without crossing a paragraph boundary."""

    index = start
    end = len(text) if limit is None else limit
    line_endings = 0
    while index < end:
        if text[index] in " \t":
            index += 1
            continue
        if text[index] == "\r":
            line_endings += 1
            index += 1
            if index < end and text[index] == "\n":
                index += 1
        elif text[index] == "\n":
            line_endings += 1
            index += 1
        else:
            break
        if line_endings > 1:
            return None
    return index


def markdown_reference_definitions_with_lines(
    lines: list[str],
    container_lines: list[tuple[tuple[str, ...], str]] | None = None,
) -> tuple[list[re.Match[str]], set[int]]:
    """Return active definitions and every normalized line they occupy."""

    if container_lines is None:
        container_lines = markdown_container_lines(lines)
    container_text = "\n".join(content for _, content in container_lines)
    container_line_endings = [
        index for index, character in enumerate(container_text) if character == "\n"
    ]
    definitions: list[re.Match[str]] = []
    definition_lines: set[int] = set()
    for match in MARKDOWN_REFERENCE_DEFINITION.finditer(container_text):
        target = match.group("target")
        raw_label = match.group("label")
        if len(raw_label) > MARKDOWN_REFERENCE_LABEL_MAX_LENGTH:
            continue
        if not target.startswith("<") and not markdown_bare_destination_is_balanced(
            target
        ):
            continue
        line_index = bisect_left(container_line_endings, match.start())
        containers, _ = container_lines[line_index]
        end_line_index = bisect_left(
            container_line_endings, max(match.start(), match.end() - 1)
        )
        if any(
            continued_containers != containers
            for continued_containers, _ in container_lines[
                line_index + 1 : end_line_index + 1
            ]
        ):
            continue
        if line_index == 0:
            definitions.append(match)
            definition_lines.update(range(line_index, end_line_index + 1))
            continue

        previous_containers, previous_content = container_lines[line_index - 1]
        begins_list_item = markdown_line_starts_list_item(lines[line_index])
        previous_ends_block = (
            not previous_content.strip()
            or line_index - 1 in definition_lines
            or MARKDOWN_ATX_HEADING.match(previous_content) is not None
            or MARKDOWN_SETEXT_HEADING.match(previous_content) is not None
            or MARKDOWN_THEMATIC_BREAK.match(previous_content) is not None
        )
        if (
            containers != previous_containers
            or begins_list_item
            or previous_ends_block
        ):
            definitions.append(match)
            definition_lines.update(range(line_index, end_line_index + 1))
    return definitions, definition_lines


def markdown_reference_definitions(
    text: str,
) -> list[re.Match[str]]:
    """Return definitions that occur where a new Markdown block may begin."""

    definitions, _ = markdown_reference_definitions_with_lines(text.splitlines())
    return definitions


def markdown_reference_definition_ranges(
    text: str, definitions: list[re.Match[str]]
) -> list[tuple[int, int]]:
    """Map normalized reference-definition matches to original line ranges."""

    if not definitions:
        return []

    lines_with_endings = text.splitlines(keepends=True)
    container_text = "\n".join(
        content for _, content in markdown_container_lines(text.splitlines())
    )
    container_line_endings = [
        index for index, character in enumerate(container_text) if character == "\n"
    ]
    line_offsets = [0]
    for line in lines_with_endings:
        line_offsets.append(line_offsets[-1] + len(line))

    ranges: list[tuple[int, int]] = []
    for definition in definitions:
        start_line = bisect_left(container_line_endings, definition.start())
        end_line = bisect_left(
            container_line_endings,
            max(definition.start(), definition.end() - 1),
        )
        ranges.append((line_offsets[start_line], line_offsets[end_line + 1]))
    return ranges


def markdown_bare_destination_is_balanced(destination: str) -> bool:
    """Return whether a bare destination has balanced unescaped parentheses."""

    depth = 0
    index = 0
    while index < len(destination):
        character = destination[index]
        if character == " " or ord(character) < 0x20 or ord(character) == 0x7F:
            return False
        if character == "\\":
            escape = MARKDOWN_BACKSLASH_ESCAPE.match(destination, index)
            if escape is not None:
                index = escape.end()
                continue
            index += 1
            continue
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth < 0:
                return False
        index += 1
    return depth == 0


def markdown_reference_usages(
    text: str,
    reference_labels: set[str],
    label_pairs: dict[int, int] | None = None,
    definition_ranges: list[tuple[int, int]] | None = None,
) -> dict[str, bool]:
    """Collect active reference labels and whether any use renders an image."""

    if not reference_labels:
        return {}
    if label_pairs is None:
        label_pairs = markdown_label_pairs(text)
    if definition_ranges is None:
        definitions = markdown_reference_definitions(text)
        definition_ranges = markdown_reference_definition_ranges(text, definitions)
    usages: dict[str, bool] = {}
    image_label_ranges = markdown_active_image_label_ranges(
        text, reference_labels, label_pairs
    )
    definition_index = 0
    definition_end = -1
    image_index = 0
    image_end = -1
    paragraph_end = -1
    for label_start, character in enumerate(text):
        if character != "[" or markdown_character_is_escaped(text, label_start):
            continue
        while (
            definition_index < len(definition_ranges)
            and definition_ranges[definition_index][0] <= label_start
        ):
            definition_end = max(
                definition_end, definition_ranges[definition_index][1]
            )
            definition_index += 1
        if label_start < definition_end:
            continue
        while (
            image_index < len(image_label_ranges)
            and image_label_ranges[image_index][0] < label_start
        ):
            image_end = max(image_end, image_label_ranges[image_index][1])
            image_index += 1
        if label_start < image_end:
            continue
        if label_start >= paragraph_end:
            paragraph_end = markdown_paragraph_end(text, label_start)
        label_end = label_pairs.get(label_start)
        if label_end is None:
            continue
        is_image = (
            label_start > 0
            and text[label_start - 1] == "!"
            and not markdown_character_is_escaped(text, label_start - 1)
        )
        if label_end + 1 < len(text) and text[label_end + 1] == ":":
            continue
        primary_label = text[label_start + 1 : label_end]
        cursor = label_end + 1
        if (
            cursor < len(text)
            and text[cursor] == "("
            and markdown_destination_end(text, cursor, paragraph_end) is not None
        ):
            continue
        if cursor < len(text) and text[cursor] == "[":
            reference_end = label_pairs.get(cursor)
            if reference_end is None:
                continue
            reference_label = text[cursor + 1 : reference_end] or primary_label
        else:
            reference_label = primary_label
        if len(reference_label) > MARKDOWN_REFERENCE_LABEL_MAX_LENGTH:
            continue
        normalized = markdown_normalize_reference_label(reference_label)
        if normalized not in reference_labels:
            continue
        if not is_image and markdown_label_contains_active_link(
            text,
            label_start,
            label_end,
            reference_labels,
            label_pairs,
            paragraph_end,
        ):
            continue
        usages[normalized] = usages.get(normalized, False) or is_image
    return usages


def markdown_label_contains_active_link(
    text: str,
    label_start: int,
    label_end: int,
    reference_labels: set[str],
    label_pairs: dict[int, int] | None = None,
    paragraph_end: int | None = None,
) -> bool:
    """Return whether a link label contains a nested link that deactivates it."""

    bracket_stack: list[int] = []
    closing_brackets: dict[int, int] = {}
    index = label_start + 1
    while index < label_end:
        if markdown_character_is_escaped(text, index):
            index += 1
            continue
        if text[index] == "[":
            bracket_stack.append(index)
        elif text[index] == "]" and bracket_stack:
            closing_brackets[bracket_stack.pop()] = index
        index += 1

    index = label_start + 1
    while index < label_end:
        nested_end = closing_brackets.get(index)
        if nested_end is None:
            index += 1
            continue
        is_image = (
            index > 0
            and text[index - 1] == "!"
            and not markdown_character_is_escaped(text, index - 1)
        )
        if is_image:
            index = nested_end + 1
            continue

        cursor = nested_end + 1
        if cursor < label_end and text[cursor] == "(":
            destination = markdown_destination_end(text, cursor, paragraph_end)
            if destination is not None and destination[1] < label_end:
                return True
        if cursor < label_end and text[cursor] == "[":
            reference_end = (
                label_pairs.get(cursor)
                if label_pairs is not None
                else markdown_label_end(text, cursor)
            )
            if reference_end is not None and reference_end < label_end:
                reference_label = text[cursor + 1 : reference_end]
                if not reference_label:
                    reference_label = text[index + 1 : nested_end]
                if (
                    len(reference_label) <= MARKDOWN_REFERENCE_LABEL_MAX_LENGTH
                    and markdown_normalize_reference_label(reference_label)
                    in reference_labels
                ):
                    return True
        elif (
            len(text[index + 1 : nested_end])
            <= MARKDOWN_REFERENCE_LABEL_MAX_LENGTH
            and
            markdown_normalize_reference_label(text[index + 1 : nested_end])
            in reference_labels
        ):
            return True
        index += 1
    return False


def markdown_render_code_spans(text: str) -> str:
    """Render code-span text with CommonMark whitespace normalization."""

    result: list[str] = []
    index = 0
    while index < len(text):
        if text[index] != "`" or markdown_character_is_escaped(text, index):
            result.append(text[index])
            index += 1
            continue
        run_end = index
        while run_end < len(text) and text[run_end] == "`":
            run_end += 1
        delimiter = text[index:run_end]
        paragraph_end = markdown_paragraph_end(text, index)
        closing = text.find(delimiter, run_end, paragraph_end)
        while closing >= 0:
            before_is_tick = closing > 0 and text[closing - 1] == "`"
            after = closing + len(delimiter)
            after_is_tick = after < len(text) and text[after] == "`"
            if not before_is_tick and not after_is_tick:
                break
            closing = text.find(
                delimiter, closing + len(delimiter), paragraph_end
            )
        if closing < 0:
            result.append(delimiter)
            index = run_end
            continue

        content = re.sub(r"[ \t\r\n]+", " ", text[run_end:closing])
        if content.startswith(" ") and content.endswith(" ") and content.strip():
            content = content[1:-1]
        content = content.replace("<", MARKDOWN_CODE_SPAN_LT).replace(
            ">", MARKDOWN_CODE_SPAN_GT
        )
        result.append(content)
        index = closing + len(delimiter)
    return "".join(result)


def html_attribute_unescape(text: str) -> str:
    """Decode HTML references using the tokenizer's attribute-value rules."""

    result: list[str] = []
    index = 0
    while index < len(text):
        if text[index] != "&":
            result.append(text[index])
            index += 1
            continue

        numeric = HTML_NUMERIC_CHARACTER_REFERENCE.match(text, index)
        if numeric is not None:
            result.append(html_unescape(numeric.group(0)))
            index = numeric.end()
            continue

        name_start = index + 1
        max_end = min(
            len(text), name_start + HTML_CHARACTER_REFERENCE_MAX_LENGTH
        )
        entity_name: str | None = None
        for end in range(max_end, name_start, -1):
            candidate = text[name_start:end]
            if candidate in HTML5_ENTITIES:
                entity_name = candidate
                break
        if entity_name is None:
            result.append("&")
            index += 1
            continue

        entity_end = name_start + len(entity_name)
        if (
            not entity_name.endswith(";")
            and entity_end < len(text)
            and (
                (text[entity_end].isascii() and text[entity_end].isalnum())
                or text[entity_end] == "="
            )
        ):
            result.append("&")
            index += 1
            continue

        result.append(HTML5_ENTITIES[entity_name])
        index = entity_end
    return "".join(result)


def html_attribute_values(
    text: str,
    names: frozenset[str],
    *,
    tag_names: frozenset[str] | None = None,
    required_attribute_values: dict[str, frozenset[str]] | None = None,
) -> list[str]:
    """Collect top-level HTML attribute values without scanning quoted values."""

    values: list[str] = []
    paragraph_boundaries = markdown_paragraph_boundaries(text)
    for tag_match in MARKDOWN_HTML_TAG.finditer(text):
        if not markdown_html_tag_is_rendered(text, tag_match, paragraph_boundaries):
            continue
        tag = tag_match.group(0)
        index = 1
        while index < len(tag) and (tag[index].isalnum() or tag[index] in {"-", ":"}):
            index += 1
        tag_name = tag[1:index].casefold()
        if tag_names is not None and tag_name not in tag_names:
            continue
        tag_values: list[str] = []
        attributes: dict[str, str] = {}
        while index < len(tag) - 1:
            while index < len(tag) - 1 and tag[index].isspace():
                index += 1
            if index >= len(tag) - 1 or tag[index] in {"/", ">"}:
                break

            name_start = index
            while (
                index < len(tag) - 1
                and not tag[index].isspace()
                and tag[index] not in "\"'=<>`/"
            ):
                index += 1
            if index == name_start:
                index += 1
                continue
            name = tag[name_start:index].casefold()
            is_first_attribute = name not in attributes

            while index < len(tag) - 1 and tag[index].isspace():
                index += 1
            if index >= len(tag) - 1 or tag[index] != "=":
                attributes.setdefault(name, "")
                continue
            index += 1
            while index < len(tag) - 1 and tag[index].isspace():
                index += 1
            if index >= len(tag) - 1:
                break

            if tag[index] in {'"', "'"}:
                quote = tag[index]
                value_start = index + 1
                index = tag.find(quote, value_start)
                if index < 0:
                    break
                value = tag[value_start:index]
                index += 1
            else:
                value_start = index
                while (
                    index < len(tag) - 1
                    and not tag[index].isspace()
                    and tag[index] not in "\"'=<>`"
                ):
                    index += 1
                value = tag[value_start:index]
            attributes.setdefault(name, value)
            if is_first_attribute and name in names:
                tag_values.append(value)
        if required_attribute_values is None or all(
            html_attribute_unescape(attributes.get(name, "")).casefold()
            in allowed_values
            for name, allowed_values in required_attribute_values.items()
        ):
            values.extend(tag_values)
    return values


def html_srcset_descriptors_are_valid(descriptors: list[str]) -> bool:
    """Return whether one srcset candidate's descriptors survive parsing."""

    width: int | None = None
    density: float | None = None
    future_compat_height: int | None = None
    for descriptor in descriptors:
        if descriptor.endswith("w") and re.fullmatch(
            r"[0-9]+", descriptor[:-1]
        ):
            if width is not None or density is not None:
                return False
            width = int(descriptor[:-1])
            if width == 0:
                return False
            continue
        if descriptor.endswith("x") and HTML_FLOATING_POINT_NUMBER.fullmatch(
            descriptor[:-1]
        ):
            if (
                width is not None
                or density is not None
                or future_compat_height is not None
            ):
                return False
            density = float(descriptor[:-1])
            if density < 0 or not math.isfinite(density):
                return False
            continue
        if descriptor.endswith("h") and re.fullmatch(
            r"[0-9]+", descriptor[:-1]
        ):
            if future_compat_height is not None or density is not None:
                return False
            future_compat_height = int(descriptor[:-1])
            if future_compat_height == 0:
                return False
            continue
        return False
    return future_compat_height is None or width is not None


def html_srcset_candidates(value: str) -> list[str]:
    """Extract URL candidates accepted by the HTML srcset parser."""

    candidates: list[str] = []
    index = 0
    while index < len(value):
        while index < len(value) and (
            value[index] in HTML_ASCII_WHITESPACE or value[index] == ","
        ):
            index += 1
        if index >= len(value):
            break

        url_start = index
        while index < len(value) and value[index] not in HTML_ASCII_WHITESPACE:
            index += 1
        url = value[url_start:index]
        trailing_commas = len(url) - len(url.rstrip(","))
        url = url.rstrip(",")
        if url and trailing_commas:
            candidates.append(url)
        if trailing_commas:
            continue

        descriptors_start = index
        parentheses = 0
        while index < len(value):
            character = value[index]
            if character == "(":
                parentheses += 1
            elif character == ")" and parentheses:
                parentheses -= 1
            elif character == "," and parentheses == 0:
                break
            index += 1
        descriptors = re.findall(
            r"[^\t\n\f\r ]+", value[descriptors_start:index]
        )
        if url and html_srcset_descriptors_are_valid(descriptors):
            candidates.append(url)
        if index < len(value) and value[index] == ",":
            index += 1
    return candidates


def css_string_value(text: str, start: int) -> tuple[str, int] | None:
    """Return a quoted CSS string and the offset after its closing quote."""

    quote = text[start]
    value: list[str] = []
    index = start + 1
    while index < len(text):
        character = text[index]
        if character == quote:
            return "".join(value), index + 1
        if character == "\\":
            if index + 1 >= len(text):
                return None
            value.extend(text[index : index + 2])
            index += 2
            continue
        if character in "\r\n\f":
            return None
        value.append(character)
        index += 1
    return None


def css_resource_targets(text: str) -> list[str]:
    """Extract resource URLs from CSS url() functions and @import strings."""

    targets: list[str] = []
    index = 0
    while index < len(text):
        if text.startswith("/*", index):
            comment_end = text.find("*/", index + 2)
            index = len(text) if comment_end < 0 else comment_end + 2
            continue
        if text[index] in {'"', "'"}:
            string = css_string_value(text, index)
            index = len(text) if string is None else string[1]
            continue

        import_match = CSS_IMPORT_RULE.match(text, index)
        if import_match is not None:
            value_start = import_match.end()
            while value_start < len(text) and text[value_start] in HTML_ASCII_WHITESPACE:
                value_start += 1
            if value_start < len(text) and text[value_start] in {'"', "'"}:
                string = css_string_value(text, value_start)
                if string is not None:
                    targets.append(string[0])
                    index = string[1]
                    continue

        url_match = CSS_URL_FUNCTION.match(text, index)
        previous = text[index - 1] if index else ""
        if url_match is not None and not (
            previous.isascii() and (previous.isalnum() or previous in {"_", "-"})
        ):
            value_start = url_match.end()
            while value_start < len(text) and text[value_start] in HTML_ASCII_WHITESPACE:
                value_start += 1
            if value_start < len(text) and text[value_start] in {'"', "'"}:
                string = css_string_value(text, value_start)
                if string is not None:
                    value, value_end = string
                    while value_end < len(text) and text[value_end] in HTML_ASCII_WHITESPACE:
                        value_end += 1
                    if value_end < len(text) and text[value_end] == ")":
                        targets.append(value)
                        index = value_end + 1
                        continue
            else:
                value_end = value_start
                while value_end < len(text) and text[value_end] != ")":
                    if text[value_end] in {'"', "'", "("}:
                        break
                    if text[value_end] == "\\" and value_end + 1 < len(text):
                        value_end += 2
                        continue
                    value_end += 1
                if value_end < len(text) and text[value_end] == ")":
                    value = text[value_start:value_end].rstrip(" \t\r\n\f")
                    if value:
                        targets.append(value)
                    index = value_end + 1
                    continue
        index += 1
    return targets


class HTMLFragmentResourceParser(HTMLParser):
    """Collect browser-loaded targets from an iframe srcdoc HTML fragment."""

    CDATA_CONTENT_ELEMENTS = tuple(MARKDOWN_HTML_RAW_TEXT_OR_RCDATA_TAGS)

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.targets: list[tuple[str, bool, bool]] = []
        self.srcdocs: list[str] = []
        self.style_content: list[str] | None = None

    def handle_starttag(
        self, tag: str, attributes: list[tuple[str, str | None]]
    ) -> None:
        tag = tag.casefold()
        values: dict[str, str] = {}
        for name, value in attributes:
            values.setdefault(name.casefold(), value or "")

        if tag in MARKDOWN_HTML_HREF_TAGS and "href" in values:
            self.targets.append((values["href"], False, False))
        if tag in MARKDOWN_HTML_SRC_TAGS and "src" in values:
            self.targets.append((values["src"], False, True))
        if (
            tag in MARKDOWN_HTML_INPUT_TAGS
            and values.get("type", "").casefold() in MARKDOWN_HTML_IMAGE_INPUT_TYPES
            and "src" in values
        ):
            self.targets.append((values["src"], False, True))
        if tag in MARKDOWN_HTML_DATA_TAGS and "data" in values:
            self.targets.append((values["data"], False, True))
        if tag in MARKDOWN_HTML_POSTER_TAGS and "poster" in values:
            self.targets.append((values["poster"], False, True))
        if tag in MARKDOWN_HTML_SRCSET_TAGS and "srcset" in values:
            self.targets.extend(
                (candidate, False, True)
                for candidate in html_srcset_candidates(values["srcset"])
            )
        if tag in MARKDOWN_HTML_SRCDOC_TAGS and "srcdoc" in values:
            self.srcdocs.append(values["srcdoc"])
        if tag == "style":
            self.style_content = []

    def handle_startendtag(
        self, tag: str, attributes: list[tuple[str, str | None]]
    ) -> None:
        self.handle_starttag(tag, attributes)

    def handle_data(self, data: str) -> None:
        if self.style_content is not None:
            self.style_content.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "style" and self.style_content is not None:
            self.targets.extend(
                (target, False, True)
                for target in css_resource_targets("".join(self.style_content))
            )
            self.style_content = None

    def finish(self) -> None:
        self.close()
        if self.style_content is not None:
            self.targets.extend(
                (target, False, True)
                for target in css_resource_targets("".join(self.style_content))
            )
            self.style_content = None


def html_fragment_resource_targets(
    text: str, *, srcdoc_depth: int
) -> list[tuple[str, bool, bool]]:
    """Collect targets from HTML parsed inside an iframe srcdoc document."""

    parser = HTMLFragmentResourceParser()
    parser.feed(text)
    parser.finish()
    targets = parser.targets
    if srcdoc_depth >= 8:
        return targets
    for srcdoc in parser.srcdocs:
        targets.extend(
            html_fragment_resource_targets(
                srcdoc, srcdoc_depth=srcdoc_depth + 1
            )
        )
    return targets


def html_style_contents(text: str) -> list[str]:
    """Return the bodies of complete rendered inline style elements."""

    contents: list[str] = []
    paragraph_boundaries = markdown_paragraph_boundaries(text)
    closing = re.compile(r"</style[ \t]*>", re.IGNORECASE)
    for tag in MARKDOWN_HTML_TAG.finditer(text):
        if not re.match(r"<style(?=[\s>])", tag.group(0), re.IGNORECASE):
            continue
        if not markdown_html_tag_is_rendered(text, tag, paragraph_boundaries):
            continue
        closing_match = closing.search(text, tag.end())
        if closing_match is None:
            continue
        contents.append(text[tag.end() : closing_match.start()])
    return contents


def html_resource_targets(text: str) -> list[tuple[str, bool, bool]]:
    """Collect navigations and resource requests from rendered HTML."""

    targets: list[tuple[str, bool, bool]] = []
    targets.extend(
        (html_attribute_unescape(target), False, False)
        for target in html_attribute_values(
            text,
            MARKDOWN_HTML_HREF_ATTRIBUTES,
            tag_names=MARKDOWN_HTML_HREF_TAGS,
        )
    )
    targets.extend(
        (html_attribute_unescape(target), False, True)
        for target in html_attribute_values(
            text,
            MARKDOWN_HTML_SRC_ATTRIBUTES,
            tag_names=MARKDOWN_HTML_SRC_TAGS,
        )
    )
    targets.extend(
        (html_attribute_unescape(target), False, True)
        for target in html_attribute_values(
            text,
            MARKDOWN_HTML_SRC_ATTRIBUTES,
            tag_names=MARKDOWN_HTML_INPUT_TAGS,
            required_attribute_values={"type": MARKDOWN_HTML_IMAGE_INPUT_TYPES},
        )
    )
    targets.extend(
        (html_attribute_unescape(target), False, True)
        for target in html_attribute_values(
            text,
            MARKDOWN_HTML_DATA_ATTRIBUTES,
            tag_names=MARKDOWN_HTML_DATA_TAGS,
        )
    )
    targets.extend(
        (html_attribute_unescape(target), False, True)
        for target in html_attribute_values(
            text,
            MARKDOWN_HTML_POSTER_ATTRIBUTES,
            tag_names=MARKDOWN_HTML_POSTER_TAGS,
        )
    )
    targets.extend(
        (candidate, False, True)
        for value in html_attribute_values(
            text,
            MARKDOWN_HTML_SRCSET_ATTRIBUTES,
            tag_names=MARKDOWN_HTML_SRCSET_TAGS,
        )
        for candidate in html_srcset_candidates(html_attribute_unescape(value))
    )
    for style_content in html_style_contents(text):
        targets.extend(
            (target, False, True)
            for target in css_resource_targets(style_content)
        )

    for srcdoc in html_attribute_values(
        text,
        MARKDOWN_HTML_SRCDOC_ATTRIBUTES,
        tag_names=MARKDOWN_HTML_SRCDOC_TAGS,
    ):
        targets.extend(
            html_fragment_resource_targets(
                html_attribute_unescape(srcdoc),
                srcdoc_depth=1,
            )
        )
    return targets


def markdown_inline_block_context(
    text: str,
) -> tuple[
    list[str],
    list[int],
    list[tuple[tuple[str, ...], str]],
    list[int],
]:
    """Precompute line containers and blank-line paragraph ends once."""

    lines_with_endings = text.splitlines(keepends=True)
    lines = [line.rstrip("\r\n") for line in lines_with_endings]
    line_offsets: list[int] = []
    offset = 0
    for line in lines_with_endings:
        line_offsets.append(offset)
        offset += len(line)
    container_lines = markdown_container_lines(lines)
    paragraph_ends = [len(text)] * len(lines)
    paragraph_start_line = 0
    for line_index, line in enumerate(lines):
        if line.strip(" \t"):
            continue
        if paragraph_start_line < line_index:
            previous_line = lines_with_endings[line_index - 1]
            paragraph_end = line_offsets[line_index - 1] + len(
                previous_line.rstrip("\r\n")
            )
            paragraph_ends[paragraph_start_line:line_index] = [paragraph_end] * (
                line_index - paragraph_start_line
            )
        paragraph_ends[line_index] = line_offsets[line_index]
        paragraph_start_line = line_index + 1
    return lines, line_offsets, container_lines, paragraph_ends


def markdown_label_pairs(text: str) -> dict[int, int]:
    """Parse matching label brackets once per inline Markdown block."""

    pairs: dict[int, int] = {}
    inline_context = markdown_inline_block_context(text)
    search_from = 0
    while search_from < len(text):
        label_start = text.find("[", search_from)
        while label_start >= 0 and markdown_character_is_escaped(text, label_start):
            label_start = text.find("[", label_start + 1)
        if label_start < 0:
            break

        block_end = markdown_inline_block_end(text, label_start, inline_context)
        stack: list[int] = []
        index = label_start
        while index < block_end:
            if text[index] == "\\":
                index += 2
                continue
            if text[index] == "[":
                stack.append(index)
            elif text[index] == "]" and stack:
                pairs[stack.pop()] = index
            index += 1
        search_from = max(block_end, label_start + 1)
    return pairs


def markdown_label_end(text: str, start: int) -> int | None:
    """Find a label's closing bracket while respecting nested image/link labels."""

    depth = 1
    index = start + 1
    inline_block_end = markdown_inline_block_end(text, start)
    while index < inline_block_end:
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


def markdown_inline_block_end(
    text: str,
    start: int,
    context: tuple[
        list[str],
        list[int],
        list[tuple[tuple[str, ...], str]],
        list[int],
    ]
    | None = None,
) -> int:
    """Return the next paragraph-interrupting block boundary after an inline start."""

    if context is None:
        context = markdown_inline_block_context(text)
    lines, line_offsets, container_lines, paragraph_ends = context
    if not lines:
        return len(text)
    start_line = max(0, bisect_right(line_offsets, start) - 1)
    paragraph_end = paragraph_ends[start_line]
    start_containers = container_lines[start_line][0]

    paragraph_end_line = bisect_left(
        line_offsets, paragraph_end, start_line + 1
    )
    for line_index in range(start_line + 1, paragraph_end_line):
        containers, content = container_lines[line_index]
        parent_containers, parent_content = markdown_blockquote_content(lines[line_index])
        direct_list_item = MARKDOWN_LIST_PREFIX.match(parent_content)
        non_one_ordered_item = (
            direct_list_item is not None
            and direct_list_item.group("marker")[0].isdigit()
            and int(direct_list_item.group("marker")[:-1]) != 1
            and parent_containers == start_containers
        )
        empty_noninterrupting_list_item = (
            direct_list_item is not None
            and (
                direct_list_item.group("marker") in {"*", "+"}
                or direct_list_item.group("marker")[0].isdigit()
            )
            and not parent_content[
                markdown_list_prefix_end(direct_list_item) :
            ].strip()
            and parent_containers == start_containers
        )
        if non_one_ordered_item or empty_noninterrupting_list_item:
            containers = parent_containers
            content = parent_content
        interrupts_paragraph = markdown_line_interrupts_paragraph(content)
        lazy_continuation = (
            containers != start_containers
            and len(containers) < len(start_containers)
            and start_containers[: len(containers)] == containers
            and not interrupts_paragraph
        )
        if (
            containers != start_containers and not lazy_continuation
        ) or not content.strip() or interrupts_paragraph:
            return line_offsets[line_index]
    return paragraph_end


def markdown_line_interrupts_paragraph(content: str) -> bool:
    """Return whether content begins a block that can interrupt a paragraph."""

    stripped = content.lstrip(" \t")
    return bool(
        MARKDOWN_ATX_HEADING.match(content)
        or MARKDOWN_SETEXT_HEADING.match(content)
        or MARKDOWN_THEMATIC_BREAK.match(content)
        or markdown_fence_opening(content)
        or MARKDOWN_RAW_HTML_TYPE_1.match(content)
        or MARKDOWN_RAW_HTML_TYPE_6.match(content)
        or stripped.startswith(("<!--", "<?", "<![CDATA["))
        or re.match(r"<![A-Z]", stripped)
    )


def markdown_destination_end(
    text: str, opening: int, paragraph_end: int | None = None
) -> tuple[str, int] | None:
    """Extract a valid CommonMark inline destination and its closing parenthesis."""

    start = opening + 1
    index = start
    if paragraph_end is None:
        paragraph_end = markdown_paragraph_end(text, opening)
    if index >= paragraph_end:
        return None

    if text[index] == "<":
        index += 1
        while index < paragraph_end:
            character = text[index]
            if character == "\\":
                escape = MARKDOWN_BACKSLASH_ESCAPE.match(text, index)
                if escape is None:
                    return None
                index = escape.end()
                continue
            if character in "\r\n<":
                return None
            if character == ">":
                index += 1
                break
            index += 1
        else:
            return None
    else:
        depth = 0
        while index < paragraph_end:
            character = text[index]
            if (
                ord(character) < 0x20 or ord(character) == 0x7F
            ) and not character.isspace():
                return None
            if character == "\\":
                escape = MARKDOWN_BACKSLASH_ESCAPE.match(text, index)
                if escape is not None:
                    index = escape.end()
                    continue
            if character.isspace() or (character == ")" and depth == 0):
                break
            if character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
            index += 1
        if depth:
            return None

    destination_end = index
    separator_start = index
    whitespace_end = markdown_inline_whitespace_end(text, index, paragraph_end)
    if whitespace_end is None or whitespace_end >= paragraph_end:
        return None
    index = whitespace_end
    if text[index] == ")":
        return text[start:destination_end], index
    if index == separator_start or text[index] not in {'"', "'", "("}:
        return None

    title_closer = ")" if text[index] == "(" else text[index]
    index += 1
    while index < paragraph_end:
        character = text[index]
        if character == "\\":
            index += 2
            continue
        if character == title_closer:
            index += 1
            break
        index += 1
    else:
        return None

    whitespace_end = markdown_inline_whitespace_end(text, index, paragraph_end)
    if whitespace_end is None or whitespace_end >= paragraph_end:
        return None
    index = whitespace_end
    if text[index] != ")":
        return None
    return text[start:destination_end], index


def markdown_active_image_label_ranges(
    text: str,
    reference_labels: set[str],
    label_pairs: dict[int, int] | None = None,
) -> list[tuple[int, int]]:
    """Return rendered image-label ranges whose nested targets are alt text only."""

    if label_pairs is None:
        label_pairs = markdown_label_pairs(text)
    ranges: list[tuple[int, int]] = []
    paragraph_end = -1
    for label_start, character in enumerate(text):
        if character != "[" or label_start == 0 or text[label_start - 1] != "!":
            continue
        if markdown_character_is_escaped(text, label_start - 1):
            continue
        label_end = label_pairs.get(label_start)
        if label_end is None:
            continue

        if label_start >= paragraph_end:
            paragraph_end = markdown_paragraph_end(text, label_start)
        primary_label = text[label_start + 1 : label_end]
        cursor = label_end + 1
        active = (
            cursor < len(text)
            and text[cursor] == "("
            and markdown_destination_end(text, cursor, paragraph_end) is not None
        )
        if not active:
            if cursor < len(text) and text[cursor] == "[":
                reference_end = label_pairs.get(cursor)
                if reference_end is None:
                    continue
                reference_label = text[cursor + 1 : reference_end] or primary_label
            else:
                reference_label = primary_label
            active = (
                len(reference_label) <= MARKDOWN_REFERENCE_LABEL_MAX_LENGTH
                and markdown_normalize_reference_label(reference_label)
                in reference_labels
            )
        if active:
            ranges.append((label_start, label_end))
    return ranges


def markdown_link_targets(text: str) -> list[tuple[str, bool, bool]]:
    """Extract destinations and whether they require Markdown parsing or a file."""

    style_content_spans: list[tuple[int, int]] = []
    rendered_text = markdown_searchable_text(
        text, style_content_spans=style_content_spans
    )
    style_contents = [text[start:end] for start, end in style_content_spans]
    markdown_characters = list(rendered_text)
    html_characters = list(rendered_text)
    inline_label_ends = set(markdown_label_pairs(rendered_text).values())
    paragraph_boundaries = markdown_paragraph_boundaries(rendered_text)
    for tag in MARKDOWN_HTML_TAG.finditer(rendered_text):
        if not markdown_html_tag_is_rendered(
            rendered_text, tag, paragraph_boundaries
        ):
            continue
        opening = tag.start() - 1
        if (
            opening >= 1
            and rendered_text[opening] == "("
            and opening - 1 in inline_label_ends
            and markdown_destination_end(
                rendered_text,
                opening,
                markdown_paragraph_end(rendered_text, opening),
            )
            is not None
        ):
            for position in range(*tag.span()):
                if html_characters[position] not in "\r\n":
                    html_characters[position] = " "
            continue
        for position in range(*tag.span()):
            if markdown_characters[position] not in "\r\n":
                markdown_characters[position] = " "
    text = "".join(markdown_characters)
    reference_definitions = markdown_reference_definitions(text)
    first_reference_definitions: dict[str, re.Match[str]] = {}
    for match in reference_definitions:
        label = markdown_normalize_reference_label(match.group("label"))
        first_reference_definitions.setdefault(label, match)
    reference_labels = set(first_reference_definitions)
    definition_ranges = markdown_reference_definition_ranges(
        text, reference_definitions
    )
    for definition_start, definition_end in definition_ranges:
        for position in range(definition_start, definition_end):
            if html_characters[position] not in "\r\n":
                html_characters[position] = " "
    label_pairs = markdown_label_pairs(text)
    image_label_ranges = markdown_active_image_label_ranges(
        text, reference_labels, label_pairs
    )
    for label_start, label_end in image_label_ranges:
        for position in range(label_start + 1, label_end):
            if html_characters[position] not in "\r\n":
                html_characters[position] = " "
    reference_usages = markdown_reference_usages(
        text, reference_labels, label_pairs, definition_ranges
    )
    targets: list[tuple[str, bool, bool]] = []
    definition_index = 0
    definition_end = -1
    image_index = 0
    image_end = -1
    inline_link_suffix_end = -1
    paragraph_end = -1
    for label_start, character in enumerate(text):
        if character != "[":
            continue
        if label_start < inline_link_suffix_end:
            continue
        while (
            definition_index < len(definition_ranges)
            and definition_ranges[definition_index][0] <= label_start
        ):
            definition_end = max(
                definition_end, definition_ranges[definition_index][1]
            )
            definition_index += 1
        if label_start < definition_end:
            continue
        while (
            image_index < len(image_label_ranges)
            and image_label_ranges[image_index][0] < label_start
        ):
            image_end = max(image_end, image_label_ranges[image_index][1])
            image_index += 1
        if label_start < image_end:
            continue
        if label_start >= paragraph_end:
            paragraph_end = markdown_paragraph_end(text, label_start)
        label_end = label_pairs.get(label_start)
        if label_end is None or label_end + 1 >= len(text) or text[label_end + 1] != "(":
            continue
        destination = markdown_destination_end(text, label_end + 1, paragraph_end)
        if destination is not None:
            is_image = (
                label_start > 0
                and text[label_start - 1] == "!"
                and not markdown_character_is_escaped(text, label_start - 1)
            )
            if not is_image and markdown_label_contains_active_link(
                text,
                label_start,
                label_end,
                reference_labels,
                label_pairs,
                paragraph_end,
            ):
                continue
            for position in range(label_end + 1, destination[1] + 1):
                if html_characters[position] not in "\r\n":
                    html_characters[position] = " "
            targets.append(
                (markdown_restore_escaped_openers(destination[0]), True, is_image)
            )
            inline_link_suffix_end = max(inline_link_suffix_end, destination[1] + 1)

    rendered_html_text = "".join(html_characters)
    targets.extend(
        (
            markdown_restore_escaped_openers(match.group("target")),
            True,
            reference_usages[label],
        )
        for label, match in first_reference_definitions.items()
        if label in reference_usages
    )
    targets.extend(
        html_resource_targets(rendered_html_text)
    )
    for style_content in style_contents:
        targets.extend(
            (target, False, True)
            for target in css_resource_targets(style_content)
        )
    return targets


def markdown_strip_inline_link_destinations(text: str) -> str:
    """Keep rendered labels while removing valid inline link destinations."""

    result: list[str] = []
    index = 0
    while index < len(text):
        is_image = (
            text.startswith("![", index)
            and not markdown_character_is_escaped(text, index)
        )
        label_start = index + 1 if is_image else index
        if (
            text[label_start] != "["
            or markdown_character_is_escaped(text, label_start)
        ):
            result.append(text[index])
            index += 1
            continue

        label_end = markdown_label_end(text, label_start)
        if label_end is None or label_end + 1 >= len(text) or text[label_end + 1] != "(":
            result.append(text[index])
            index += 1
            continue
        destination = markdown_destination_end(text, label_end + 1)
        if destination is None:
            result.append(text[index])
            index += 1
            continue

        result.append(text[label_start + 1 : label_end])
        index = destination[1] + 1
    return "".join(result)


def markdown_strip_inline_html_constructs(text: str) -> str:
    """Remove complete rendered inline HTML while retaining visible text."""

    spans: list[tuple[int, int]] = []
    special_search_characters = list(text)
    for tag in MARKDOWN_HTML_TAG_OR_CLOSING.finditer(text):
        spans.append(tag.span())
        for position in range(*tag.span()):
            special_search_characters[position] = " "
    special_search_text = "".join(special_search_characters)
    spans.extend(markdown_inline_html_special_spans(special_search_text))

    result: list[str] = []
    cursor = 0
    for start, end in sorted(spans):
        if start < cursor:
            cursor = max(cursor, end)
            continue
        result.append(text[cursor:start])
        cursor = end
    result.append(text[cursor:])
    return "".join(result)


def markdown_strip_active_reference_links(
    text: str, reference_labels: set[str]
) -> str:
    """Keep rendered labels while removing only active full-reference markup."""

    result: list[str] = []
    index = 0
    while index < len(text):
        is_image = (
            text.startswith("![", index)
            and not markdown_character_is_escaped(text, index)
        )
        label_start = index + 1 if is_image else index
        if (
            label_start >= len(text)
            or text[label_start] != "["
            or markdown_character_is_escaped(text, label_start)
        ):
            result.append(text[index])
            index += 1
            continue

        label_end = markdown_label_end(text, label_start)
        reference_start = None if label_end is None else label_end + 1
        if (
            reference_start is None
            or reference_start >= len(text)
            or text[reference_start] != "["
        ):
            result.append(text[index])
            index += 1
            continue
        reference_end = markdown_label_end(text, reference_start)
        if reference_end is None:
            result.append(text[index])
            index += 1
            continue

        primary_label = text[label_start + 1 : label_end]
        reference_label = text[reference_start + 1 : reference_end] or primary_label
        if (
            len(reference_label) > MARKDOWN_REFERENCE_LABEL_MAX_LENGTH
            or markdown_normalize_reference_label(reference_label)
            not in reference_labels
        ):
            result.append(text[index])
            index += 1
            continue

        result.append(primary_label)
        index = reference_end + 1
    return "".join(result)


def github_heading_slug(
    heading: str, reference_labels: set[str] | None = None
) -> str:
    """Approximate GitHub's generated heading IDs for ordinary Markdown headings."""

    heading = markdown_render_code_spans(heading)
    previous_heading: str | None = None
    while heading != previous_heading:
        previous_heading = heading
        heading = markdown_strip_active_reference_links(
            heading, reference_labels or set()
        )
        heading = markdown_strip_inline_link_destinations(heading)
    heading = MARKDOWN_AUTOLINK.sub(r"\1", heading)
    heading = markdown_strip_inline_html_constructs(heading)
    heading = heading.replace(MARKDOWN_CODE_SPAN_LT, "<").replace(
        MARKDOWN_CODE_SPAN_GT, ">"
    )
    heading = markdown_unescape(heading)
    heading = re.sub(
        r"(?<![\w\\])(?P<delimiter>_{1,3})(?=\S)(?P<content>.+?\S)"
        r"(?P=delimiter)(?!\w)",
        r"\g<content>",
        heading,
    )
    heading = re.sub(r"[*~`]", "", heading).lower()
    heading = re.sub(r"\s", "-", heading)
    characters = [
        character
        for character in heading
        if character.isalnum()
        or character in {"-", "_"}
        or unicodedata.category(character).startswith("M")
    ]
    return "".join(characters)


def markdown_html_anchor_searchable_text(text: str) -> str:
    """Mask Markdown-only HTML-shaped text before collecting explicit anchors."""

    rendered_text = markdown_searchable_text(text)
    characters = list(rendered_text)
    reference_definitions = markdown_reference_definitions(rendered_text)
    reference_labels = {
        markdown_normalize_reference_label(definition.group("label"))
        for definition in reference_definitions
    }
    definition_ranges = markdown_reference_definition_ranges(
        rendered_text, reference_definitions
    )
    label_pairs = markdown_label_pairs(rendered_text)
    image_label_ranges = markdown_active_image_label_ranges(
        rendered_text, reference_labels, label_pairs
    )

    for start, end in definition_ranges:
        for position in range(start, end):
            if characters[position] not in "\r\n":
                characters[position] = " "
    for label_start, label_end in image_label_ranges:
        for position in range(label_start + 1, label_end):
            if characters[position] not in "\r\n":
                characters[position] = " "

    inline_link_suffix_end = -1
    paragraph_end = -1
    for label_start, character in enumerate(rendered_text):
        if character != "[" or characters[label_start] == " ":
            continue
        if label_start < inline_link_suffix_end:
            continue
        label_end = label_pairs.get(label_start)
        if (
            label_end is None
            or label_end + 1 >= len(rendered_text)
            or rendered_text[label_end + 1] != "("
        ):
            continue
        if label_start >= paragraph_end:
            paragraph_end = markdown_paragraph_end(rendered_text, label_start)
        destination = markdown_destination_end(
            rendered_text, label_end + 1, paragraph_end
        )
        if destination is None:
            continue
        for position in range(label_end + 1, destination[1] + 1):
            if characters[position] not in "\r\n":
                characters[position] = " "
        inline_link_suffix_end = destination[1] + 1

    return "".join(characters)


def markdown_heading_fragments(text: str) -> set[str]:
    """Collect generated heading fragments and explicit HTML anchors outside fences."""

    fragments: set[str] = set()
    used_slugs: set[str] = set()
    next_duplicate_indexes: dict[str, int] = {}
    setext_candidate: tuple[tuple[str, ...], list[str]] | None = None

    reference_labels: set[str] = set()

    def add_heading(heading: str) -> None:
        heading = re.sub(r"[ \t]+#+[ \t]*$", "", heading)
        base = github_heading_slug(heading, reference_labels)
        if not base:
            return
        candidate = base
        if candidate in used_slugs:
            duplicate_index = next_duplicate_indexes.get(base, 1)
            candidate = f"{base}-{duplicate_index}"
            while candidate in used_slugs:
                duplicate_index += 1
                candidate = f"{base}-{duplicate_index}"
            next_duplicate_indexes[base] = duplicate_index + 1
        else:
            next_duplicate_indexes.setdefault(base, 1)
        used_slugs.add(candidate)
        fragments.add(candidate)

    lines = text.splitlines()
    searchable_text = markdown_searchable_text(text)
    structure_text_with_tags = markdown_searchable_text(text, mask_inline_code=False)
    structure_characters = list(structure_text_with_tags)
    structure_paragraph_boundaries = markdown_paragraph_boundaries(
        structure_text_with_tags
    )
    for tag in MARKDOWN_HTML_TAG.finditer(structure_text_with_tags):
        if not markdown_html_tag_is_rendered(
            structure_text_with_tags, tag, structure_paragraph_boundaries
        ):
            continue
        for position in range(*tag.span()):
            if structure_characters[position] not in "\r\n":
                structure_characters[position] = " "
    structure_lines = "".join(structure_characters).splitlines()
    structure_containers = markdown_container_lines(structure_lines)
    raw_containers = markdown_container_lines(lines)
    structure_text = "\n".join(content for _, content in structure_containers)
    reference_definitions = markdown_reference_definitions(structure_text)
    reference_labels.update(
        markdown_normalize_reference_label(definition.group("label"))
        for definition in reference_definitions
    )
    footnote_characters = list(searchable_text)
    footnote_paragraph_boundaries = markdown_paragraph_boundaries(searchable_text)
    for tag in MARKDOWN_HTML_TAG.finditer(searchable_text):
        if not markdown_html_tag_is_rendered(
            searchable_text, tag, footnote_paragraph_boundaries
        ):
            continue
        for position in range(*tag.span()):
            if footnote_characters[position] not in "\r\n":
                footnote_characters[position] = " "
    image_label_ranges = markdown_active_image_label_ranges(
        searchable_text,
        reference_labels,
        markdown_label_pairs(searchable_text),
    )
    for label_start, label_end in image_label_ranges:
        for position in range(label_start + 1, label_end):
            if footnote_characters[position] not in "\r\n":
                footnote_characters[position] = " "
    footnote_lines = "".join(footnote_characters).splitlines()
    footnote_text = "\n".join(
        content for _, content in markdown_container_lines(footnote_lines)
    )
    footnote_text = markdown_strip_inline_link_destinations(footnote_text)
    reference_definition_lines: set[int] = set()
    footnote_definition_lines: set[int] = set()
    footnote_labels: set[str] = set()
    for footnote in MARKDOWN_FOOTNOTE_DEFINITION.finditer(footnote_text):
        footnote_definition_lines.add(
            footnote_text.count("\n", 0, footnote.start())
        )
        label = MARKDOWN_BACKSLASH_ESCAPE.sub(r"\1", footnote.group("label"))
        normalized_label = markdown_unescape(label).casefold()
        footnote_labels.add(normalized_label)
        fragments.add(f"user-content-fn-{normalized_label}")
    footnote_reference_counts: dict[str, int] = {}
    for footnote in MARKDOWN_FOOTNOTE_REFERENCE.finditer(footnote_text):
        label = MARKDOWN_BACKSLASH_ESCAPE.sub(r"\1", footnote.group("label"))
        normalized_label = markdown_unescape(label).casefold()
        if normalized_label not in footnote_labels:
            continue
        count = footnote_reference_counts.get(normalized_label, 0) + 1
        footnote_reference_counts[normalized_label] = count
        suffix = "" if count == 1 else f"-{count}"
        fragments.add(f"user-content-fnref-{normalized_label}{suffix}")
    for definition in reference_definitions:
        start_line = structure_text.count("\n", 0, definition.start())
        end_line = structure_text.count(
            "\n", 0, max(definition.start(), definition.end() - 1)
        )
        reference_definition_lines.update(range(start_line, end_line + 1))
    anchor_text = markdown_html_anchor_searchable_text(text)
    for anchor in html_attribute_values(anchor_text, MARKDOWN_HTML_ID_ATTRIBUTES):
        fragments.add(html_attribute_unescape(anchor))
    for anchor in html_attribute_values(
        anchor_text,
        MARKDOWN_HTML_NAME_ATTRIBUTES,
        tag_names=MARKDOWN_HTML_LEGACY_ANCHOR_TAGS,
    ):
        fragments.add(html_attribute_unescape(anchor))
    frontmatter_end = markdown_frontmatter_end(text.splitlines(keepends=True))
    content_start = len(text[:frontmatter_end].splitlines()) if frontmatter_end else 0

    for line_index, line in enumerate(lines[content_start:], start=content_start):
        containers, structure_content = structure_containers[line_index]
        _, raw_content = raw_containers[line_index]
        parent_containers, parent_content = markdown_blockquote_content(line)
        direct_list_item = MARKDOWN_LIST_PREFIX.match(parent_content)
        non_one_ordered_interrupt = (
            direct_list_item is not None
            and direct_list_item.group("marker")[0].isdigit()
            and int(direct_list_item.group("marker")[:-1]) != 1
            and setext_candidate is not None
            and setext_candidate[0] == parent_containers
        )
        if non_one_ordered_interrupt:
            containers = parent_containers
            structure_content = parent_content
            raw_content = parent_content
        lazy_continuation = (
            setext_candidate is not None
            and containers != setext_candidate[0]
            and len(containers) < len(setext_candidate[0])
            and setext_candidate[0][: len(containers)] == containers
            and not markdown_line_interrupts_paragraph(structure_content)
        )
        if lazy_continuation:
            containers = setext_candidate[0]
        if (
            line_index in reference_definition_lines
            or line_index in footnote_definition_lines
        ):
            setext_candidate = None
            continue
        atx_heading = MARKDOWN_ATX_HEADING.match(structure_content)
        if atx_heading:
            raw_heading = MARKDOWN_ATX_HEADING.match(raw_content)
            add_heading(
                (raw_heading.group(1) if raw_heading else atx_heading.group(1)) or ""
            )
            setext_candidate = None
            continue
        if MARKDOWN_SETEXT_HEADING.match(structure_content):
            if setext_candidate and setext_candidate[0] == containers:
                add_heading(" ".join(setext_candidate[1]))
            setext_candidate = None
            continue
        if not structure_content.strip():
            setext_candidate = None
        elif setext_candidate and setext_candidate[0] == containers:
            setext_candidate[1].append(raw_content.strip())
        else:
            setext_candidate = (containers, [raw_content.strip()])

    return fragments


def find_broken_links(root: Path) -> list[str]:
    errors: list[str] = []
    repository_root = root.resolve()
    skill_root = (repository_root / "build-robot-project").resolve()
    fragment_cache: dict[Path, set[str]] = {}
    decoded_markdown_cache: dict[Path, str | None] = {}

    def read_markdown(path: Path) -> str | None:
        if path not in decoded_markdown_cache:
            decoded_markdown_cache[path] = decode_text_data(path.read_bytes())
            if decoded_markdown_cache[path] is None:
                errors.append(
                    f"{path.relative_to(root)}: undecodable textual resource"
                )
        return decoded_markdown_cache[path]

    for path in markdown_files(root):
        text = read_markdown(path)
        if text is None:
            continue
        for raw_target, is_markdown, requires_file in markdown_link_targets(text):
            target = raw_target.strip()
            if not target:
                continue
            if is_markdown:
                if target.startswith("<") and target.endswith(">"):
                    target = target[1:-1]
                    target = target.replace("\t", "%09")
                    leading_spaces = len(target) - len(target.lstrip(" "))
                    if leading_spaces:
                        target = "%20" * leading_spaces + target[leading_spaces:]
                else:
                    target = target.split(maxsplit=1)[0]
                target = MARKDOWN_BACKSLASH_ESCAPE.sub(r"\1", target)
            target = markdown_unescape(target) if is_markdown else target
            if not is_markdown:
                suffix_positions = [
                    position
                    for separator in ("?", "#")
                    if (position := target.find(separator)) >= 0
                ]
                path_end = min(suffix_positions, default=len(target))
                target = (
                    target[:path_end].replace("\\", "/") + target[path_end:]
                )
            if not target or target.startswith("/") or URI_SCHEME.match(target):
                continue
            parsed_target = urlsplit(target)
            path_target = unquote(parsed_target.path)
            fragment = unquote(parsed_target.fragment)
            if "\x00" in path_target:
                errors.append(f"{path.relative_to(root)}: broken relative link {raw_target!r}")
                continue
            try:
                resolved = (
                    (path.parent / path_target).resolve()
                    if path_target
                    else path.resolve()
                )
            except (OSError, ValueError):
                errors.append(f"{path.relative_to(root)}: broken relative link {raw_target!r}")
                continue
            if path.resolve().is_relative_to(skill_root) and not resolved.is_relative_to(skill_root):
                errors.append(
                    f"{path.relative_to(root)}: relative link escapes distributable skill "
                    f"directory {raw_target!r}"
                )
                continue
            if not resolved.is_relative_to(repository_root):
                errors.append(
                    f"{path.relative_to(root)}: relative link escapes repository checkout "
                    f"{raw_target!r}"
                )
                continue
            if not resolved.exists():
                errors.append(f"{path.relative_to(root)}: broken relative link {raw_target!r}")
                continue
            if path_target.endswith("/") and resolved.is_file():
                errors.append(f"{path.relative_to(root)}: broken relative link {raw_target!r}")
                continue
            if requires_file and not resolved.is_file():
                errors.append(
                    f"{path.relative_to(root)}: resource target is not a file {raw_target!r}"
                )
                continue
            if (
                fragment
                and resolved.is_file()
                and resolved.suffix.lower() in MARKDOWN_SUFFIXES
            ):
                if resolved not in fragment_cache:
                    resolved_text = read_markdown(resolved)
                    if resolved_text is None:
                        continue
                    fragment_cache[resolved] = markdown_heading_fragments(resolved_text)
                if fragment not in fragment_cache[resolved]:
                    errors.append(
                        f"{path.relative_to(root)}: broken Markdown fragment "
                        f"#{fragment!s} in {raw_target!r}"
                    )
    return errors


def find_portability_violations(skill_root: Path) -> list[str]:
    errors: list[str] = []
    for path in sorted(
        path
        for path in skill_root.rglob("*")
        if path.is_file()
        and path_resolves_within(path, skill_root)
        and path.relative_to(skill_root).parts[:1] != ("agents",)
    ):
        data = path.read_bytes()
        if data_looks_binary(data):
            continue
        text = decode_text_data(data)
        if text is None:
            if path.suffix.lower() in PORTABLE_TEXT_SUFFIXES:
                errors.append(
                    f"{path.relative_to(skill_root)}: undecodable textual resource"
                )
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
        and path_resolves_within(path, root)
        and not is_ignored_repository_path(path, root)
        and not is_ignored_secret_file(path)
    ):
        data = path.read_bytes()
        if data_looks_binary(data):
            continue
        text = decode_text_data(data)
        if text is None:
            if path.suffix.lower() in PORTABLE_TEXT_SUFFIXES:
                errors.append(f"{path.relative_to(root)}: undecodable textual resource")
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
        path
        for path in root.rglob("*")
        if path_resolves_within(path, root)
        and not is_ignored_repository_path(path, root)
        and not (path.is_file() and is_ignored_secret_file(path))
    ):
        if path.is_file() and path.stat().st_size == 0:
            errors.append(f"empty file: {path.relative_to(root)}")
        if path.is_dir() and not any(path.iterdir()):
            errors.append(f"empty directory: {path.relative_to(root)}")
    return errors


def validate_repository(root: Path) -> list[str]:
    errors: list[str] = []
    skill_root = root / "build-robot-project"
    repository_boundary = root.resolve()
    skill_boundary = skill_root.resolve()

    for relative in REQUIRED_ROOT_FILES:
        required = root / relative
        if not required.is_file():
            errors.append(f"missing required repository file: {relative}")
        elif not path_resolves_within(required, repository_boundary):
            errors.append(
                f"required repository file resolves outside repository: {relative}"
            )
    for relative in REQUIRED_SKILL_FILES:
        required = skill_root / relative
        if not required.is_file():
            errors.append(f"missing required skill file: build-robot-project/{relative}")
        elif not path_resolves_within(required, skill_boundary):
            errors.append(
                "required skill file resolves outside distributable skill directory: "
                f"build-robot-project/{relative}"
            )

    skill_file = skill_root / "SKILL.md"
    if skill_file.is_file() and path_resolves_within(skill_file, skill_boundary):
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
        try:
            skill_text = skill_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            skill_text = None
        if skill_text is not None:
            line_count = len(skill_text.splitlines())
            if line_count >= 500:
                errors.append(f"SKILL.md must stay below 500 lines; found {line_count}")
        estimated_tokens = math.ceil(len(body) / 4)
        if estimated_tokens >= 5000:
            errors.append(f"SKILL.md estimated token count must stay below 5000; found {estimated_tokens}")

    errors.extend(find_escaping_skill_symlinks(skill_root))
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

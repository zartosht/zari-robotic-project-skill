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
    r"(?m)^[ \t]{0,3}\[(?!\^)(?P<label>[^\]\n]+)\]:[ \t]*"
    r"(?:\n[ \t]{1,3})?(?P<target><[^>\n]+>|[^\s\n]+)"
)
MARKDOWN_BLOCKQUOTE_PREFIX = re.compile(r"^[ \t]{0,3}>[ \t]?")
MARKDOWN_LIST_PREFIX = re.compile(
    r"^(?P<indent>[ \t]{0,3})(?P<marker>[*+-]|\d{1,9}[.)])"
    r"(?P<padding>[ \t]+|$)"
)
MARKDOWN_INDENTED_CODE = re.compile(r"^(?: {4,}|\t)")
MARKDOWN_FENCE_START = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")
MARKDOWN_ATX_HEADING = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+(.+?)\s*$")
MARKDOWN_SETEXT_HEADING = re.compile(r"^[ \t]{0,3}(?:=+|-+)[ \t]*$")
MARKDOWN_HTML_TAG = re.compile(r"<[A-Za-z][^<>]*>", re.DOTALL)
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
    r"^[ \t]{0,3}</?[A-Za-z][A-Za-z0-9-]*(?:[ \t]+[^<>]*)?[ \t]*/?>[ \t]*$"
)
MARKDOWN_CODE_SPAN_LT = "\ue000"
MARKDOWN_CODE_SPAN_GT = "\ue001"
MARKDOWN_AUTOLINK = re.compile(
    r"<((?:[A-Za-z][A-Za-z0-9+.-]{1,31}:[^<>\s]*)|(?:[^<>\s@]+@[^<>\s@]+))>"
)
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
PORTABLE_TEXT_SUFFIXES = frozenset(
    {
        ".cfg",
        ".csv",
        ".ini",
        ".js",
        ".json",
        ".md",
        ".markdown",
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
)


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


def path_resolves_within(path: Path, root: Path) -> bool:
    """Return whether a path resolves inside the expected repository boundary."""

    try:
        return path.resolve().is_relative_to(root.resolve())
    except (OSError, RuntimeError):
        return False


def decode_text_data(data: bytes) -> str | None:
    """Decode UTF-8 or BOM-marked Unicode text without guessing binary data."""

    try:
        return data.decode("utf-8")
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


def markdown_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and path_resolves_within(path, root)
        and path.suffix.lower() in {".md", ".markdown"}
        and not is_ignored_repository_path(path, root)
    )


def markdown_list_prefix_end(match: re.Match[str]) -> int:
    """Return the content offset for a CommonMark list marker."""

    padding = match.group("padding")
    consumed_padding = 1 if len(padding) > 4 else len(padding)
    return match.start("padding") + consumed_padding


def markdown_line_starts_list_item(line: str) -> bool:
    """Return whether a line directly opens a list item, including in blockquotes."""

    content = line
    while blockquote := MARKDOWN_BLOCKQUOTE_PREFIX.match(content):
        content = content[blockquote.end() :]
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
    """Normalize direct containers and single-list continuation indentation."""

    normalized: list[tuple[tuple[str, ...], str]] = []
    active_list_indent: int | None = None
    for line in lines:
        leading_spaces = len(line) - len(line.lstrip(" "))
        is_continuation = (
            active_list_indent is not None
            and leading_spaces >= active_list_indent
            and bool(line.strip())
        )
        if is_continuation:
            nested_containers, content = markdown_container_content(
                line[active_list_indent:]
            )
            normalized.append((("list", *nested_containers), content))
        else:
            normalized.append(markdown_container_content(line))

        list_item = MARKDOWN_LIST_PREFIX.match(line)
        if list_item:
            active_list_indent = markdown_list_prefix_end(list_item)
        elif line.strip() and not is_continuation:
            active_list_indent = None

    return normalized


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


def mask_markdown_raw_html_blocks(characters: list[str]) -> None:
    """Mask CommonMark raw HTML block bodies while retaining opening tags."""

    text = "".join(characters)
    lines_with_endings = text.splitlines(keepends=True)
    container_lines = markdown_container_lines(
        [line.rstrip("\r\n") for line in lines_with_endings]
    )
    offset = 0
    skip_until = 0
    blank_block_start: int | None = None
    open_paragraph_containers: tuple[str, ...] | None = None

    def mask(start: int, end: int) -> None:
        for position in range(start, end):
            if characters[position] not in "\r\n":
                characters[position] = " "

    def mask_except_html_tags(start: int, end: int) -> None:
        cursor = start
        for tag in MARKDOWN_HTML_TAG.finditer(text, start, end):
            mask(cursor, tag.start())
            cursor = tag.end()
        mask(cursor, end)

    for line, (containers, content) in zip(lines_with_endings, container_lines):
        line_body = line.rstrip("\r\n")
        content_start = offset + len(line_body) - len(content)
        content_end = offset + len(line_body)

        if offset < skip_until:
            open_paragraph_containers = None
            offset += len(line)
            continue

        if blank_block_start is not None:
            if not content.strip():
                mask_except_html_tags(blank_block_start, content_start)
                blank_block_start = None
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
            opening_end = text.find(">", content_start + type_1.end())
            closing = re.compile(
                rf"</{re.escape(type_1.group('tag'))}[ \t]*>", re.IGNORECASE
            )
            if opening_end < 0:
                mask(content_start, len(text))
                skip_until = len(text)
            else:
                closing_match = closing.search(text, opening_end + 1)
                raw_end = closing_match.end() if closing_match else len(text)
                line_end = text.find("\n", raw_end)
                skip_until = len(text) if line_end < 0 else line_end + 1
                mask(opening_end + 1, skip_until)
            open_paragraph_containers = None
        elif special_end:
            marker, block_start = special_end
            absolute_start = content_start + block_start
            marker_match = re.compile(marker).search(text, absolute_start)
            raw_end = marker_match.end() if marker_match else len(text)
            line_end = text.find("\n", raw_end)
            skip_until = len(text) if line_end < 0 else line_end + 1
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
                opening_end = content.find(">", raw_tag.end())
                body_start = content_start + (
                    opening_end + 1 if opening_end >= 0 else len(content)
                )
                blank_block_start = body_start
                open_paragraph_containers = None
            elif not content.strip():
                open_paragraph_containers = None
            elif (
                MARKDOWN_ATX_HEADING.match(content)
                or MARKDOWN_SETEXT_HEADING.match(content)
            ):
                open_paragraph_containers = None
            else:
                open_paragraph_containers = containers

        offset += len(line)

    if blank_block_start is not None:
        mask_except_html_tags(blank_block_start, len(text))


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
    open_paragraph_containers: tuple[str, ...] | None = None

    container_lines = markdown_container_lines(
        [line.rstrip("\r\n") for line in lines_with_endings]
    )
    for line, (containers, container_content) in zip(lines_with_endings, container_lines):
        indented_candidate = MARKDOWN_INDENTED_CODE.match(container_content) is not None
        indented_code = (
            indented_candidate
            and (
                open_paragraph_containers != containers
                or markdown_line_starts_list_item(line.rstrip("\r\n"))
            )
        )
        fence_line = fence_character is not None
        if fence_character is None:
            match = None if indented_code else markdown_fence_opening(container_content)
            if match:
                fence = match.group(1)
                fence_character = fence[0]
                fence_length = len(fence)
                fence_line = True
        else:
            closing_fence = re.compile(
                rf"^[ \t]{{0,3}}{re.escape(fence_character)}{{{fence_length},}}[ \t]*$"
            )
            if closing_fence.match(container_content):
                fence_character = None
                fence_length = 0

        literal_block = indented_code or fence_line
        if literal_block:
            for index in range(offset, offset + len(line)):
                if characters[index] not in "\r\n":
                    characters[index] = " "

        if (
            not container_content.strip()
            or literal_block
            or MARKDOWN_ATX_HEADING.match(container_content)
            or MARKDOWN_SETEXT_HEADING.match(container_content)
        ):
            open_paragraph_containers = None
        else:
            open_paragraph_containers = containers
        offset += len(line)

    mask_markdown_raw_html_blocks(characters)

    literal_characters = characters.copy()
    masked = "".join(literal_characters)
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
        closing = -1
        while True:
            candidate = masked.find(delimiter, search_from)
            if candidate == -1:
                break
            before_is_tick = candidate > 0 and masked[candidate - 1] == "`"
            after = candidate + len(delimiter)
            after_is_tick = after < len(masked) and masked[after] == "`"
            if (
                not markdown_character_is_escaped(masked, candidate)
                and not before_is_tick
                and not after_is_tick
            ):
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


def markdown_character_is_escaped(text: str, index: int) -> bool:
    """Return whether a Markdown punctuation character has an odd escape prefix."""

    preceding_backslashes = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        preceding_backslashes += 1
        cursor -= 1
    return preceding_backslashes % 2 == 1


def markdown_normalize_reference_label(label: str) -> str:
    """Normalize a reference label for case-insensitive CommonMark matching."""

    label = MARKDOWN_BACKSLASH_ESCAPE.sub(r"\1", label)
    return " ".join(html_unescape(label).split()).casefold()


def markdown_image_reference_labels(text: str) -> set[str]:
    """Collect labels whose reference definitions are used by images."""

    labels: set[str] = set()
    index = 0
    while index + 1 < len(text):
        if (
            text[index] != "!"
            or text[index + 1] != "["
            or markdown_character_is_escaped(text, index)
        ):
            index += 1
            continue
        label_start = index + 1
        label_end = markdown_label_end(text, label_start)
        if label_end is None:
            index += 2
            continue
        primary_label = text[label_start + 1 : label_end]
        cursor = label_end + 1
        if (
            cursor < len(text)
            and text[cursor] == "("
            and markdown_destination_end(text, cursor) is not None
        ):
            index = label_end + 1
            continue
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        if cursor < len(text) and text[cursor] == "[":
            reference_end = markdown_label_end(text, cursor)
            if reference_end is None:
                index = label_end + 1
                continue
            reference_label = text[cursor + 1 : reference_end] or primary_label
            labels.add(markdown_normalize_reference_label(reference_label))
            index = reference_end + 1
            continue
        labels.add(markdown_normalize_reference_label(primary_label))
        index = label_end + 1
    return labels


def markdown_label_contains_active_link(
    text: str,
    label_start: int,
    label_end: int,
    reference_labels: set[str],
) -> bool:
    """Return whether a link label contains a nested link that deactivates it."""

    index = label_start + 1
    while index < label_end:
        if text[index] != "[" or markdown_character_is_escaped(text, index):
            index += 1
            continue
        is_image = (
            index > 0
            and text[index - 1] == "!"
            and not markdown_character_is_escaped(text, index - 1)
        )
        nested_end = markdown_label_end(text, index)
        if nested_end is None or nested_end > label_end:
            index += 1
            continue
        if is_image:
            index = nested_end + 1
            continue
        if markdown_label_contains_active_link(
            text, index, nested_end, reference_labels
        ):
            return True

        cursor = nested_end + 1
        if cursor < label_end and text[cursor] == "(":
            destination = markdown_destination_end(text, cursor)
            if destination is not None and destination[1] < label_end:
                return True
        while cursor < label_end and text[cursor].isspace():
            cursor += 1
        if cursor < label_end and text[cursor] == "[":
            reference_end = markdown_label_end(text, cursor)
            if reference_end is not None and reference_end < label_end:
                reference_label = text[cursor + 1 : reference_end]
                if not reference_label:
                    reference_label = text[index + 1 : nested_end]
                if markdown_normalize_reference_label(reference_label) in reference_labels:
                    return True
        elif (
            markdown_normalize_reference_label(text[index + 1 : nested_end])
            in reference_labels
        ):
            return True
        index = nested_end + 1
    return False


def markdown_protect_code_span_angles(text: str) -> str:
    """Protect visible angle brackets in code spans from HTML-tag stripping."""

    characters = list(text)
    index = 0
    while index < len(text):
        if text[index] != "`" or markdown_character_is_escaped(text, index):
            index += 1
            continue
        run_end = index
        while run_end < len(text) and text[run_end] == "`":
            run_end += 1
        delimiter = text[index:run_end]
        closing = text.find(delimiter, run_end)
        while closing >= 0:
            before_is_tick = closing > 0 and text[closing - 1] == "`"
            after = closing + len(delimiter)
            after_is_tick = after < len(text) and text[after] == "`"
            if not before_is_tick and not after_is_tick:
                break
            closing = text.find(delimiter, closing + len(delimiter))
        if closing < 0:
            index = run_end
            continue
        for position in range(run_end, closing):
            if characters[position] == "<":
                characters[position] = MARKDOWN_CODE_SPAN_LT
            elif characters[position] == ">":
                characters[position] = MARKDOWN_CODE_SPAN_GT
        index = closing + len(delimiter)
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


def markdown_link_targets(text: str) -> list[tuple[str, bool, bool]]:
    """Extract Markdown and rendered raw-HTML destinations."""

    rendered_text = markdown_searchable_text(text)
    markdown_characters = list(rendered_text)
    for tag in MARKDOWN_HTML_TAG.finditer(rendered_text):
        for position in range(*tag.span()):
            if markdown_characters[position] not in "\r\n":
                markdown_characters[position] = " "
    text = "".join(markdown_characters)
    container_text = "\n".join(
        content for _, content in markdown_container_lines(text.splitlines())
    )
    reference_definitions = list(
        MARKDOWN_REFERENCE_DEFINITION.finditer(container_text)
    )
    reference_labels = {
        markdown_normalize_reference_label(match.group("label"))
        for match in reference_definitions
    }
    image_reference_labels = markdown_image_reference_labels(text)
    targets: list[tuple[str, bool, bool]] = []
    for label_start, character in enumerate(text):
        if character != "[":
            continue
        label_end = markdown_label_end(text, label_start)
        if label_end is None or label_end + 1 >= len(text) or text[label_end + 1] != "(":
            continue
        destination = markdown_destination_end(text, label_end + 1)
        if destination is not None:
            is_image = (
                label_start > 0
                and text[label_start - 1] == "!"
                and not markdown_character_is_escaped(text, label_start - 1)
            )
            if not is_image and markdown_label_contains_active_link(
                text, label_start, label_end, reference_labels
            ):
                continue
            targets.append((destination[0], True, is_image))

    targets.extend(
        (
            match.group("target"),
            True,
            markdown_normalize_reference_label(match.group("label"))
            in image_reference_labels,
        )
        for match in reference_definitions
    )
    targets.extend(
        (target, False, False)
        for target in html_attribute_values(rendered_text, MARKDOWN_HTML_TARGET)
    )
    return targets


def github_heading_slug(heading: str) -> str:
    """Approximate GitHub's generated heading IDs for ordinary Markdown headings."""

    heading = markdown_protect_code_span_angles(heading)
    heading = re.sub(r"!\[([^\]]*)\]\s*\[[^\]]*\]", r"\1", heading)
    heading = re.sub(r"\[([^\]]+)\]\s*\[[^\]]*\]", r"\1", heading)
    heading = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", heading)
    heading = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", heading)
    heading = MARKDOWN_AUTOLINK.sub(r"\1", heading)
    heading = re.sub(r"<[^>]+>", "", heading)
    heading = heading.replace(MARKDOWN_CODE_SPAN_LT, "<").replace(
        MARKDOWN_CODE_SPAN_GT, ">"
    )
    heading = html_unescape(heading)
    heading = re.sub(
        r"(?<![\w\\])(?P<delimiter>_{1,2})(?=\S)(?P<content>.+?\S)"
        r"(?P=delimiter)(?!\w)",
        r"\g<content>",
        heading,
    )
    heading = re.sub(r"[*~`]", "", heading).lower()
    characters = [
        character
        for character in heading
        if character.isalnum() or character in {"-", "_"} or character.isspace()
    ]
    return re.sub(r"\s", "-", "".join(characters).strip())


def markdown_heading_fragments(text: str) -> set[str]:
    """Collect generated heading fragments and explicit HTML anchors outside fences."""

    fragments: set[str] = set()
    used_slugs: set[str] = set()
    setext_candidate: tuple[tuple[str, ...], list[str]] | None = None

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
    structure_containers = markdown_container_lines(structure_lines)
    raw_containers = markdown_container_lines(lines)
    for anchor in html_attribute_values(searchable_text, MARKDOWN_HTML_ANCHOR):
        fragments.add(html_unescape(anchor))
    content_start = 0
    if lines and lines[0].strip() == "---":
        for line_index, line in enumerate(lines[1:], start=1):
            if line.strip() in {"---", "..."}:
                content_start = line_index + 1
                break

    for line_index, line in enumerate(lines[content_start:], start=content_start):
        containers, structure_content = structure_containers[line_index]
        _, raw_content = raw_containers[line_index]
        atx_heading = MARKDOWN_ATX_HEADING.match(structure_content)
        if atx_heading:
            raw_heading = MARKDOWN_ATX_HEADING.match(raw_content)
            add_heading(raw_heading.group(1) if raw_heading else atx_heading.group(1))
            setext_candidate = None
            continue
        if (
            MARKDOWN_SETEXT_HEADING.match(structure_content)
            and setext_candidate
            and setext_candidate[0] == containers
        ):
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
    for path in markdown_files(root):
        text = path.read_text(encoding="utf-8")
        for raw_target, is_markdown, is_image in markdown_link_targets(text):
            target = raw_target.strip()
            if not target:
                continue
            if is_markdown:
                if target.startswith("<") and ">" in target:
                    target = target[1 : target.index(">")]
                else:
                    target = target.split(maxsplit=1)[0]
                target = MARKDOWN_BACKSLASH_ESCAPE.sub(r"\1", target)
            target = html_unescape(target)
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
            if is_image and not resolved.is_file():
                errors.append(
                    f"{path.relative_to(root)}: image target is not a file {raw_target!r}"
                )
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
    for path in sorted(
        path
        for path in portable_paths
        if path.is_file() and path_resolves_within(path, skill_root)
    ):
        data = path.read_bytes()
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
        text = decode_text_data(path.read_bytes())
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

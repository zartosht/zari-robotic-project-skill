#!/usr/bin/env python3
"""Deterministic repository checks for Zari Robot Project Builder."""

from __future__ import annotations

import argparse
import math
import os
import re
import sys
import unicodedata
import xml.etree.ElementTree as ElementTree
from bisect import bisect_left, bisect_right
from html import unescape as html_unescape
from html.entities import html5 as HTML5_ENTITIES
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urljoin, urlsplit


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
    rf"(?:[ \t\f\r\n]+{MARKDOWN_HTML_ATTRIBUTE_NAME}"
    rf"(?:[ \t\f\r\n]*=[ \t\f\r\n]*{MARKDOWN_HTML_ATTRIBUTE_VALUE})?)*"
    rf"[ \t\f\r\n]*/?>"
)
MARKDOWN_HTML_TAG_OR_CLOSING = re.compile(
    rf"(?:{MARKDOWN_HTML_TAG.pattern}|</[A-Za-z][A-Za-z0-9-]*[ \t\f\r\n]*>)"
)
HTML_RAW_BLOCK_ATTRIBUTE_NAME = r'''[^\t\n\f\r "'=<>`/]+'''
HTML_RAW_BLOCK_ATTRIBUTE_VALUE = r'''(?:[^\t\n\f\r "'=<>`]+|"[^"]*"|'[^']*')'''
HTML_RAW_BLOCK_TAG = re.compile(
    rf"<[A-Za-z][A-Za-z0-9-]*"
    rf"(?:[ \t\f\r\n]+{HTML_RAW_BLOCK_ATTRIBUTE_NAME}"
    rf"(?:[ \t\f\r\n]*=[ \t\f\r\n]*{HTML_RAW_BLOCK_ATTRIBUTE_VALUE})?)*"
    rf"[ \t\f\r\n]*/?>"
)
HTML_RAW_BLOCK_TAG_OR_CLOSING = re.compile(
    rf"(?:{HTML_RAW_BLOCK_TAG.pattern}|</[A-Za-z][A-Za-z0-9-]*[ \t\f\r\n]*>)"
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
HTML_SCRIPTING_ENABLED_RAW_TEXT_TAGS = (
    MARKDOWN_HTML_RAW_TEXT_OR_RCDATA_TAGS | frozenset({"noscript"})
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
MARKDOWN_HTML_NAVIGATION_HREF_TAGS = frozenset({"a", "area"})
MARKDOWN_HTML_LINK_TAGS = frozenset({"link"})
MARKDOWN_HTML_HREF_TAGS = MARKDOWN_HTML_NAVIGATION_HREF_TAGS | MARKDOWN_HTML_LINK_TAGS
MARKDOWN_HTML_LINK_RESOURCE_RELATIONS = frozenset(
    {
        "apple-touch-icon",
        "apple-touch-startup-image",
        "icon",
        "manifest",
        "mask-icon",
        "modulepreload",
        "prefetch",
        "preload",
        "prerender",
        "stylesheet",
    }
)
MARKDOWN_HTML_LINK_ORIGIN_HINT_RELATIONS = frozenset(
    {"dns-prefetch", "preconnect"}
)
MARKDOWN_SVG_RESOURCE_HREF_ATTRIBUTES = frozenset({"href", "xlink:href"})
MARKDOWN_SVG_RESOURCE_HREF_TAGS = frozenset(
    {"feimage", "image", "script", "use"}
)
MARKDOWN_SVG_NAVIGATION_HREF_TAGS = frozenset({"a"})
SVG_PRESENTATION_RESOURCE_ATTRIBUTES = frozenset(
    {
        "clip-path",
        "fill",
        "filter",
        "marker",
        "marker-end",
        "marker-mid",
        "marker-start",
        "mask",
        "stroke",
    }
)
MARKDOWN_HTML_SRC_TAGS = frozenset(
    {
        "audio",
        "embed",
        "frame",
        "iframe",
        "img",
        "script",
        "track",
        "video",
    }
)
MARKDOWN_HTML_EMBEDDED_DOCUMENT_SRC_TAGS = frozenset(
    {"embed", "frame", "iframe"}
)
MARKDOWN_HTML_INPUT_TAGS = frozenset({"input"})
MARKDOWN_HTML_IMAGE_INPUT_TYPES = frozenset({"image"})
MARKDOWN_HTML_DATA_TAGS = frozenset({"object"})
MARKDOWN_HTML_EMBEDDED_DOCUMENT_DATA_TAGS = frozenset({"object"})
MARKDOWN_HTML_POSTER_TAGS = frozenset({"video"})
MARKDOWN_HTML_BACKGROUND_TAGS = frozenset(
    {"body", "table", "tbody", "td", "tfoot", "th", "thead", "tr"}
)
MARKDOWN_HTML_MAP_TAGS = frozenset({"map"})
HTML_DECLARATIVE_SHADOW_ROOT_MODES = frozenset({"closed", "open"})
HTML_FRAMESET_ALLOWED_START_TAGS = frozenset({"frame", "frameset", "noframes"})
CSS_RESOURCE_PROPERTIES = frozenset(
    {
        "-moz-binding",
        "-webkit-backdrop-filter",
        "-webkit-border-image",
        "-webkit-box-reflect",
        "-webkit-mask",
        "-webkit-mask-box-image",
        "-webkit-mask-box-image-source",
        "-webkit-mask-image",
        "backdrop-filter",
        "background",
        "background-image",
        "border-image",
        "border-image-source",
        "clip-path",
        "content",
        "cue",
        "cue-after",
        "cue-before",
        "cursor",
        "fill",
        "filter",
        "list-style",
        "list-style-image",
        "marker",
        "marker-end",
        "marker-mid",
        "marker-start",
        "mask",
        "mask-border",
        "mask-border-source",
        "mask-box-image",
        "mask-box-image-source",
        "mask-image",
        "offset-path",
        "play-during",
        "shape-outside",
        "stroke",
    }
)
CSS_RESOURCE_DESCRIPTORS = {
    "additive-symbols": frozenset({"counter-style"}),
    "negative": frozenset({"counter-style"}),
    "pad": frozenset({"counter-style"}),
    "prefix": frozenset({"counter-style"}),
    "src": frozenset({"color-profile", "font-face"}),
    "suffix": frozenset({"counter-style"}),
    "symbols": frozenset({"counter-style"}),
}
MARKDOWN_HTML_SRCSET_ATTRIBUTES = frozenset({"srcset"})
MARKDOWN_HTML_SRCSET_TAGS = frozenset({"img"})
MARKDOWN_HTML_IMAGESRCSET_ATTRIBUTES = frozenset({"imagesrcset"})
MARKDOWN_HTML_IMAGE_PRELOAD_AS_VALUES = frozenset({"image"})
MARKDOWN_HTML_SRCDOC_ATTRIBUTES = frozenset({"srcdoc"})
MARKDOWN_HTML_SRCDOC_TAGS = frozenset({"iframe"})
MARKDOWN_HTML_STYLE_ATTRIBUTES = frozenset({"style"})
MARKDOWN_HTML_BASE_TAGS = frozenset({"base"})
MARKDOWN_HTML_META_TAGS = frozenset({"meta"})
MARKDOWN_HTML_CONTENT_ATTRIBUTES = frozenset({"content"})
MARKDOWN_HTML_FORM_TAGS = frozenset({"form"})
MARKDOWN_HTML_BUTTON_TAGS = frozenset({"button"})
MARKDOWN_HTML_NON_SUBMIT_BUTTON_TYPES = frozenset({"button", "reset"})
HTML_VOID_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "source",
        "track",
        "wbr",
    }
)
HTML_SELECT_ALLOWED_START_TAGS = frozenset(
    {"hr", "optgroup", "option", "script", "template"}
)
HTML_SELECT_BREAKOUT_START_TAGS = frozenset({"input", "keygen", "textarea"})
MARKDOWN_HTML_SUBMIT_INPUT_TYPES = frozenset({"image", "submit"})
HTML_NAMESPACE = "html"
SVG_NAMESPACE = "svg"
MATHML_NAMESPACE = "mathml"
XHTML_XML_NAMESPACE = "http://www.w3.org/1999/xhtml"
SVG_XML_NAMESPACE = "http://www.w3.org/2000/svg"
XML_ID_ATTRIBUTE = "{http://www.w3.org/XML/1998/namespace}id"
XML_BASE_ATTRIBUTE = "{http://www.w3.org/XML/1998/namespace}base"
SVG_HTML_INTEGRATION_POINTS = frozenset({"desc", "foreignobject", "title"})
MATHML_TEXT_INTEGRATION_POINTS = frozenset({"mi", "mn", "mo", "ms", "mtext"})
HTML_FOREIGN_CONTENT_BREAKOUT_START_TAGS = frozenset(
    {
        "b",
        "big",
        "blockquote",
        "body",
        "br",
        "center",
        "code",
        "dd",
        "div",
        "dl",
        "dt",
        "em",
        "embed",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "head",
        "hr",
        "i",
        "img",
        "li",
        "listing",
        "menu",
        "meta",
        "nobr",
        "ol",
        "p",
        "pre",
        "ruby",
        "s",
        "small",
        "span",
        "strong",
        "strike",
        "sub",
        "sup",
        "table",
        "tt",
        "u",
        "ul",
        "var",
    }
)
HTML_JAVASCRIPT_MIME_TYPE_ESSENCES = frozenset(
    {
        "application/ecmascript",
        "application/javascript",
        "application/x-ecmascript",
        "application/x-javascript",
        "text/ecmascript",
        "text/javascript",
        "text/javascript1.0",
        "text/javascript1.1",
        "text/javascript1.2",
        "text/javascript1.3",
        "text/javascript1.4",
        "text/javascript1.5",
        "text/jscript",
        "text/livescript",
        "text/x-ecmascript",
        "text/x-javascript",
    }
)
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
URI_SPAN = re.compile(r"\b[A-Za-z][A-Za-z0-9+.-]*://[^\s<>\"']+")
URL_INTERNAL_ASCII_WHITESPACE_TRANSLATION = str.maketrans("", "", "\t\n\r")
CSS_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")
PERCENT_ENCODED_PATH_SEPARATOR = re.compile(r"(%(?:2[fF]|5[cC]))")
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
HTML_TEXT_SUFFIXES = frozenset({".htm", ".html"})
XHTML_SUFFIXES = frozenset({".xht", ".xhtml"})
HTML_SUFFIXES = HTML_TEXT_SUFFIXES | XHTML_SUFFIXES
SVG_SUFFIXES = frozenset({".svg"})
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


def markdown_splitlines(text: str, *, keepends: bool = False) -> list[str]:
    """Split Markdown on its CR/LF line endings, not other Unicode separators."""

    parts = re.split(r"(\r\n|\r|\n)", text)
    lines = [
        parts[index] + (parts[index + 1] if keepends else "")
        for index in range(0, len(parts) - 1, 2)
    ]
    if parts[-1]:
        lines.append(parts[-1])
    return lines


def parse_frontmatter(path: Path) -> tuple[dict[str, str], str, list[str]]:
    """Parse the intentionally simple scalar YAML frontmatter used by this skill."""

    errors: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return {}, "", [f"{path}: SKILL.md must be valid UTF-8"]
    lines = markdown_splitlines(text)
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
    nested_style_sources: list[str] | None = None,
    module_script_content_spans: list[tuple[int, int]] | None = None,
) -> None:
    """Mask CommonMark raw HTML block bodies while retaining opening tags."""

    text = "".join(characters)
    lines_with_endings = markdown_splitlines(text, keepends=True)
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
    blank_block_tag_start: int | None = None
    open_paragraph_containers: tuple[str, ...] | None = None

    def mask(start: int, end: int) -> None:
        for position in range(start, end):
            if characters[position] not in "\r\n":
                characters[position] = " "

    def collect_nested_style_sources(block_start: int, block_end: int) -> None:
        if nested_style_sources is None or block_start >= block_end:
            return
        nested_style_sources.extend(
            html_style_contents(
                mask_html_template_contents(text[block_start:block_end])
            )
        )

    def normalize_raw_html_attribute_names(start: int, end: int) -> None:
        def skip_whitespace(index: int) -> int:
            while index < end and text[index] in HTML_ASCII_WHITESPACE:
                if text[index] == "\f":
                    characters[index] = " "
                index += 1
            return index

        index = start + 1
        if index < end and text[index] == "/":
            return
        while index < end and (
            text[index].isascii() and (text[index].isalnum() or text[index] == "-")
        ):
            index += 1
        while index < end:
            index = skip_whitespace(index)
            if index >= end or text[index] in {"/", ">"}:
                return
            name_start = index
            while (
                index < end
                and text[index] not in HTML_ASCII_WHITESPACE
                and text[index] not in "\"'=<>`/"
            ):
                index += 1
            for position in range(name_start, index):
                character = text[position]
                valid = (
                    character.isascii()
                    and (
                        character.isalpha()
                        or character in {"_", ":"}
                        or (
                            position > name_start
                            and (character.isdigit() or character in {".", "-"})
                        )
                    )
                )
                if not valid:
                    characters[position] = "x"
            index = skip_whitespace(index)
            if index >= end or text[index] != "=":
                continue
            index += 1
            index = skip_whitespace(index)
            if index < end and text[index] in {'"', "'"}:
                quote = text[index]
                index += 1
                while index < end and text[index] != quote:
                    index += 1
                if index < end:
                    index += 1
            else:
                while (
                    index < end
                    and text[index] not in HTML_ASCII_WHITESPACE
                    and text[index] not in "\"'=<>`"
                ):
                    index += 1

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
        for tag in HTML_RAW_BLOCK_TAG_OR_CLOSING.finditer(text, start, end):
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
            normalize_raw_html_attribute_names(*tag.span())
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
                if blank_block_tag_start is not None:
                    collect_nested_style_sources(
                        blank_block_tag_start, blank_block_end
                    )
                mask_except_html_tags(blank_block_start, blank_block_end)
                blank_block_start = None
                blank_block_tag_start = None
            elif not content.strip():
                if blank_block_tag_start is not None:
                    collect_nested_style_sources(
                        blank_block_tag_start, content_start
                    )
                mask_except_html_tags(blank_block_start, content_start)
                blank_block_start = None
                blank_block_tag_start = None
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
            opening_tag = HTML_RAW_BLOCK_TAG.match(
                text, tag_start, raw_container_end
            )
            if opening_tag is not None:
                normalize_raw_html_attribute_names(*opening_tag.span())
            closing = re.compile(
                rf"</{re.escape(tag_name)}[ \t\f\r\n]*>", re.IGNORECASE
            )
            closing_match = closing.search(
                text,
                opening_tag.end() if opening_tag else content_start + type_1.end(),
                raw_container_end,
            )
            raw_end = closing_match.end() if closing_match else raw_container_end
            if style_content_spans is not None and tag_name == "style" and opening_tag:
                style_types = html_attribute_values(
                    opening_tag.group(0),
                    frozenset({"type"}),
                    tag_names=frozenset({"style"}),
                )
                if not style_types or html_style_type_uses_css(
                    html_attribute_unescape(style_types[0])
                ):
                    style_content_spans.append(
                        (
                            opening_tag.end(),
                            closing_match.start()
                            if closing_match
                            else raw_container_end,
                        )
                    )
            if (
                module_script_content_spans is not None
                and tag_name == "script"
                and opening_tag
            ):
                script_tag = opening_tag.group(0)
                type_values = html_attribute_values(
                    script_tag,
                    frozenset({"type"}),
                    tag_names=frozenset({"script"}),
                )
                src_values = html_attribute_values(
                    script_tag,
                    frozenset({"src"}),
                    tag_names=frozenset({"script"}),
                )
                script_attributes = {
                    "type": (
                        html_attribute_unescape(type_values[0])
                        if type_values
                        else ""
                    )
                }
                if html_script_is_module(script_attributes) and not src_values:
                    module_script_content_spans.append(
                        (
                            opening_tag.end(),
                            closing_match.start()
                            if closing_match
                            else raw_container_end,
                        )
                    )
            skip_until = line_end_after(raw_end, raw_container_end)
            if opening_tag is None:
                mask(content_start, skip_until)
            elif tag_name == "style" and closing_match is not None:
                mask(opening_tag.end(), closing_match.start())
                mask_except_html_tags(closing_match.start(), skip_until)
            elif tag_name == "pre":
                mask_except_html_tags(opening_tag.end(), skip_until)
            elif closing_match is not None:
                mask(opening_tag.end(), closing_match.start())
                mask(closing_match.end(), skip_until)
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
                opening_tag = HTML_RAW_BLOCK_TAG.match(
                    text, tag_start, raw_container_end
                )
                if opening_tag is not None:
                    normalize_raw_html_attribute_names(*opening_tag.span())
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
                    if closing_match is None:
                        mask(body_start, skip_until)
                    else:
                        mask(body_start, closing_match.start())
                        mask(closing_match.end(), skip_until)
                else:
                    blank_block_start = body_start
                    blank_block_end = raw_container_end
                    blank_block_tag_start = tag_start
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
        if blank_block_tag_start is not None:
            collect_nested_style_sources(
                blank_block_tag_start, blank_block_end
            )
        mask_except_html_tags(blank_block_start, blank_block_end)


def markdown_frontmatter_end(lines_with_endings: list[str]) -> int:
    """Return the end offset of recognized mapping frontmatter, if present."""

    if not lines_with_endings:
        return 0
    opening = lines_with_endings[0].rstrip("\r\n").rstrip(" \t")
    if opening != "---":
        return 0

    offset = len(lines_with_endings[0])
    keys: set[str] = set()
    for line in lines_with_endings[1:]:
        offset += len(line)
        stripped = line.strip()
        delimiter = line.rstrip("\r\n").rstrip(" \t")
        if delimiter in {"---", "..."}:
            return offset if keys else 0
        if not stripped or stripped.startswith("#"):
            continue
        if line.startswith((" ", "\t")):
            if not keys:
                return 0
            continue
        if ":" not in line or line.startswith("-"):
            return 0
        key, _ = line.split(":", 1)
        key = key.strip()
        if not key or key in keys:
            return 0
        keys.add(key)
    return 0


def markdown_normalize_footnote_label(label: str) -> str:
    """Normalize one GFM footnote label for matching."""

    label = MARKDOWN_BACKSLASH_ESCAPE.sub(r"\1", label)
    return markdown_unescape(label).casefold()


def markdown_footnote_reference_labels(searchable_text: str) -> set[str]:
    """Return rendered footnote labels referenced by searchable Markdown."""

    characters = list(searchable_text)
    lines_with_endings = markdown_splitlines(searchable_text, keepends=True)
    lines = [line.rstrip("\r\n") for line in lines_with_endings]
    container_lines = markdown_container_lines(lines)
    offset = 0
    for line, (_, content) in zip(lines_with_endings, container_lines):
        if MARKDOWN_FOOTNOTE_DEFINITION.match(content) is not None:
            for position in range(offset, offset + len(line)):
                if characters[position] not in "\r\n":
                    characters[position] = " "
        offset += len(line)

    paragraph_boundaries = markdown_paragraph_boundaries(searchable_text)
    for tag in MARKDOWN_HTML_TAG.finditer(searchable_text):
        if not markdown_html_tag_is_rendered(
            searchable_text, tag, paragraph_boundaries
        ):
            continue
        for position in range(*tag.span()):
            if characters[position] not in "\r\n":
                characters[position] = " "

    labels_text = "".join(characters)
    label_pairs = markdown_label_pairs(labels_text)
    inline_context = markdown_inline_block_context(labels_text)
    for label_start, label_end in label_pairs.items():
        if (
            label_start == 0
            or labels_text[label_start - 1] != "!"
            or markdown_character_is_escaped(labels_text, label_start - 1)
        ):
            continue
        for position in range(label_start + 1, label_end):
            if characters[position] not in "\r\n":
                characters[position] = " "

    for label_start, label_end in label_pairs.items():
        opening = label_end + 1
        if opening >= len(labels_text) or labels_text[opening] != "(":
            continue
        destination = markdown_destination_end(
            labels_text,
            opening,
            markdown_inline_block_end(
                labels_text, label_start, inline_context
            ),
        )
        if destination is None:
            continue
        for position in range(opening, destination[1] + 1):
            if characters[position] not in "\r\n":
                characters[position] = " "

    reference_text = "".join(characters)
    return {
        markdown_normalize_footnote_label(match.group("label"))
        for match in MARKDOWN_FOOTNOTE_REFERENCE.finditer(reference_text)
    }


def markdown_footnote_continuation_lines(
    container_lines: list[tuple[tuple[str, ...], str]],
    referenced_labels: set[str],
) -> set[int]:
    """Return indented block lines that remain inside footnote definitions."""

    continuation_lines: set[int] = set()
    active_containers: tuple[str, ...] | None = None
    for line_index, (containers, content) in enumerate(container_lines):
        if active_containers is not None:
            if containers != active_containers:
                active_containers = None
            elif not content.strip():
                continue
            elif MARKDOWN_INDENTED_CODE.match(content) is not None:
                continuation_lines.add(line_index)
                continue
            else:
                active_containers = None
        definition = MARKDOWN_FOOTNOTE_DEFINITION.match(content)
        if definition is not None:
            label = markdown_normalize_footnote_label(definition.group("label"))
            active_containers = containers if label in referenced_labels else None
    return continuation_lines


def markdown_searchable_text(
    text: str,
    *,
    mask_inline_code: bool = True,
    style_content_spans: list[tuple[int, int]] | None = None,
    nested_style_sources: list[str] | None = None,
    module_script_content_spans: list[tuple[int, int]] | None = None,
    _footnote_reference_labels: set[str] | None = None,
) -> str:
    """Mask literal Markdown regions while preserving offsets and line structure."""

    characters = list(text)
    lines_with_endings = markdown_splitlines(text, keepends=True)
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
    if _footnote_reference_labels is None:
        has_footnote_definition = any(
            MARKDOWN_FOOTNOTE_DEFINITION.match(content) is not None
            for _, content in container_lines
        )
        if not has_footnote_definition:
            _footnote_reference_labels = set()
        else:
            footnote_reference_text = markdown_searchable_text(
                text,
                mask_inline_code=True,
                _footnote_reference_labels=set(),
            )
            _footnote_reference_labels = markdown_footnote_reference_labels(
                footnote_reference_text
            )
    footnote_continuation_lines = markdown_footnote_continuation_lines(
        container_lines, _footnote_reference_labels
    )
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
            and line_index not in footnote_continuation_lines
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
        characters,
        reference_definition_lines,
        style_content_spans,
        nested_style_sources,
        module_script_content_spans,
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

    definitions, _ = markdown_reference_definitions_with_lines(
        markdown_splitlines(text)
    )
    return definitions


def markdown_reference_definition_ranges(
    text: str, definitions: list[re.Match[str]]
) -> list[tuple[int, int]]:
    """Map normalized reference-definition matches to original line ranges."""

    if not definitions:
        return []

    lines_with_endings = markdown_splitlines(text, keepends=True)
    container_text = "\n".join(
        content
        for _, content in markdown_container_lines(markdown_splitlines(text))
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
    excluded_attribute_values: dict[str, frozenset[str]] | None = None,
    excluded_attribute_names_by_tag: dict[str, frozenset[str]] | None = None,
    required_attribute_tokens: dict[str, frozenset[str]] | None = None,
    excluded_attribute_tokens: dict[str, frozenset[str]] | None = None,
    excluded_attribute_predicate: Callable[[str, dict[str, str]], bool]
    | None = None,
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
        required_values_match = required_attribute_values is None or all(
            html_attribute_unescape(attributes.get(name, "")).casefold()
            in allowed_values
            for name, allowed_values in required_attribute_values.items()
        )
        excluded_values_match = excluded_attribute_values is not None and any(
            html_attribute_unescape(attributes.get(name, "")).casefold()
            in excluded_values
            for name, excluded_values in excluded_attribute_values.items()
        )
        excluded_names = (
            excluded_attribute_names_by_tag.get(tag_name, frozenset())
            if excluded_attribute_names_by_tag is not None
            else frozenset()
        )
        attribute_tokens = {
            name: frozenset(
                re.findall(
                    r"[^\t\n\f\r ]+",
                    html_attribute_unescape(attributes.get(name, "")).casefold(),
                )
            )
            for name in {
                *(required_attribute_tokens or {}),
                *(excluded_attribute_tokens or {}),
            }
        }
        required_tokens_match = required_attribute_tokens is None or all(
            attribute_tokens[name].intersection(allowed_tokens)
            for name, allowed_tokens in required_attribute_tokens.items()
        )
        excluded_tokens_match = excluded_attribute_tokens is not None and any(
            attribute_tokens[name].intersection(excluded_tokens)
            for name, excluded_tokens in excluded_attribute_tokens.items()
        )
        if (
            required_values_match
            and not excluded_values_match
            and required_tokens_match
            and not excluded_names.intersection(attributes)
            and not excluded_tokens_match
            and not (
                excluded_attribute_predicate is not None
                and excluded_attribute_predicate(tag_name, attributes)
            )
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


def html_srcset_candidate_data(value: str) -> list[tuple[str, list[str]]]:
    """Extract accepted srcset URLs together with their descriptors."""

    candidates: list[tuple[str, list[str]]] = []
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
            candidates.append((url, []))
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
            candidates.append((url, descriptors))
        if index < len(value) and value[index] == ",":
            index += 1
    return candidates


def html_srcset_candidates(value: str) -> list[str]:
    """Extract URL candidates accepted by the HTML srcset parser."""

    return [url for url, _ in html_srcset_candidate_data(value)]


def html_srcset_overrides_src(value: str) -> bool:
    """Return whether a parsed srcset replaces an img src candidate."""

    for _, descriptors in html_srcset_candidate_data(value):
        if not descriptors or any(descriptor.endswith("w") for descriptor in descriptors):
            return True
        if len(descriptors) == 1 and descriptors[0].endswith("x"):
            if float(descriptors[0][:-1]) == 1:
                return True
    return False


def html_script_type_uses_src(value: str) -> bool:
    """Return whether a script type can fetch and execute its src URL."""

    normalized = value.strip("\t\n\f\r ").casefold()
    if normalized in {"", "module"}:
        return True
    essence = normalized.split(";", 1)[0].rstrip("\t\n\f\r ")
    return essence in HTML_JAVASCRIPT_MIME_TYPE_ESSENCES


def html_script_attributes_use_src(attributes: dict[str, str]) -> bool:
    """Return whether decoded script attributes select an executable type."""

    if "type" in attributes:
        return html_script_type_uses_src(attributes["type"])
    language = attributes.get("language", "").strip("\t\n\f\r ")
    if language:
        return html_script_type_uses_src(f"text/{language}")
    return True


def html_script_is_module(attributes: dict[str, str]) -> bool:
    """Return whether script attributes select a JavaScript module script."""

    return attributes.get("type", "").strip("\t\n\f\r ").casefold() == "module"


def html_style_type_uses_css(value: str) -> bool:
    """Return whether a decoded style type selects CSS."""

    normalized = value.strip("\t\n\f\r ").casefold()
    if not normalized:
        return True
    return normalized.split(";", 1)[0].rstrip("\t\n\f\r ") == "text/css"


def css_escape_value(text: str, start: int) -> tuple[str, int] | None:
    """Decode one CSS escape and return its value and following offset."""

    index = start + 1
    if index >= len(text):
        return None
    if text[index] in CSS_HEX_DIGITS:
        value_end = index
        while (
            value_end < len(text)
            and value_end - index < 6
            and text[value_end] in CSS_HEX_DIGITS
        ):
            value_end += 1
        code_point = int(text[index:value_end], 16)
        if value_end < len(text) and text[value_end] in HTML_ASCII_WHITESPACE:
            if (
                text[value_end] == "\r"
                and value_end + 1 < len(text)
                and text[value_end + 1] == "\n"
            ):
                value_end += 2
            else:
                value_end += 1
        if (
            code_point == 0
            or code_point > 0x10FFFF
            or 0xD800 <= code_point <= 0xDFFF
        ):
            return "\N{REPLACEMENT CHARACTER}", value_end
        return chr(code_point), value_end
    if text[index] == "\r":
        return "", index + 2 if text.startswith("\r\n", index) else index + 1
    if text[index] in "\n\f":
        return "", index + 1
    return text[index], index + 1


def css_unescape(text: str) -> str | None:
    """Decode CSS escapes in an unquoted URL token."""

    value: list[str] = []
    index = 0
    while index < len(text):
        if text[index] != "\\":
            value.append(text[index])
            index += 1
            continue
        escaped = css_escape_value(text, index)
        if escaped is None:
            return None
        decoded, next_index = escaped
        if not decoded and next_index > index + 1:
            return None
        value.append(decoded)
        index = next_index
    return "".join(value)


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
            escaped = css_escape_value(text, index)
            if escaped is None:
                return None
            decoded, index = escaped
            value.append(decoded)
            continue
        if character in "\r\n\f":
            return None
        value.append(character)
        index += 1
    return None


def css_name_character(character: str) -> bool:
    """Return whether one decoded character can continue a CSS name."""

    return bool(character) and (
        (character.isascii() and (character.isalnum() or character in {"_", "-"}))
        or not character.isascii()
    )


def css_identifier_value(text: str, start: int) -> tuple[str, int] | None:
    """Decode a CSS identifier from one tokenizer position."""

    value: list[str] = []
    index = start
    while index < len(text):
        character = text[index]
        if character == "\\":
            escaped = css_escape_value(text, index)
            if escaped is None or not escaped[0]:
                return None
            decoded, index = escaped
            value.append(decoded)
            continue
        if not css_name_character(character):
            break
        value.append(character)
        index += 1
    return ("".join(value), index) if value else None


def css_image_set_string_targets(text: str, start: int) -> list[str]:
    """Extract top-level string candidates from one image-set function."""

    targets: list[str] = []
    index = start
    depth = 1
    candidate_start = True
    while index < len(text) and depth:
        if text.startswith("/*", index):
            comment_end = text.find("*/", index + 2)
            index = len(text) if comment_end < 0 else comment_end + 2
            continue
        character = text[index]
        if character in {'"', "'"}:
            string = css_string_value(text, index)
            if string is None:
                index += 1
                continue
            if depth == 1 and candidate_start:
                targets.append(string[0])
            index = string[1]
            if depth == 1:
                candidate_start = False
            continue
        if character == "(":
            if depth == 1:
                candidate_start = False
            depth += 1
        elif character == ")":
            depth -= 1
        elif depth == 1 and character == ",":
            candidate_start = True
        elif depth == 1 and character not in HTML_ASCII_WHITESPACE:
            candidate_start = False
        index += 1
    return targets


def css_url_requires_file(target: str) -> bool:
    """Return whether a CSS URL is not a same-document fragment reference."""

    try:
        parsed = urlsplit(target)
    except ValueError:
        return True
    return bool(
        parsed.scheme
        or parsed.netloc
        or parsed.path
        or parsed.query
        or not parsed.fragment
    )


def css_skip_whitespace_and_comments(text: str, start: int) -> int:
    """Return the next CSS token offset after whitespace and comments."""

    index = start
    while index < len(text):
        while index < len(text) and text[index] in HTML_ASCII_WHITESPACE:
            index += 1
        if not text.startswith("/*", index):
            break
        comment_end = text.find("*/", index + 2)
        if comment_end < 0:
            return len(text)
        index = comment_end + 2
    return index


def css_at_rule_block_start(text: str, start: int) -> int | None:
    """Return a CSS at-rule's top-level opening brace, if present."""

    index = start
    parentheses = 0
    brackets = 0
    while index < len(text):
        if text.startswith("/*", index):
            comment_end = text.find("*/", index + 2)
            if comment_end < 0:
                return None
            index = comment_end + 2
            continue
        if text[index] in {'"', "'"}:
            string = css_string_value(text, index)
            if string is None:
                return None
            index = string[1]
            continue
        if text[index] == "(":
            parentheses += 1
        elif text[index] == ")" and parentheses:
            parentheses -= 1
        elif text[index] == "[":
            brackets += 1
        elif text[index] == "]" and brackets:
            brackets -= 1
        elif not parentheses and not brackets:
            if text[index] == "{":
                return index
            if text[index] == ";":
                return None
        index += 1
    return None


def css_block_end(text: str, start: int) -> int:
    """Return the offset after a balanced CSS block starting after its brace."""

    index = start
    depth = 1
    while index < len(text) and depth:
        if text.startswith("/*", index):
            comment_end = text.find("*/", index + 2)
            index = len(text) if comment_end < 0 else comment_end + 2
            continue
        if text[index] in {'"', "'"}:
            string = css_string_value(text, index)
            index = len(text) if string is None else string[1]
            continue
        if text[index] == "\\":
            escaped = css_escape_value(text, index)
            index = index + 1 if escaped is None else escaped[1]
            continue
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
        index += 1
    return index


def css_rule_boundary(text: str, start: int) -> tuple[str, int]:
    """Return a CSS rule's form and the offset after that complete rule."""

    index = start
    parentheses = 0
    brackets = 0
    while index < len(text):
        if text.startswith("/*", index):
            comment_end = text.find("*/", index + 2)
            index = len(text) if comment_end < 0 else comment_end + 2
            continue
        if text[index] in {'"', "'"}:
            string = css_string_value(text, index)
            index = len(text) if string is None else string[1]
            continue
        if text[index] == "\\":
            escaped = css_escape_value(text, index)
            index = index + 1 if escaped is None else escaped[1]
            continue
        if text[index] == "(":
            parentheses += 1
        elif text[index] == ")" and parentheses:
            parentheses -= 1
        elif text[index] == "[":
            brackets += 1
        elif text[index] == "]" and brackets:
            brackets -= 1
        elif not parentheses and not brackets:
            if text[index] == ";":
                return "statement", index + 1
            if text[index] == "{":
                return "block", css_block_end(text, index + 1)
        index += 1
    return "eof", len(text)


def css_top_level_import_starts(text: str) -> set[int]:
    """Return offsets of imports accepted by top-level stylesheet ordering."""

    starts: set[int] = set()
    imports_allowed = True
    index = 0
    while index < len(text):
        index = css_skip_whitespace_and_comments(text, index)
        if text.startswith("<!--", index):
            index += 4
            continue
        if text.startswith("-->", index):
            index += 3
            continue
        if index >= len(text):
            break
        if text[index] != "@":
            imports_allowed = False
            _, index = css_rule_boundary(text, index)
            continue

        identifier = css_identifier_value(text, index + 1)
        if identifier is None:
            imports_allowed = False
            index += 1
            continue
        rule_form, rule_end = css_rule_boundary(text, identifier[1])
        name = identifier[0].casefold()
        if name == "import" and imports_allowed and rule_form == "statement":
            starts.add(index)
        elif not (
            rule_form == "statement" and name in {"charset", "layer"}
        ):
            imports_allowed = False
        index = rule_end
    return starts


def css_is_declaration_start(text: str, start: int) -> bool:
    """Return whether an identifier begins after a declaration boundary."""

    index = start
    while index:
        index -= 1
        if text[index] in HTML_ASCII_WHITESPACE:
            continue
        if index and text[index - 1 : index + 1] == "*/":
            comment_start = text.rfind("/*", 0, index - 1)
            if comment_start < 0:
                return False
            index = comment_start
            continue
        return text[index] in "{;"
    return True


def css_declaration_value_end(text: str, start: int) -> int:
    """Return the first top-level declaration delimiter after a value start."""

    parentheses = 0
    brackets = 0
    braces = 0
    index = start
    while index < len(text):
        if text.startswith("/*", index):
            comment_end = text.find("*/", index + 2)
            index = len(text) if comment_end < 0 else comment_end + 2
            continue
        if text[index] in {'"', "'"}:
            string = css_string_value(text, index)
            index = len(text) if string is None else string[1]
            continue
        if text[index] == "\\":
            escaped = css_escape_value(text, index)
            index = index + 1 if escaped is None else escaped[1]
            continue
        if text[index] == "(":
            parentheses += 1
        elif text[index] == ")" and parentheses:
            parentheses -= 1
        elif text[index] == "[":
            brackets += 1
        elif text[index] == "]" and brackets:
            brackets -= 1
        elif text[index] == "{":
            braces += 1
        elif text[index] == "}":
            if braces:
                braces -= 1
            elif not parentheses and not brackets:
                return index
        elif (
            text[index] == ";"
            and not parentheses
            and not brackets
            and not braces
        ):
            return index
        index += 1
    return len(text)


def css_custom_property_declarations(text: str) -> list[tuple[str, int, int]]:
    """Return custom-property names and their value ranges."""

    declarations: list[tuple[str, int, int]] = []
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
        if not text.startswith("--", index) or not css_is_declaration_start(
            text, index
        ):
            index += 1
            continue
        identifier = css_identifier_value(text, index)
        if identifier is None or not identifier[0].startswith("--"):
            index += 2
            continue
        colon = css_skip_whitespace_and_comments(text, identifier[1])
        if colon >= len(text) or text[colon] != ":":
            index = identifier[1]
            continue
        value_start = colon + 1
        value_end = css_declaration_value_end(text, value_start)
        declarations.append((identifier[0], value_start, value_end))
        index = value_end + (value_end < len(text))
    return declarations


def css_variable_references(text: str) -> list[tuple[str, int]]:
    """Return decoded custom-property names referenced by var() functions."""

    references: list[tuple[str, int]] = []
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
        previous = text[index - 1] if index else ""
        identifier = (
            css_identifier_value(text, index)
            if (css_name_character(text[index]) or text[index] == "\\")
            and not css_name_character(previous)
            else None
        )
        if identifier is None:
            index += 1
            continue
        if (
            identifier[0].casefold() == "var"
            and identifier[1] < len(text)
            and text[identifier[1]] == "("
        ):
            name_start = css_skip_whitespace_and_comments(
                text, identifier[1] + 1
            )
            name = css_identifier_value(text, name_start)
            if name is not None and name[0].startswith("--"):
                references.append((name[0], index))
        index = max(index + 1, identifier[1])
    return references


def css_used_custom_properties(
    texts: list[str],
    initially_used: set[str] | frozenset[str] = frozenset(),
) -> set[str]:
    """Return custom properties consumed by resource-bearing declarations."""

    dependencies: dict[str, set[str]] = {}
    used = set(initially_used)
    for text in texts:
        declarations = css_custom_property_declarations(text)
        starts = [start for _, start, _ in declarations]
        resource_ranges = css_direct_resource_declaration_value_ranges(text)
        resource_starts = [start for start, _ in resource_ranges]
        for name, position in css_variable_references(text):
            declaration_index = bisect_right(starts, position) - 1
            if (
                declaration_index >= 0
                and position < declarations[declaration_index][2]
            ):
                owner = declarations[declaration_index][0]
                dependencies.setdefault(owner, set()).add(name)
            else:
                resource_index = bisect_right(resource_starts, position) - 1
                if (
                    resource_index >= 0
                    and position < resource_ranges[resource_index][1]
                ):
                    used.add(name)
    pending = list(used)
    while pending:
        name = pending.pop()
        for dependency in dependencies.get(name, set()):
            if dependency not in used:
                used.add(dependency)
                pending.append(dependency)
    return used


def css_unused_custom_property_value_ranges(
    text: str,
    used_custom_properties: set[str] | frozenset[str] = frozenset(),
) -> list[tuple[int, int]]:
    """Return value ranges for custom properties never referenced by live CSS."""

    declarations = css_custom_property_declarations(text)
    if not declarations:
        return []
    used = css_used_custom_properties([text], used_custom_properties)
    return [
        (start, end)
        for name, start, end in declarations
        if name not in used
    ]


def css_declaration_value_ranges(text: str) -> list[tuple[str, int, int]]:
    """Return syntactic declaration names and their value ranges."""

    declarations: list[tuple[str, int, int]] = []
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
        previous = text[index - 1] if index else ""
        if (
            not (css_name_character(text[index]) or text[index] == "\\")
            or css_name_character(previous)
            or not css_is_declaration_start(text, index)
        ):
            index += 1
            continue
        identifier = css_identifier_value(text, index)
        if identifier is None:
            index += 1
            continue
        colon = css_skip_whitespace_and_comments(text, identifier[1])
        if colon >= len(text) or text[colon] != ":":
            index = identifier[1]
            continue
        value_start = colon + 1
        value_end = css_declaration_value_end(text, value_start)
        if (
            css_at_rule_block_start(text[value_start:value_end], 0)
            is not None
        ):
            # A top-level block after the colon belongs to a nested selector,
            # not a property declaration such as ``background:hover {...}``.
            index = identifier[1]
            continue
        declarations.append((identifier[0], value_start, value_end))
        index = value_end + (value_end < len(text))
    return declarations


def css_enclosing_at_rule(text: str, position: int) -> str | None:
    """Return the innermost at-rule whose block contains one position."""

    contexts: list[str | None] = []
    statement_starts = [0]
    parentheses = 0
    brackets = 0
    index = 0
    while index < min(position, len(text)):
        if text.startswith("/*", index):
            comment_end = text.find("*/", index + 2)
            index = len(text) if comment_end < 0 else comment_end + 2
            continue
        if text[index] in {'"', "'"}:
            string = css_string_value(text, index)
            index = len(text) if string is None else string[1]
            continue
        if text[index] == "\\":
            escaped = css_escape_value(text, index)
            index = index + 1 if escaped is None else escaped[1]
            continue
        if text[index] == "(":
            parentheses += 1
        elif text[index] == ")" and parentheses:
            parentheses -= 1
        elif text[index] == "[":
            brackets += 1
        elif text[index] == "]" and brackets:
            brackets -= 1
        elif not parentheses and not brackets:
            if text[index] == "{":
                header_start = css_skip_whitespace_and_comments(
                    text, statement_starts[-1]
                )
                at_rule: str | None = None
                if header_start < index and text[header_start] == "@":
                    identifier = css_identifier_value(text, header_start + 1)
                    if identifier is not None:
                        at_rule = identifier[0].casefold()
                contexts.append(at_rule)
                statement_starts.append(index + 1)
            elif text[index] == ";":
                statement_starts[-1] = index + 1
            elif text[index] == "}" and contexts:
                contexts.pop()
                statement_starts.pop()
                statement_starts[-1] = index + 1
        index += 1
    return contexts[-1] if contexts else None


def css_direct_resource_declaration_value_ranges(
    text: str,
) -> list[tuple[int, int]]:
    """Return direct property or descriptor ranges that can consume URLs."""

    ranges: list[tuple[int, int]] = []
    for name, start, end in css_declaration_value_ranges(text):
        canonical_name = name.casefold()
        descriptor_rules = CSS_RESOURCE_DESCRIPTORS.get(canonical_name)
        if canonical_name in CSS_RESOURCE_PROPERTIES or (
            descriptor_rules is not None
            and css_enclosing_at_rule(text, start) in descriptor_rules
        ):
            ranges.append((start, end))
    return ranges


def css_resource_declaration_value_ranges(
    text: str,
    used_custom_properties: set[str] | frozenset[str] = frozenset(),
) -> list[tuple[int, int]]:
    """Return declaration ranges whose values may consume URL resources."""

    used_custom = css_used_custom_properties([text], used_custom_properties)
    ranges = css_direct_resource_declaration_value_ranges(text)
    for name, start, end in css_declaration_value_ranges(text):
        if name.startswith("--") and name in used_custom:
            ranges.append((start, end))
    return sorted(ranges)


def css_resource_references(
    text: str,
    *,
    used_custom_properties: set[str] | frozenset[str] = frozenset(),
    imported_targets: list[str] | None = None,
) -> list[tuple[str, bool]]:
    """Extract CSS resource URLs and whether each requires a file path."""

    targets: list[tuple[str, bool]] = []
    forced_file_url_starts: set[int] = set()
    ignored_url_starts: set[int] = set()
    ignored_supports_condition_end = -1
    valid_import_starts = css_top_level_import_starts(text)
    unused_custom_property_ranges = css_unused_custom_property_value_ranges(
        text, used_custom_properties
    )
    unused_custom_property_starts = [
        start for start, _ in unused_custom_property_ranges
    ]
    resource_declaration_ranges = css_resource_declaration_value_ranges(
        text, used_custom_properties
    )
    resource_declaration_starts = [
        start for start, _ in resource_declaration_ranges
    ]

    def inside_unused_custom_property(position: int) -> bool:
        range_index = bisect_right(unused_custom_property_starts, position) - 1
        return (
            range_index >= 0
            and position < unused_custom_property_ranges[range_index][1]
        )

    def inside_resource_declaration(position: int) -> bool:
        range_index = bisect_right(resource_declaration_starts, position) - 1
        return (
            range_index >= 0
            and position < resource_declaration_ranges[range_index][1]
        )

    index = 0
    while index < len(text):
        if text.startswith("/*", index):
            comment_end = text.find("*/", index + 2)
            index = len(text) if comment_end < 0 else comment_end + 2
            continue

        previous = text[index - 1] if index else ""
        function_identifier = (
            css_identifier_value(text, index)
            if (css_name_character(text[index]) or text[index] == "\\")
            and not css_name_character(previous)
            else None
        )
        if (
            function_identifier is not None
            and function_identifier[0].casefold()
            in {"image-set", "-webkit-image-set"}
            and function_identifier[1] < len(text)
            and text[function_identifier[1]] == "("
            and not css_name_character(previous)
            and index >= ignored_supports_condition_end
            and not inside_unused_custom_property(index)
            and inside_resource_declaration(index)
        ):
            targets.extend(
                (target, True)
                for target in css_image_set_string_targets(
                    text, function_identifier[1] + 1
                )
            )
        if text[index] in {'"', "'"}:
            string = css_string_value(text, index)
            index = len(text) if string is None else string[1]
            continue

        at_rule_identifier = (
            css_identifier_value(text, index + 1)
            if text[index] == "@"
            else None
        )
        if (
            at_rule_identifier is not None
            and at_rule_identifier[0].casefold() == "import"
        ):
            if index not in valid_import_starts:
                _, index = css_rule_boundary(text, at_rule_identifier[1])
                continue
            value_start = css_skip_whitespace_and_comments(
                text, at_rule_identifier[1]
            )
            if value_start < len(text) and text[value_start] in {'"', "'"}:
                string = css_string_value(text, value_start)
                if string is not None:
                    targets.append((string[0], True))
                    if imported_targets is not None:
                        imported_targets.append(string[0])
                    index = string[1]
                    continue
            import_url_identifier = (
                css_identifier_value(text, value_start)
                if value_start < len(text)
                else None
            )
            if (
                import_url_identifier is not None
                and import_url_identifier[0].casefold() == "url"
                and import_url_identifier[1] < len(text)
                and text[import_url_identifier[1]] == "("
            ):
                forced_file_url_starts.add(value_start)
        if (
            at_rule_identifier is not None
            and at_rule_identifier[0].casefold() == "namespace"
        ):
            value_start = css_skip_whitespace_and_comments(
                text, at_rule_identifier[1]
            )
            namespace_value_identifier = (
                css_identifier_value(text, value_start)
                if value_start < len(text)
                else None
            )
            if (
                namespace_value_identifier is not None
                and namespace_value_identifier[0].casefold() != "url"
            ):
                value_start = css_skip_whitespace_and_comments(
                    text, namespace_value_identifier[1]
                )
                namespace_value_identifier = (
                    css_identifier_value(text, value_start)
                    if value_start < len(text)
                    else None
                )
            if (
                namespace_value_identifier is not None
                and namespace_value_identifier[0].casefold() == "url"
                and namespace_value_identifier[1] < len(text)
                and text[namespace_value_identifier[1]] == "("
            ):
                ignored_url_starts.add(value_start)
        if (
            at_rule_identifier is not None
            and at_rule_identifier[0].casefold() == "supports"
        ):
            block_start = css_at_rule_block_start(text, at_rule_identifier[1])
            if block_start is not None:
                ignored_supports_condition_end = max(
                    ignored_supports_condition_end, block_start
                )

        url_identifier = function_identifier
        if (
            url_identifier is not None
            and url_identifier[0].casefold() == "url"
            and url_identifier[1] < len(text)
            and text[url_identifier[1]] == "("
            and not css_name_character(previous)
        ):
            value_start = url_identifier[1] + 1
            value_start = css_skip_whitespace_and_comments(text, value_start)
            if value_start < len(text) and text[value_start] in {'"', "'"}:
                string = css_string_value(text, value_start)
                if string is not None:
                    value, value_end = string
                    value_end = css_skip_whitespace_and_comments(
                        text, value_end
                    )
                    if value_end < len(text) and text[value_end] == ")":
                        if (
                            index not in ignored_url_starts
                            and index >= ignored_supports_condition_end
                            and not inside_unused_custom_property(index)
                            and (
                                index in forced_file_url_starts
                                or inside_resource_declaration(index)
                            )
                        ):
                            if (
                                imported_targets is not None
                                and index in forced_file_url_starts
                            ):
                                imported_targets.append(value)
                            targets.append(
                                (
                                    value,
                                    index in forced_file_url_starts
                                    or css_url_requires_file(value),
                                )
                            )
                        index = value_end + 1
                        continue
            else:
                value_end = value_start
                value_parts: list[str] = []
                value_part_start = value_start
                has_internal_whitespace = False
                while value_end < len(text) and text[value_end] != ")":
                    if text.startswith("/*", value_end):
                        value_parts.append(text[value_part_start:value_end])
                        comment_end = text.find("*/", value_end + 2)
                        if comment_end < 0:
                            value_end = len(text)
                            break
                        value_end = comment_end + 2
                        value_part_start = value_end
                        continue
                    if text[value_end] in {'"', "'", "("}:
                        break
                    if text[value_end] == "\\" and value_end + 1 < len(text):
                        escape = css_escape_value(text, value_end)
                        if escape is None:
                            break
                        _, value_end = escape
                        continue
                    if text[value_end] in HTML_ASCII_WHITESPACE:
                        value_parts.append(text[value_part_start:value_end])
                        whitespace_end = css_skip_whitespace_and_comments(
                            text, value_end
                        )
                        if whitespace_end >= len(text) or text[whitespace_end] != ")":
                            has_internal_whitespace = True
                        value_end = whitespace_end
                        value_part_start = value_end
                        continue
                    value_end += 1
                if value_end < len(text) and text[value_end] == ")":
                    value_parts.append(text[value_part_start:value_end])
                    value = "".join(value_parts).rstrip(" \t\r\n\f")
                    decoded = css_unescape(value)
                    if (
                        decoded
                        and not has_internal_whitespace
                        and index not in ignored_url_starts
                        and index >= ignored_supports_condition_end
                        and not inside_unused_custom_property(index)
                        and (
                            index in forced_file_url_starts
                            or inside_resource_declaration(index)
                        )
                    ):
                        if (
                            imported_targets is not None
                            and index in forced_file_url_starts
                        ):
                            imported_targets.append(decoded)
                        targets.append(
                            (
                                decoded,
                                index in forced_file_url_starts
                                or css_url_requires_file(decoded),
                            )
                        )
                    index = value_end + 1
                    continue
        if function_identifier is not None:
            index = function_identifier[1]
            continue
        index += 1
    return targets


def css_resource_targets(text: str) -> list[str]:
    """Extract resource URLs from CSS for compatibility callers."""

    return [target for target, _ in css_resource_references(text)]


def svg_presentation_resource_targets(
    attributes: dict[str, str],
) -> list[tuple[str, bool, bool]]:
    """Return URLs loaded by SVG presentation attributes."""

    targets: list[tuple[str, bool, bool]] = []
    for name in SVG_PRESENTATION_RESOURCE_ATTRIBUTES:
        if name not in attributes:
            continue
        targets.extend(
            (target, False, requires_file)
            for target, requires_file in css_resource_references(
                f"{name}:{attributes[name]};"
            )
        )
    return targets


def html_target_requires_file(target: str) -> bool:
    """Return whether an HTML resource URL identifies an external file path."""

    try:
        return bool(urlsplit(target).path)
    except ValueError:
        return True


def html_meta_refresh_target(content: str) -> str | None:
    """Extract the navigation URL from a valid-enough meta refresh value."""

    match = re.match(
        r"^[\t\n\f\r ]*[0-9]+(?:\.[0-9]+)?[\t\n\f\r ]*[;,]",
        content,
    )
    if match is None:
        return None
    target = content[match.end() :].lstrip("\t\n\f\r ")
    url_prefix = re.match(r"url(?=[\t\n\f\r =]|$)", target, re.IGNORECASE)
    if url_prefix is not None:
        target = target[url_prefix.end() :].lstrip("\t\n\f\r ")
        if target.startswith("="):
            target = target[1:].lstrip("\t\n\f\r ")
    target = target.strip("\t\n\f\r ")
    if target.startswith(('"', "'")):
        quote_character = target[0]
        closing_quote = target.find(quote_character, 1)
        target = (
            target[1:closing_quote]
            if closing_quote >= 0
            else target[1:]
        )
    return target or None


def html_slash_closes_context(tag: str, *, inside_foreign: bool) -> bool:
    """Return whether HTML parsing honors a start tag's self-closing flag."""

    return inside_foreign or tag in {"math", "svg"} or tag in HTML_VOID_TAGS


def html_element_is_integration_point(
    tag: str, namespace: str, attributes: dict[str, str]
) -> bool:
    """Return whether foreign content re-enters HTML below this element."""

    return (
        namespace == SVG_NAMESPACE and tag in SVG_HTML_INTEGRATION_POINTS
    ) or (
        namespace == MATHML_NAMESPACE
        and (
            tag in MATHML_TEXT_INTEGRATION_POINTS
            or (
                tag == "annotation-xml"
                and attributes.get("encoding", "").strip().casefold()
                in {"application/xhtml+xml", "text/html"}
            )
        )
    )


def html_start_tag_breaks_out_of_foreign_content(
    tag: str, attributes: dict[str, str]
) -> bool:
    """Return whether an HTML start tag exits the current foreign subtree."""

    return tag in HTML_FOREIGN_CONTENT_BREAKOUT_START_TAGS or (
        tag == "font"
        and any(name in attributes for name in {"color", "face", "size"})
    )


def html_start_tag_namespace(
    element_stack: list[tuple[str, str, dict[str, str]]],
    tag: str,
    attributes: dict[str, str],
) -> str:
    """Return the namespace assigned by the HTML tree builder to a start tag."""

    if (
        element_stack
        and element_stack[-1][1] != HTML_NAMESPACE
        and not html_element_is_integration_point(*element_stack[-1])
        and html_start_tag_breaks_out_of_foreign_content(tag, attributes)
    ):
        while (
            element_stack
            and element_stack[-1][1] != HTML_NAMESPACE
            and not html_element_is_integration_point(*element_stack[-1])
        ):
            element_stack.pop()

    if not element_stack:
        parent_namespace = HTML_NAMESPACE
        parent_tag = ""
        parent_attributes: dict[str, str] = {}
    else:
        parent_tag, parent_namespace, parent_attributes = element_stack[-1]

    enters_html = html_element_is_integration_point(
        parent_tag, parent_namespace, parent_attributes
    ) and not (
        parent_namespace == MATHML_NAMESPACE
        and parent_tag in MATHML_TEXT_INTEGRATION_POINTS
        and tag in {"malignmark", "mglyph"}
    )
    if parent_namespace == HTML_NAMESPACE or enters_html:
        if tag == "svg":
            return SVG_NAMESPACE
        if tag == "math":
            return MATHML_NAMESPACE
        return HTML_NAMESPACE
    if parent_namespace == MATHML_NAMESPACE and tag == "svg":
        return SVG_NAMESPACE
    return parent_namespace


def html_canonical_tag_name(tag: str, namespace: str) -> str:
    """Apply HTML tree-builder tag aliases used by resource semantics."""

    if namespace == HTML_NAMESPACE and tag == "image":
        return "img"
    return tag


def html_push_element_context(
    element_stack: list[tuple[str, str, dict[str, str]]],
    tag: str,
    namespace: str,
    attributes: dict[str, str],
) -> None:
    """Push a non-void element onto a lightweight namespace stack."""

    canonical_tag = html_canonical_tag_name(tag, namespace)
    if namespace == HTML_NAMESPACE and canonical_tag in HTML_VOID_TAGS:
        return
    element_stack.append((tag, namespace, attributes))


def html_pop_element_context(
    element_stack: list[tuple[str, str, dict[str, str]]], tag: str
) -> None:
    """Pop through the most recent matching element context."""

    for index in range(len(element_stack) - 1, -1, -1):
        if element_stack[index][0] == tag:
            del element_stack[index:]
            return


def html_has_ancestor(
    element_stack: list[tuple[str, str, dict[str, str]]],
    tags: frozenset[str],
) -> bool:
    """Return whether an HTML-namespace ancestor has one of the given tags."""

    return any(
        namespace == HTML_NAMESPACE and tag in tags
        for tag, namespace, _ in element_stack
    )


def html_has_direct_parent(
    element_stack: list[tuple[str, str, dict[str, str]]],
    tags: frozenset[str],
) -> bool:
    """Return whether the direct parent is an HTML element with a given tag."""

    return bool(
        element_stack
        and element_stack[-1][1] == HTML_NAMESPACE
        and element_stack[-1][0] in tags
    )


def html_template_establishes_declarative_shadow_root(
    element_stack: list[tuple[str, str, dict[str, str]]],
    namespace: str,
    attributes: dict[str, str],
) -> bool:
    """Return whether a template has an eligible declarative shadow host."""

    if (
        namespace != HTML_NAMESPACE
        or attributes.get("shadowrootmode", "").casefold()
        not in HTML_DECLARATIVE_SHADOW_ROOT_MODES
        or not element_stack
    ):
        return False
    parent_tag, parent_namespace, _ = element_stack[-1]
    return (
        parent_namespace == HTML_NAMESPACE
        and parent_tag not in HTML_VOID_TAGS
        and parent_tag not in {"body", "head", "html", "slot", "template"}
    )


HTML_START_TAG_ATTRIBUTE = re.compile(
    rf"(?P<name>{MARKDOWN_HTML_ATTRIBUTE_NAME})"
    rf"(?:[ \t\f\r\n]*=[ \t\f\r\n]*"
    rf"(?P<value>{MARKDOWN_HTML_ATTRIBUTE_VALUE}))?"
)


def html_raw_start_tag_attributes(raw_tag: str) -> dict[str, str]:
    """Parse raw HTML attributes with deterministic tokenizer unescaping."""

    tag_name = re.match(r"<[A-Za-z][A-Za-z0-9-]*", raw_tag)
    if tag_name is None:
        return {}
    values: dict[str, str] = {}
    cursor = tag_name.end()
    while cursor < len(raw_tag):
        whitespace = re.match(r"[\t\n\f\r ]+", raw_tag[cursor:])
        if whitespace is None:
            break
        cursor += whitespace.end()
        if raw_tag.startswith((">", "/>"), cursor):
            break
        attribute = HTML_START_TAG_ATTRIBUTE.match(raw_tag, cursor)
        if attribute is None:
            break
        raw_value = attribute.group("value") or ""
        if (
            len(raw_value) >= 2
            and raw_value[0] in {'"', "'"}
            and raw_value[-1] == raw_value[0]
        ):
            raw_value = raw_value[1:-1]
        values.setdefault(
            attribute.group("name").casefold(),
            html_attribute_unescape(raw_value),
        )
        cursor = attribute.end()
    return values


def html_formaction_value(
    tag: str, namespace: str, attributes: dict[str, str]
) -> str | None:
    """Return a submit control's formaction value, if it can override one."""

    if namespace != HTML_NAMESPACE or "formaction" not in attributes:
        return None
    if (
        tag in MARKDOWN_HTML_BUTTON_TAGS
        and attributes.get("type", "").casefold()
        not in MARKDOWN_HTML_NON_SUBMIT_BUTTON_TYPES
    ):
        return attributes["formaction"]
    if (
        tag in MARKDOWN_HTML_INPUT_TAGS
        and attributes.get("type", "").casefold()
        in MARKDOWN_HTML_SUBMIT_INPUT_TYPES
    ):
        return attributes["formaction"]
    return None


def html_link_href_should_validate(relations: frozenset[str]) -> bool:
    """Return whether a link href addresses a path the browser may request."""

    return bool(
        relations.intersection(MARKDOWN_HTML_LINK_RESOURCE_RELATIONS)
    ) or not relations.intersection(MARKDOWN_HTML_LINK_ORIGIN_HINT_RELATIONS)


def html_owned_formaction_targets(
    candidates: list[tuple[str, str | None, bool]],
    first_id_elements: dict[str, tuple[str, str]],
) -> list[tuple[str, bool, bool]]:
    """Return formaction targets whose controls have an effective form owner."""

    return [
        (target, False, False)
        for target, explicit_form_id, inside_form in candidates
        if (
            inside_form
            if explicit_form_id is None
            else first_id_elements.get(explicit_form_id)
            == ("form", HTML_NAMESPACE)
        )
    ]


class HTMLContextResourceParser(HTMLParser):
    """Collect resources whose HTML meaning depends on ancestor context."""

    CDATA_CONTENT_ELEMENTS = tuple(HTML_SCRIPTING_ENABLED_RAW_TEXT_TAGS)

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.targets: list[tuple[str, bool, bool]] = []
        self.embedded_document_targets: list[str] = []
        self.stylesheet_targets: list[str] = []
        self.module_script_targets: list[str] = []
        self.module_script_content: list[str] | None = None
        self.base_hrefs: list[str] = []
        self.formaction_candidates: list[tuple[str, str | None, bool]] = []
        self.first_id_elements: dict[str, tuple[str, str]] = {}
        self.form_active = False
        self.template_depth = 0
        self.in_select = False
        self.frameset_depth = 0
        self.after_frameset = False
        self.element_stack: list[tuple[str, str, dict[str, str]]] = []

    def handle_starttag(
        self, tag: str, attributes: list[tuple[str, str | None]]
    ) -> None:
        tag = tag.casefold()
        if self.template_depth:
            if tag == "template":
                self.template_depth += 1
            return
        raw_tag = self.get_starttag_text()
        if raw_tag is not None and MARKDOWN_HTML_TAG.fullmatch(raw_tag) is None:
            return
        if self.in_select:
            if tag in HTML_SELECT_BREAKOUT_START_TAGS:
                self.in_select = False
            elif tag == "select":
                self.in_select = False
                return
            elif tag not in HTML_SELECT_ALLOWED_START_TAGS:
                return

        values = html_raw_start_tag_attributes(raw_tag or "")

        namespace = html_start_tag_namespace(self.element_stack, tag, values)
        canonical_tag = html_canonical_tag_name(tag, namespace)
        if namespace == HTML_NAMESPACE and (
            (self.frameset_depth and canonical_tag not in HTML_FRAMESET_ALLOWED_START_TAGS)
            or (
                self.after_frameset
                and canonical_tag not in {"html", "noframes"}
            )
        ):
            return
        if (
            tag == "template"
            and namespace == HTML_NAMESPACE
            and not html_template_establishes_declarative_shadow_root(
                self.element_stack, namespace, values
            )
        ):
            self.template_depth = 1
            return
        if canonical_tag in MARKDOWN_HTML_FORM_TAGS and namespace == HTML_NAMESPACE:
            if self.form_active:
                return
            self.form_active = True
            if "action" in values:
                self.targets.append((values["action"], False, False))
        if "id" in values:
            self.first_id_elements.setdefault(
                values["id"], (canonical_tag, namespace)
            )
        formaction = html_formaction_value(canonical_tag, namespace, values)
        if formaction is not None:
            self.formaction_candidates.append(
                (
                    formaction,
                    values.get("form") if "form" in values else None,
                    self.form_active,
                )
            )
        picture_parent = html_has_direct_parent(
            self.element_stack, frozenset({"picture"})
        )
        media_parent = html_has_direct_parent(
            self.element_stack, frozenset({"audio", "video"})
        )
        if tag == "base" and "href" in values and namespace == HTML_NAMESPACE:
            self.base_hrefs.append(values["href"])
        if (
            canonical_tag == "a"
            and namespace == HTML_NAMESPACE
            and "href" in values
        ):
            self.targets.append((values["href"], False, False))
        if (
            canonical_tag == "area"
            and namespace == HTML_NAMESPACE
            and "href" in values
            and html_has_ancestor(self.element_stack, MARKDOWN_HTML_MAP_TAGS)
        ):
            self.targets.append((values["href"], False, False))
        if (
            canonical_tag in MARKDOWN_HTML_LINK_TAGS
            and namespace == HTML_NAMESPACE
        ):
            relations = frozenset(
                re.findall(
                    r"[^\t\n\f\r ]+", values.get("rel", "").casefold()
                )
            )
            if "href" in values:
                is_resource = bool(
                    relations.intersection(MARKDOWN_HTML_LINK_RESOURCE_RELATIONS)
                )
                if html_link_href_should_validate(relations):
                    self.targets.append((values["href"], False, is_resource))
                if "stylesheet" in relations:
                    self.stylesheet_targets.append(values["href"])
            if (
                "preload" in relations
                and values.get("as", "").casefold()
                in MARKDOWN_HTML_IMAGE_PRELOAD_AS_VALUES
                and "imagesrcset" in values
            ):
                self.targets.extend(
                    (candidate, False, True)
                    for candidate in html_srcset_candidates(
                        values["imagesrcset"]
                    )
                )
        if (
            canonical_tag in MARKDOWN_HTML_SRC_TAGS
            and namespace == HTML_NAMESPACE
            and "src" in values
            and not (canonical_tag == "iframe" and "srcdoc" in values)
            and not (
                canonical_tag == "img"
                and "srcset" in values
                and html_srcset_overrides_src(values["srcset"])
            )
            and not (
                canonical_tag == "script"
                and not html_script_attributes_use_src(values)
            )
        ):
            self.targets.append((values["src"], False, True))
            if canonical_tag in MARKDOWN_HTML_EMBEDDED_DOCUMENT_SRC_TAGS:
                self.embedded_document_targets.append(values["src"])
            if canonical_tag == "script" and html_script_is_module(values):
                self.module_script_targets.append(values["src"])
        if (
            canonical_tag == "script"
            and namespace == HTML_NAMESPACE
            and "src" not in values
            and html_script_is_module(values)
        ):
            self.module_script_content = []
        if (
            canonical_tag in MARKDOWN_HTML_INPUT_TAGS
            and namespace == HTML_NAMESPACE
            and values.get("type", "").casefold()
            in MARKDOWN_HTML_IMAGE_INPUT_TYPES
            and "src" in values
        ):
            self.targets.append((values["src"], False, True))
        if (
            canonical_tag == "source"
            and namespace == HTML_NAMESPACE
            and "src" in values
            and media_parent
        ):
            self.targets.append((values["src"], False, True))
        if (
            canonical_tag == "source"
            and namespace == HTML_NAMESPACE
            and "srcset" in values
            and picture_parent
        ):
            self.targets.extend(
                (candidate, False, True)
                for candidate in html_srcset_candidates(values["srcset"])
            )
        if (
            canonical_tag in MARKDOWN_HTML_DATA_TAGS
            and namespace == HTML_NAMESPACE
            and "data" in values
        ):
            self.targets.append((values["data"], False, True))
            if canonical_tag in MARKDOWN_HTML_EMBEDDED_DOCUMENT_DATA_TAGS:
                self.embedded_document_targets.append(values["data"])
        if (
            canonical_tag in MARKDOWN_HTML_POSTER_TAGS
            and namespace == HTML_NAMESPACE
            and "poster" in values
        ):
            self.targets.append((values["poster"], False, True))
        if (
            canonical_tag in MARKDOWN_HTML_BACKGROUND_TAGS
            and namespace == HTML_NAMESPACE
            and values.get("background", "")
        ):
            self.targets.append((values["background"], False, True))
        if namespace == SVG_NAMESPACE and tag in MARKDOWN_SVG_RESOURCE_HREF_TAGS:
            target = values.get("href", values.get("xlink:href"))
            if target is not None:
                self.targets.append(
                    (target, False, html_target_requires_file(target))
                )
        if namespace == SVG_NAMESPACE and tag in MARKDOWN_SVG_NAVIGATION_HREF_TAGS:
            target = values.get("href", values.get("xlink:href"))
            if target is not None:
                self.targets.append((target, False, False))
        if namespace == SVG_NAMESPACE:
            self.targets.extend(svg_presentation_resource_targets(values))
        if tag == "select" and namespace == HTML_NAMESPACE:
            self.in_select = True
        html_push_element_context(self.element_stack, tag, namespace, values)
        if canonical_tag == "frameset" and namespace == HTML_NAMESPACE:
            self.frameset_depth += 1

    def handle_startendtag(
        self, tag: str, attributes: list[tuple[str, str | None]]
    ) -> None:
        tag = tag.casefold()
        values = html_raw_start_tag_attributes(self.get_starttag_text() or "")
        namespace = html_start_tag_namespace(self.element_stack, tag, values)
        self.handle_starttag(tag, attributes)
        if html_slash_closes_context(
            html_canonical_tag_name(tag, namespace),
            inside_foreign=namespace != HTML_NAMESPACE,
        ):
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag == "template" and self.template_depth:
            self.template_depth -= 1
            return
        if self.template_depth:
            return
        if tag == "form":
            if not self.form_active:
                return
            self.form_active = False
        if tag == "script" and self.module_script_content is not None:
            self.finish_module_script_content()
        if tag == "frameset" and self.frameset_depth:
            self.frameset_depth -= 1
            if not self.frameset_depth:
                self.after_frameset = True
        html_pop_element_context(self.element_stack, tag)
        self.in_select = html_has_ancestor(
            self.element_stack, frozenset({"select"})
        )

    def handle_data(self, data: str) -> None:
        if self.module_script_content is not None:
            self.module_script_content.append(data)

    def finish_module_script_content(self) -> None:
        """Collect static imports from the current inline module body."""

        if self.module_script_content is None:
            return
        for target in javascript_static_module_specifiers(
            "".join(self.module_script_content)
        ):
            self.targets.append((target, False, True))
            self.module_script_targets.append(target)
        self.module_script_content = None


def html_context_resource_targets(
    text: str,
    *,
    embedded_document_targets: list[str] | None = None,
    stylesheet_targets: list[str] | None = None,
    module_script_targets: list[str] | None = None,
) -> list[tuple[str, bool, bool]]:
    """Return resource targets that require HTML ancestor context."""

    parser = HTMLContextResourceParser()
    parser.feed(text)
    parser.close()
    parser.finish_module_script_content()
    if embedded_document_targets is not None:
        embedded_document_targets.extend(parser.embedded_document_targets)
    if stylesheet_targets is not None:
        stylesheet_targets.extend(parser.stylesheet_targets)
    if module_script_targets is not None:
        module_script_targets.extend(parser.module_script_targets)
    return parser.targets + html_owned_formaction_targets(
        parser.formaction_candidates, parser.first_id_elements
    )


def html_context_base_hrefs(text: str) -> list[str]:
    """Return HTML-namespace base href values in document order."""

    parser = HTMLContextResourceParser()
    parser.feed(text)
    parser.close()
    return parser.base_hrefs


class HTMLFragmentResourceParser(HTMLParser):
    """Collect browser-loaded targets from an iframe srcdoc HTML fragment."""

    CDATA_CONTENT_ELEMENTS = tuple(HTML_SCRIPTING_ENABLED_RAW_TEXT_TAGS)

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.targets: list[tuple[str, bool, bool]] = []
        self.embedded_document_targets: list[str] = []
        self.srcdocs: list[str] = []
        self.base_href: str | None = None
        self.style_content: list[str] | None = None
        self.style_sources: list[str] = []
        self.used_custom_properties: set[str] = set()
        self.stylesheet_targets: list[str] = []
        self.module_script_targets: list[str] = []
        self.module_script_content: list[str] | None = None
        self.formaction_candidates: list[tuple[str, str | None, bool]] = []
        self.first_id_elements: dict[str, tuple[str, str]] = {}
        self.form_active = False
        self.template_depth = 0
        self.in_select = False
        self.frameset_depth = 0
        self.after_frameset = False
        self.element_stack: list[tuple[str, str, dict[str, str]]] = []

    def handle_starttag(
        self, tag: str, attributes: list[tuple[str, str | None]]
    ) -> None:
        tag = tag.casefold()
        raw_tag = self.get_starttag_text()
        values = (
            html_raw_start_tag_attributes(raw_tag)
            if raw_tag is not None
            else {
                name.casefold(): value or ""
                for name, value in attributes
            }
        )

        if self.template_depth:
            if tag == "template":
                self.template_depth += 1
            return
        if self.in_select:
            if tag in HTML_SELECT_BREAKOUT_START_TAGS:
                self.in_select = False
            elif tag == "select":
                self.in_select = False
                return
            elif tag not in HTML_SELECT_ALLOWED_START_TAGS:
                return
        namespace = html_start_tag_namespace(self.element_stack, tag, values)
        canonical_tag = html_canonical_tag_name(tag, namespace)
        if namespace == HTML_NAMESPACE and (
            (self.frameset_depth and canonical_tag not in HTML_FRAMESET_ALLOWED_START_TAGS)
            or (
                self.after_frameset
                and canonical_tag not in {"html", "noframes"}
            )
        ):
            return
        if (
            tag == "template"
            and namespace == HTML_NAMESPACE
            and not html_template_establishes_declarative_shadow_root(
                self.element_stack, namespace, values
            )
        ):
            self.template_depth = 1
            return
        if canonical_tag in MARKDOWN_HTML_FORM_TAGS and namespace == HTML_NAMESPACE:
            if self.form_active:
                return
            self.form_active = True
            if "action" in values:
                self.targets.append((values["action"], False, False))
        if "id" in values:
            self.first_id_elements.setdefault(
                values["id"], (canonical_tag, namespace)
            )
        formaction = html_formaction_value(canonical_tag, namespace, values)
        if formaction is not None:
            self.formaction_candidates.append(
                (
                    formaction,
                    values.get("form") if "form" in values else None,
                    self.form_active,
                )
            )
        picture_parent = html_has_direct_parent(
            self.element_stack, frozenset({"picture"})
        )
        media_parent = html_has_direct_parent(
            self.element_stack, frozenset({"audio", "video"})
        )
        if (
            tag == "base"
            and self.base_href is None
            and "href" in values
            and namespace == HTML_NAMESPACE
        ):
            try:
                urlsplit(values["href"])
            except ValueError:
                pass
            else:
                self.base_href = values["href"]
        if (
            canonical_tag == "a"
            and namespace == HTML_NAMESPACE
            and "href" in values
        ):
            self.targets.append((values["href"], False, False))
        if (
            canonical_tag == "area"
            and namespace == HTML_NAMESPACE
            and "href" in values
            and html_has_ancestor(self.element_stack, MARKDOWN_HTML_MAP_TAGS)
        ):
            self.targets.append((values["href"], False, False))
        if (
            canonical_tag in MARKDOWN_HTML_LINK_TAGS
            and namespace == HTML_NAMESPACE
        ):
            relations = frozenset(
                re.findall(
                    r"[^\t\n\f\r ]+", values.get("rel", "").casefold()
                )
            )
            if "href" in values:
                is_resource = bool(
                    relations.intersection(MARKDOWN_HTML_LINK_RESOURCE_RELATIONS)
                )
                if html_link_href_should_validate(relations):
                    self.targets.append(
                        (values["href"], False, is_resource)
                    )
                if "stylesheet" in relations:
                    self.stylesheet_targets.append(values["href"])
            if (
                "preload" in relations
                and values.get("as", "").casefold()
                in MARKDOWN_HTML_IMAGE_PRELOAD_AS_VALUES
                and "imagesrcset" in values
            ):
                self.targets.extend(
                    (candidate, False, True)
                    for candidate in html_srcset_candidates(
                        values["imagesrcset"]
                    )
                )
        if namespace == SVG_NAMESPACE and tag in MARKDOWN_SVG_RESOURCE_HREF_TAGS:
            target = values.get("href", values.get("xlink:href"))
            if target is not None:
                self.targets.append(
                    (target, False, html_target_requires_file(target))
                )
        if namespace == SVG_NAMESPACE and tag in MARKDOWN_SVG_NAVIGATION_HREF_TAGS:
            target = values.get("href", values.get("xlink:href"))
            if target is not None:
                self.targets.append((target, False, False))
        if (
            canonical_tag in MARKDOWN_HTML_SRC_TAGS
            and namespace == HTML_NAMESPACE
            and "src" in values
            and not (canonical_tag == "iframe" and "srcdoc" in values)
            and not (
                canonical_tag == "img"
                and "srcset" in values
                and html_srcset_overrides_src(values["srcset"])
            )
            and not (
                canonical_tag == "script"
                and not html_script_attributes_use_src(values)
            )
        ):
            self.targets.append((values["src"], False, True))
            if canonical_tag in MARKDOWN_HTML_EMBEDDED_DOCUMENT_SRC_TAGS:
                self.embedded_document_targets.append(values["src"])
            if canonical_tag == "script" and html_script_is_module(values):
                self.module_script_targets.append(values["src"])
        if (
            canonical_tag == "script"
            and namespace == HTML_NAMESPACE
            and "src" not in values
            and html_script_is_module(values)
        ):
            self.module_script_content = []
        if (
            canonical_tag == "source"
            and namespace == HTML_NAMESPACE
            and "src" in values
            and media_parent
        ):
            self.targets.append((values["src"], False, True))
        if (
            canonical_tag in MARKDOWN_HTML_INPUT_TAGS
            and namespace == HTML_NAMESPACE
            and values.get("type", "").casefold() in MARKDOWN_HTML_IMAGE_INPUT_TYPES
            and "src" in values
        ):
            self.targets.append((values["src"], False, True))
        if (
            canonical_tag in MARKDOWN_HTML_DATA_TAGS
            and namespace == HTML_NAMESPACE
            and "data" in values
        ):
            self.targets.append((values["data"], False, True))
            if canonical_tag in MARKDOWN_HTML_EMBEDDED_DOCUMENT_DATA_TAGS:
                self.embedded_document_targets.append(values["data"])
        if (
            canonical_tag in MARKDOWN_HTML_POSTER_TAGS
            and namespace == HTML_NAMESPACE
            and "poster" in values
        ):
            self.targets.append((values["poster"], False, True))
        if (
            canonical_tag in MARKDOWN_HTML_BACKGROUND_TAGS
            and namespace == HTML_NAMESPACE
            and values.get("background", "")
        ):
            self.targets.append((values["background"], False, True))
        if namespace == SVG_NAMESPACE:
            self.targets.extend(svg_presentation_resource_targets(values))
        if (
            canonical_tag in MARKDOWN_HTML_SRCSET_TAGS
            and namespace == HTML_NAMESPACE
            and "srcset" in values
        ):
            self.targets.extend(
                (candidate, False, True)
                for candidate in html_srcset_candidates(values["srcset"])
            )
        if (
            canonical_tag == "source"
            and namespace == HTML_NAMESPACE
            and "srcset" in values
            and picture_parent
        ):
            self.targets.extend(
                (candidate, False, True)
                for candidate in html_srcset_candidates(values["srcset"])
            )
        if (
            canonical_tag in MARKDOWN_HTML_SRCDOC_TAGS
            and namespace == HTML_NAMESPACE
            and "srcdoc" in values
        ):
            self.srcdocs.append(values["srcdoc"])
        if "style" in values:
            self.style_sources.append(values["style"])
        if (
            canonical_tag in MARKDOWN_HTML_META_TAGS
            and namespace == HTML_NAMESPACE
            and values.get("http-equiv", "").strip().casefold() == "refresh"
            and "content" in values
        ):
            refresh_target = html_meta_refresh_target(values["content"])
            if refresh_target is not None:
                self.targets.append((refresh_target, False, False))
        if tag == "style" and html_style_type_uses_css(values.get("type", "")):
            self.style_content = []
        if tag == "select" and namespace == HTML_NAMESPACE:
            self.in_select = True
        html_push_element_context(self.element_stack, tag, namespace, values)
        if canonical_tag == "frameset" and namespace == HTML_NAMESPACE:
            self.frameset_depth += 1

    def handle_startendtag(
        self, tag: str, attributes: list[tuple[str, str | None]]
    ) -> None:
        tag = tag.casefold()
        raw_tag = self.get_starttag_text()
        values = (
            html_raw_start_tag_attributes(raw_tag)
            if raw_tag is not None
            else {
                name.casefold(): value or ""
                for name, value in attributes
            }
        )
        namespace = html_start_tag_namespace(self.element_stack, tag, values)
        self.handle_starttag(tag, attributes)
        if html_slash_closes_context(
            html_canonical_tag_name(tag, namespace),
            inside_foreign=namespace != HTML_NAMESPACE,
        ):
            self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self.style_content is not None:
            self.style_content.append(data)
        if self.module_script_content is not None:
            self.module_script_content.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag == "template" and self.template_depth:
            self.template_depth -= 1
            return
        if self.template_depth:
            return
        if tag == "form":
            if not self.form_active:
                return
            self.form_active = False
        if tag == "style" and self.style_content is not None:
            self.style_sources.append("".join(self.style_content))
            self.style_content = None
        if tag == "script" and self.module_script_content is not None:
            self.finish_module_script_content()
        if tag == "frameset" and self.frameset_depth:
            self.frameset_depth -= 1
            if not self.frameset_depth:
                self.after_frameset = True
        html_pop_element_context(self.element_stack, tag)
        self.in_select = html_has_ancestor(
            self.element_stack, frozenset({"select"})
        )

    def finish_module_script_content(self) -> None:
        """Collect static imports from the current inline module body."""

        if self.module_script_content is None:
            return
        for target in javascript_static_module_specifiers(
            "".join(self.module_script_content)
        ):
            self.targets.append((target, False, True))
            self.module_script_targets.append(target)
        self.module_script_content = None

    def finish(self) -> None:
        self.close()
        self.finish_module_script_content()
        self.targets.extend(
            html_owned_formaction_targets(
                self.formaction_candidates, self.first_id_elements
            )
        )
        if self.style_content is not None:
            self.style_sources.append("".join(self.style_content))
            self.style_content = None
        used_custom_properties = css_used_custom_properties(
            self.style_sources
        )
        self.used_custom_properties.update(used_custom_properties)
        for style_source in self.style_sources:
            self.targets.extend(
                (target, False, requires_file)
                for target, requires_file in css_resource_references(
                    style_source,
                    used_custom_properties=used_custom_properties,
                    imported_targets=self.stylesheet_targets,
                )
            )


class HTMLDocumentFragmentParser(HTMLParser):
    """Collect addressable fragments from a standalone HTML document."""

    CDATA_CONTENT_ELEMENTS = tuple(HTML_SCRIPTING_ENABLED_RAW_TEXT_TAGS)

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.fragments: set[str] = set()
        self.template_depth = 0
        self.in_select = False
        self.element_stack: list[tuple[str, str, dict[str, str]]] = []

    def handle_starttag(
        self, tag: str, attributes: list[tuple[str, str | None]]
    ) -> None:
        tag = tag.casefold()
        if self.template_depth:
            if tag == "template":
                self.template_depth += 1
            return
        if self.in_select:
            if tag in HTML_SELECT_BREAKOUT_START_TAGS:
                self.in_select = False
            elif tag == "select":
                self.in_select = False
                return
            elif tag not in HTML_SELECT_ALLOWED_START_TAGS:
                return
        values: dict[str, str] = {}
        for name, value in attributes:
            values.setdefault(name.casefold(), value or "")
        namespace = html_start_tag_namespace(self.element_stack, tag, values)
        if "id" in values:
            self.fragments.add(values["id"])
        if tag == "a" and namespace == HTML_NAMESPACE and "name" in values:
            self.fragments.add(values["name"])
        if tag == "template" and namespace == HTML_NAMESPACE:
            self.template_depth += 1
            return
        if tag == "select" and namespace == HTML_NAMESPACE:
            self.in_select = True
        html_push_element_context(self.element_stack, tag, namespace, values)

    def handle_startendtag(
        self, tag: str, attributes: list[tuple[str, str | None]]
    ) -> None:
        tag = tag.casefold()
        values = {
            name.casefold(): value or "" for name, value in attributes
        }
        namespace = html_start_tag_namespace(self.element_stack, tag, values)
        self.handle_starttag(tag, attributes)
        if html_slash_closes_context(
            html_canonical_tag_name(tag, namespace),
            inside_foreign=namespace != HTML_NAMESPACE,
        ):
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag == "template" and self.template_depth:
            self.template_depth -= 1
            return
        if self.template_depth:
            return
        html_pop_element_context(self.element_stack, tag)
        self.in_select = html_has_ancestor(
            self.element_stack, frozenset({"select"})
        )


def html_document_fragments(text: str) -> set[str]:
    """Return IDs and legacy anchor names from a standalone HTML document."""

    parser = HTMLDocumentFragmentParser()
    parser.feed(text)
    parser.close()
    return parser.fragments


def svg_document_fragments(text: str) -> set[str]:
    """Return case-sensitive IDs from a standalone SVG document."""

    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError:
        return set()
    fragments: set[str] = set()
    for element in root.iter():
        identifier = element.attrib.get(
            "id", element.attrib.get(XML_ID_ATTRIBUTE)
        )
        if identifier is not None:
            fragments.add(identifier)
    return fragments


def svg_fragment_is_view_specification(fragment: str) -> bool:
    """Return whether a fragment is a supported SVG viewBox specification."""

    whitespace = r"[\t\n\f\r ]*"
    separator = r"(?:[\t\n\f\r ]*,[\t\n\f\r ]*|[\t\n\f\r ]+)"
    number = HTML_FLOATING_POINT_NUMBER.pattern
    match = re.fullmatch(
        rf"svgView\({whitespace}viewBox\({whitespace}"
        rf"(?P<x>{number}){separator}(?P<y>{number}){separator}"
        rf"(?P<width>{number}){separator}(?P<height>{number})"
        rf"{whitespace}\){whitespace}\)",
        fragment,
    )
    return bool(
        match
        and float(match.group("width")) >= 0
        and float(match.group("height")) >= 0
    )


def xml_expanded_name(name: object) -> tuple[str, str]:
    """Split an ElementTree expanded name into namespace and local name."""

    if not isinstance(name, str):
        return "", ""
    if name.startswith("{") and "}" in name:
        namespace, local_name = name[1:].split("}", 1)
        return namespace, local_name
    return "", name


def xml_resolve_target(target: str, base: str) -> str:
    """Resolve an XML resource target against its inherited base URI."""

    try:
        return urljoin(base, target)
    except ValueError:
        return target


def xml_stylesheet_processing_instruction_targets(text: str) -> list[str]:
    """Return CSS hrefs from well-formed xml-stylesheet instructions."""

    parser = ElementTree.XMLPullParser(events=("start", "pi"))
    try:
        parser.feed(text)
        parser.close()
        processing_instructions: list[str] = []
        document_element_started = False
        for event, element in parser.read_events():
            if event == "start":
                document_element_started = True
            elif not document_element_started:
                processing_instructions.append(element.text or "")
    except ElementTree.ParseError:
        return []

    targets: list[str] = []
    attribute_pattern = re.compile(
        r"(?P<name>[A-Za-z_:][A-Za-z0-9_.:-]*)"
        r"[\t\r\n ]*=[\t\r\n ]*"
        r"(?P<quote>['\"])(?P<value>.*?)(?P=quote)",
        re.DOTALL,
    )
    for instruction in processing_instructions:
        target_match = re.match(r"xml-stylesheet(?=[\t\r\n ]|$)", instruction)
        if target_match is None:
            continue
        attributes: dict[str, str] = {}
        cursor = target_match.end()
        valid = True
        while cursor < len(instruction):
            whitespace = re.match(r"[\t\r\n ]+", instruction[cursor:])
            if whitespace is None:
                valid = False
                break
            cursor += whitespace.end()
            if cursor == len(instruction):
                break
            attribute = attribute_pattern.match(instruction, cursor)
            if attribute is None:
                valid = False
                break
            attributes.setdefault(
                attribute.group("name"), html_unescape(attribute.group("value"))
            )
            cursor = attribute.end()
        if (
            valid
            and "href" in attributes
            and attributes.get("type", "text/css").strip().casefold()
            == "text/css"
        ):
            targets.append(attributes["href"])
    return targets


def svg_xml_element_resource_targets(
    root: ElementTree.Element,
    *,
    stylesheet_targets: list[str] | None = None,
    embedded_document_targets: list[str] | None = None,
    module_script_targets: list[str] | None = None,
    used_custom_property_names: set[str] | None = None,
    inherited_base: str = "",
) -> list[tuple[str, bool, bool]]:
    """Collect browser-loaded targets from an XML-parsed SVG subtree."""

    targets: list[tuple[str, bool, bool]] = []
    style_sources: list[tuple[str, str]] = []
    document_stylesheet_targets: list[str] = []
    document_resource_targets: list[str] = []
    document_module_script_targets: list[str] = []
    srcdocs: list[tuple[str, str]] = []
    xlink_href = "{http://www.w3.org/1999/xlink}href"

    def add_target(
        target: str, base: str, *, requires_file: bool
    ) -> str:
        resolved_target = xml_resolve_target(target, base)
        targets.append((resolved_target, False, requires_file))
        return resolved_target

    def visit(
        element: ElementTree.Element,
        base: str,
        parent_name: tuple[str, str] = ("", ""),
        inside_foreign_object: bool = False,
    ) -> None:
        namespace, tag = xml_expanded_name(element.tag)
        attributes = element.attrib
        effective_base = base
        if XML_BASE_ATTRIBUTE in attributes:
            effective_base = xml_resolve_target(
                attributes[XML_BASE_ATTRIBUTE], base
            )
        descendant_inside_foreign_object = inside_foreign_object or (
            namespace == SVG_XML_NAMESPACE and tag == "foreignObject"
        )
        if namespace == SVG_XML_NAMESPACE:
            if tag in MARKDOWN_SVG_RESOURCE_HREF_TAGS:
                target = attributes.get("href", attributes.get(xlink_href))
                if target is not None:
                    resolved_target = xml_resolve_target(target, effective_base)
                    add_target(
                        target,
                        effective_base,
                        requires_file=html_target_requires_file(
                            resolved_target
                        ),
                    )
            if tag in MARKDOWN_SVG_NAVIGATION_HREF_TAGS:
                target = attributes.get("href", attributes.get(xlink_href))
                if target is not None:
                    add_target(
                        target, effective_base, requires_file=False
                    )
            for target, _, _ in svg_presentation_resource_targets(attributes):
                resolved_target = xml_resolve_target(target, effective_base)
                add_target(
                    target,
                    effective_base,
                    requires_file=html_target_requires_file(resolved_target),
                )
            if "style" in attributes:
                style_sources.append((attributes["style"], effective_base))
            if tag == "style":
                style_sources.append(("".join(element.itertext()), effective_base))
        elif namespace == XHTML_XML_NAMESPACE and inside_foreign_object:
            if tag == "a" and "href" in attributes:
                add_target(attributes["href"], effective_base, requires_file=False)
            if tag == "link":
                relations = frozenset(
                    re.findall(
                        r"[^\t\n\f\r ]+", attributes.get("rel", "").casefold()
                    )
                )
                if "href" in attributes:
                    is_resource = bool(
                        relations.intersection(
                            MARKDOWN_HTML_LINK_RESOURCE_RELATIONS
                        )
                    )
                    resolved_target = xml_resolve_target(
                        attributes["href"], effective_base
                    )
                    if html_link_href_should_validate(relations):
                        add_target(
                            attributes["href"],
                            effective_base,
                            requires_file=is_resource,
                        )
                    if "stylesheet" in relations:
                        document_stylesheet_targets.append(resolved_target)
                if (
                    "preload" in relations
                    and attributes.get("as", "").casefold()
                    in MARKDOWN_HTML_IMAGE_PRELOAD_AS_VALUES
                    and "imagesrcset" in attributes
                ):
                    for candidate in html_srcset_candidates(
                        attributes["imagesrcset"]
                    ):
                        add_target(candidate, effective_base, requires_file=True)
            if (
                tag in MARKDOWN_HTML_SRC_TAGS
                and "src" in attributes
                and not (tag == "iframe" and "srcdoc" in attributes)
                and not (
                    tag == "img"
                    and "srcset" in attributes
                    and html_srcset_overrides_src(attributes["srcset"])
                )
                and not (
                    tag == "script"
                    and not html_script_attributes_use_src(attributes)
                )
            ):
                resolved_target = add_target(
                    attributes["src"], effective_base, requires_file=True
                )
                if tag in MARKDOWN_HTML_EMBEDDED_DOCUMENT_SRC_TAGS:
                    document_resource_targets.append(resolved_target)
                if tag == "script" and html_script_is_module(attributes):
                    document_module_script_targets.append(resolved_target)
            if (
                tag == "script"
                and "src" not in attributes
                and html_script_is_module(attributes)
            ):
                for target in javascript_static_module_specifiers(
                    "".join(element.itertext())
                ):
                    resolved_target = add_target(
                        target, effective_base, requires_file=True
                    )
                    document_module_script_targets.append(resolved_target)
            if (
                tag == "input"
                and attributes.get("type", "").casefold()
                in MARKDOWN_HTML_IMAGE_INPUT_TYPES
                and "src" in attributes
            ):
                add_target(attributes["src"], effective_base, requires_file=True)
            if (
                tag == "source"
                and parent_name[0] == XHTML_XML_NAMESPACE
                and parent_name[1] in {"audio", "video"}
                and "src" in attributes
            ):
                add_target(attributes["src"], effective_base, requires_file=True)
            if (
                tag == "source"
                and parent_name == (XHTML_XML_NAMESPACE, "picture")
                and "srcset" in attributes
            ):
                for candidate in html_srcset_candidates(attributes["srcset"]):
                    add_target(candidate, effective_base, requires_file=True)
            if tag == "img" and "srcset" in attributes:
                for candidate in html_srcset_candidates(attributes["srcset"]):
                    add_target(candidate, effective_base, requires_file=True)
            if tag == "object" and "data" in attributes:
                resolved_target = add_target(
                    attributes["data"], effective_base, requires_file=True
                )
                document_resource_targets.append(resolved_target)
            if tag == "video" and "poster" in attributes:
                add_target(attributes["poster"], effective_base, requires_file=True)
            if (
                tag in MARKDOWN_HTML_BACKGROUND_TAGS
                and attributes.get("background", "")
            ):
                add_target(
                    attributes["background"], effective_base, requires_file=True
                )
            if tag == "form" and "action" in attributes:
                add_target(attributes["action"], effective_base, requires_file=False)
            formaction = html_formaction_value(tag, HTML_NAMESPACE, attributes)
            if formaction is not None and "form" in attributes:
                add_target(formaction, effective_base, requires_file=False)
            if "style" in attributes:
                style_sources.append((attributes["style"], effective_base))
            if tag == "style" and html_style_type_uses_css(
                attributes.get("type", "")
            ):
                style_sources.append(("".join(element.itertext()), effective_base))
            if (
                tag == "meta"
                and attributes.get("http-equiv", "").strip().casefold()
                == "refresh"
                and "content" in attributes
            ):
                refresh_target = html_meta_refresh_target(attributes["content"])
                if refresh_target is not None:
                    add_target(
                        refresh_target, effective_base, requires_file=False
                    )
            if tag == "iframe" and "srcdoc" in attributes:
                srcdocs.append((attributes["srcdoc"], effective_base))
        for child in element:
            visit(
                child,
                effective_base,
                (namespace, tag),
                descendant_inside_foreign_object,
            )

    visit(root, inherited_base)
    used_custom_properties = css_used_custom_properties(
        [style_source for style_source, _ in style_sources]
    )
    if used_custom_property_names is not None:
        used_custom_property_names.update(used_custom_properties)
    for style_source, effective_base in style_sources:
        imported_targets: list[str] = []
        for target, _ in css_resource_references(
            style_source,
            used_custom_properties=used_custom_properties,
            imported_targets=imported_targets,
        ):
            resolved_target = xml_resolve_target(target, effective_base)
            targets.append(
                (
                    resolved_target,
                    False,
                    html_target_requires_file(resolved_target),
                )
            )
        document_stylesheet_targets.extend(
            xml_resolve_target(target, effective_base)
            for target in imported_targets
        )
    if stylesheet_targets is not None:
        stylesheet_targets.extend(document_stylesheet_targets)
    if embedded_document_targets is not None:
        embedded_document_targets.extend(document_resource_targets)
    if module_script_targets is not None:
        module_script_targets.extend(document_module_script_targets)
    for srcdoc, srcdoc_base in srcdocs:
        targets.extend(
            html_fragment_resource_targets(
                srcdoc,
                inherited_base=srcdoc_base,
                stylesheet_targets=stylesheet_targets,
                embedded_document_targets=embedded_document_targets,
                module_script_targets=module_script_targets,
                used_custom_property_names=used_custom_property_names,
            )
        )
    return targets


def svg_document_resource_targets(
    text: str,
    *,
    stylesheet_targets: list[str] | None = None,
    embedded_document_targets: list[str] | None = None,
    module_script_targets: list[str] | None = None,
    used_custom_property_names: set[str] | None = None,
) -> list[tuple[str, bool, bool]]:
    """Collect browser-loaded targets from a standalone SVG document."""

    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError:
        return []
    targets = svg_xml_element_resource_targets(
        root,
        stylesheet_targets=stylesheet_targets,
        embedded_document_targets=embedded_document_targets,
        module_script_targets=module_script_targets,
        used_custom_property_names=used_custom_property_names,
    )
    processing_instruction_targets = (
        xml_stylesheet_processing_instruction_targets(text)
    )
    targets.extend(
        (target, False, True) for target in processing_instruction_targets
    )
    if stylesheet_targets is not None:
        stylesheet_targets.extend(processing_instruction_targets)
    return targets


def xhtml_document_fragments(text: str) -> set[str]:
    """Return case-sensitive XHTML and XML fragment identifiers."""

    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError:
        return set()
    fragments: set[str] = set()
    for element in root.iter():
        identifier = element.attrib.get(
            "id", element.attrib.get(XML_ID_ATTRIBUTE)
        )
        if identifier is not None:
            fragments.add(identifier)
    return fragments


def xhtml_document_resource_targets(
    text: str,
    *,
    stylesheet_targets: list[str] | None = None,
    embedded_document_targets: list[str] | None = None,
    module_script_targets: list[str] | None = None,
    used_custom_property_names: set[str] | None = None,
) -> list[tuple[str, bool, bool]]:
    """Collect resources from XHTML using XML namespace and name semantics."""

    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError:
        return []

    targets: list[tuple[str, bool, bool]] = []
    style_sources: list[tuple[str, str]] = []
    document_stylesheet_targets: list[str] = []
    document_resource_targets: list[str] = []
    document_module_script_targets: list[str] = []
    srcdocs: list[tuple[str, str]] = []
    first_id_elements: dict[str, tuple[str, str]] = {}
    document_base = ""
    document_base_found = False

    for element in root.iter():
        namespace, tag = xml_expanded_name(element.tag)
        attributes = element.attrib
        if "id" in attributes:
            first_id_elements.setdefault(
                attributes["id"], (tag, namespace)
            )
        if (
            namespace == XHTML_XML_NAMESPACE
            and tag == "base"
            and not document_base_found
            and "href" in attributes
        ):
            try:
                urlsplit(attributes["href"])
            except ValueError:
                pass
            else:
                document_base = attributes["href"]
                document_base_found = True

    def add_target(
        target: str, base: str, *, requires_file: bool
    ) -> str:
        resolved_target = xml_resolve_target(target, base)
        targets.append((resolved_target, False, requires_file))
        return resolved_target

    def visit(
        element: ElementTree.Element,
        inherited_base: str,
        parent_name: tuple[str, str] = ("", ""),
        inside_form: bool = False,
    ) -> None:
        namespace, tag = xml_expanded_name(element.tag)
        attributes = element.attrib
        effective_base = inherited_base
        if XML_BASE_ATTRIBUTE in attributes:
            effective_base = xml_resolve_target(
                attributes[XML_BASE_ATTRIBUTE], inherited_base
            )
        if namespace == SVG_XML_NAMESPACE:
            return
        if namespace != XHTML_XML_NAMESPACE:
            for child in element:
                visit(child, effective_base, (namespace, tag), inside_form)
            return
        if tag == "a" and "href" in attributes:
            add_target(attributes["href"], effective_base, requires_file=False)
        if tag == "link":
            relations = frozenset(
                re.findall(
                    r"[^\t\n\f\r ]+", attributes.get("rel", "").casefold()
                )
            )
            if "href" in attributes:
                is_resource = bool(
                    relations.intersection(MARKDOWN_HTML_LINK_RESOURCE_RELATIONS)
                )
                resolved_target = xml_resolve_target(
                    attributes["href"], effective_base
                )
                if html_link_href_should_validate(relations):
                    add_target(
                        attributes["href"],
                        effective_base,
                        requires_file=is_resource,
                    )
                if "stylesheet" in relations:
                    document_stylesheet_targets.append(resolved_target)
            if (
                "preload" in relations
                and attributes.get("as", "").casefold()
                in MARKDOWN_HTML_IMAGE_PRELOAD_AS_VALUES
                and "imagesrcset" in attributes
            ):
                for candidate in html_srcset_candidates(
                    attributes["imagesrcset"]
                ):
                    add_target(candidate, effective_base, requires_file=True)
        if (
            tag in MARKDOWN_HTML_SRC_TAGS
            and "src" in attributes
            and not (tag == "iframe" and "srcdoc" in attributes)
            and not (
                tag == "img"
                and "srcset" in attributes
                and html_srcset_overrides_src(attributes["srcset"])
            )
            and not (
                tag == "script"
                and not html_script_attributes_use_src(attributes)
            )
        ):
            resolved_target = add_target(
                attributes["src"], effective_base, requires_file=True
            )
            if tag in MARKDOWN_HTML_EMBEDDED_DOCUMENT_SRC_TAGS:
                document_resource_targets.append(resolved_target)
            if tag == "script" and html_script_is_module(attributes):
                document_module_script_targets.append(resolved_target)
        if (
            tag == "script"
            and "src" not in attributes
            and html_script_is_module(attributes)
        ):
            for target in javascript_static_module_specifiers(
                "".join(element.itertext())
            ):
                resolved_target = add_target(
                    target, effective_base, requires_file=True
                )
                document_module_script_targets.append(resolved_target)
        if (
            tag == "input"
            and attributes.get("type", "").casefold()
            in MARKDOWN_HTML_IMAGE_INPUT_TYPES
            and "src" in attributes
        ):
            add_target(attributes["src"], effective_base, requires_file=True)
        if (
            tag == "source"
            and parent_name[0] == XHTML_XML_NAMESPACE
            and parent_name[1] in {"audio", "video"}
            and "src" in attributes
        ):
            add_target(attributes["src"], effective_base, requires_file=True)
        if (
            tag == "source"
            and parent_name == (XHTML_XML_NAMESPACE, "picture")
            and "srcset" in attributes
        ):
            for candidate in html_srcset_candidates(attributes["srcset"]):
                add_target(candidate, effective_base, requires_file=True)
        if tag == "img" and "srcset" in attributes:
            for candidate in html_srcset_candidates(attributes["srcset"]):
                add_target(candidate, effective_base, requires_file=True)
        if tag == "object" and "data" in attributes:
            resolved_target = add_target(
                attributes["data"], effective_base, requires_file=True
            )
            document_resource_targets.append(resolved_target)
        if tag == "video" and "poster" in attributes:
            add_target(attributes["poster"], effective_base, requires_file=True)
        if (
            tag in MARKDOWN_HTML_BACKGROUND_TAGS
            and attributes.get("background", "")
        ):
            add_target(
                attributes["background"], effective_base, requires_file=True
            )
        if tag == "form" and "action" in attributes:
            add_target(attributes["action"], effective_base, requires_file=False)
        formaction = html_formaction_value(tag, HTML_NAMESPACE, attributes)
        if formaction is not None:
            explicit_form_id = attributes.get("form")
            has_form_owner = (
                inside_form
                if explicit_form_id is None
                else first_id_elements.get(explicit_form_id)
                == ("form", XHTML_XML_NAMESPACE)
            )
            if has_form_owner:
                add_target(formaction, effective_base, requires_file=False)
        if "style" in attributes:
            style_sources.append((attributes["style"], effective_base))
        if tag == "style" and html_style_type_uses_css(attributes.get("type", "")):
            style_sources.append(("".join(element.itertext()), effective_base))
        if (
            tag == "meta"
            and attributes.get("http-equiv", "").strip().casefold() == "refresh"
            and "content" in attributes
        ):
            refresh_target = html_meta_refresh_target(attributes["content"])
            if refresh_target is not None:
                add_target(
                    refresh_target, effective_base, requires_file=False
                )
        if tag == "iframe" and "srcdoc" in attributes:
            srcdocs.append((attributes["srcdoc"], effective_base))
        descendant_inside_form = inside_form or tag == "form"
        for child in element:
            visit(
                child,
                effective_base,
                (namespace, tag),
                descendant_inside_form,
            )

    visit(root, document_base)

    targets.extend(
        svg_xml_element_resource_targets(
            root,
            stylesheet_targets=document_stylesheet_targets,
            embedded_document_targets=document_resource_targets,
            module_script_targets=document_module_script_targets,
            used_custom_property_names=used_custom_property_names,
            inherited_base=document_base,
        )
    )
    used_custom_properties = css_used_custom_properties(
        [style_source for style_source, _ in style_sources]
    )
    if used_custom_property_names is not None:
        used_custom_property_names.update(used_custom_properties)
    for style_source, style_base in style_sources:
        imported_targets: list[str] = []
        for target, requires_file in css_resource_references(
            style_source,
            used_custom_properties=used_custom_properties,
            imported_targets=imported_targets,
        ):
            add_target(
                target, style_base, requires_file=requires_file
            )
        document_stylesheet_targets.extend(
            xml_resolve_target(target, style_base)
            for target in imported_targets
        )
    for srcdoc, srcdoc_base in srcdocs:
        targets.extend(
            html_fragment_resource_targets(
                srcdoc,
                inherited_base=srcdoc_base,
                stylesheet_targets=document_stylesheet_targets,
                embedded_document_targets=document_resource_targets,
                module_script_targets=document_module_script_targets,
                used_custom_property_names=used_custom_property_names,
            )
        )
    processing_instruction_targets = (
        xml_stylesheet_processing_instruction_targets(text)
    )
    targets.extend(
        (target, False, True) for target in processing_instruction_targets
    )
    document_stylesheet_targets.extend(processing_instruction_targets)
    if stylesheet_targets is not None:
        stylesheet_targets.extend(document_stylesheet_targets)
    if embedded_document_targets is not None:
        embedded_document_targets.extend(document_resource_targets)
    if module_script_targets is not None:
        module_script_targets.extend(document_module_script_targets)
    return targets


def url_element_fragment(fragment: str) -> str:
    """Return the element-ID portion before any text-fragment directive."""

    return fragment.split(":~:", 1)[0]


def html_fragment_is_special_top(fragment: str) -> bool:
    """Return whether an HTML fragment denotes the document top."""

    return fragment.casefold() == "top"


def html_same_document_fragment(target: str) -> str | None:
    """Return a decoded fragment for a fragment-only URL."""

    try:
        parsed = urlsplit(target)
    except ValueError:
        return None
    if (
        parsed.scheme
        or parsed.netloc
        or parsed.path
        or parsed.query
        or not parsed.fragment
    ):
        return None
    return unquote(parsed.fragment)


def html_fragment_resource_targets(
    text: str,
    *,
    inherited_base: str = "",
    stylesheet_targets: list[str] | None = None,
    embedded_document_targets: list[str] | None = None,
    module_script_targets: list[str] | None = None,
    used_custom_property_names: set[str] | None = None,
) -> list[tuple[str, bool, bool]]:
    """Collect targets from HTML parsed inside an iframe srcdoc document."""

    targets: list[tuple[str, bool, bool]] = []
    pending_documents = [(text, inherited_base)]
    seen_documents: set[tuple[str, str]] = set()
    while pending_documents:
        document, parent_base = pending_documents.pop()
        document_key = (document, parent_base)
        if document_key in seen_documents:
            continue
        seen_documents.add(document_key)

        parser = HTMLFragmentResourceParser()
        parser.feed(document)
        parser.finish()
        if used_custom_property_names is not None:
            used_custom_property_names.update(parser.used_custom_properties)
        effective_base = parent_base
        if parser.base_href is not None:
            try:
                effective_base = urljoin(
                    html_url_for_resolution(parent_base),
                    html_url_for_resolution(parser.base_href),
                )
                urlsplit(effective_base)
            except ValueError:
                effective_base = parent_base

        if stylesheet_targets is not None:
            stylesheet_targets.extend(
                target
                for target, _, _ in resolve_html_targets(
                    [
                        (target, False, True)
                        for target in parser.stylesheet_targets
                    ],
                    effective_base,
                )
            )
        if embedded_document_targets is not None:
            embedded_document_targets.extend(
                target
                for target, _, _ in resolve_html_targets(
                    [
                        (target, False, True)
                        for target in parser.embedded_document_targets
                    ],
                    effective_base,
                )
            )
        if module_script_targets is not None:
            module_script_targets.extend(
                target
                for target, _, _ in resolve_html_targets(
                    [
                        (target, False, True)
                        for target in parser.module_script_targets
                    ],
                    effective_base,
                )
            )

        for target, is_markdown, requires_file in parser.targets:
            if html_same_document_fragment(target) is not None:
                continue
            try:
                resolved_target = urljoin(
                    html_url_for_resolution(effective_base),
                    html_url_for_resolution(target),
                )
            except ValueError:
                resolved_target = target
            targets.append((resolved_target, is_markdown, requires_file))
        pending_documents.extend(
            (srcdoc, effective_base) for srcdoc in reversed(parser.srcdocs)
        )
    return targets


def html_srcdoc_fragment_errors(text: str) -> list[str]:
    """Return missing same-document fragments from nested srcdoc documents."""

    searchable_text = mask_html_template_contents(
        mask_html_raw_text_element_contents(text)
    )
    pending_documents = [
        html_attribute_unescape(srcdoc)
        for srcdoc in html_attribute_values(
            searchable_text,
            MARKDOWN_HTML_SRCDOC_ATTRIBUTES,
            tag_names=MARKDOWN_HTML_SRCDOC_TAGS,
        )
    ]
    seen_documents: set[str] = set()
    missing_fragments: list[str] = []
    while pending_documents:
        document = pending_documents.pop()
        if document in seen_documents:
            continue
        seen_documents.add(document)

        parser = HTMLFragmentResourceParser()
        parser.feed(document)
        parser.finish()
        fragments = html_document_fragments(document)
        for target, _, _ in parser.targets:
            fragment = html_same_document_fragment(target)
            if fragment is None:
                continue
            element_fragment = url_element_fragment(fragment)
            if (
                element_fragment
                and not html_fragment_is_special_top(element_fragment)
                and element_fragment not in fragments
            ):
                missing_fragments.append(target)
        pending_documents.extend(reversed(parser.srcdocs))
    return missing_fragments


def mask_html_raw_text_element_contents(text: str) -> str:
    """Mask HTML raw-text/RCDATA bodies while preserving tags and line endings."""

    characters = list(text)
    element_stack: list[tuple[str, str, dict[str, str]]] = []
    search_from = 0
    while search_from < len(text):
        tag_match = HTML_RAW_BLOCK_TAG_OR_CLOSING.search(text, search_from)
        if tag_match is None:
            break
        value = tag_match.group(0)
        name_match = re.match(r"</?([A-Za-z][A-Za-z0-9-]*)", value)
        if name_match is None:
            search_from = tag_match.end()
            continue
        tag = name_match.group(1).casefold()
        if value.startswith("</"):
            html_pop_element_context(element_stack, tag)
            search_from = tag_match.end()
            continue

        attributes: dict[str, str] = {}
        encoding_values = html_attribute_values(value, frozenset({"encoding"}))
        if encoding_values:
            attributes["encoding"] = html_attribute_unescape(encoding_values[0])
        namespace = html_start_tag_namespace(element_stack, tag, attributes)
        canonical_tag = html_canonical_tag_name(tag, namespace)
        html_push_element_context(element_stack, tag, namespace, attributes)

        is_self_closing = value.rstrip().endswith("/>") and html_slash_closes_context(
            canonical_tag, inside_foreign=namespace != HTML_NAMESPACE
        )
        if is_self_closing:
            html_pop_element_context(element_stack, tag)
            search_from = tag_match.end()
            continue
        if (
            namespace != HTML_NAMESPACE
            or tag not in HTML_SCRIPTING_ENABLED_RAW_TEXT_TAGS
        ):
            search_from = tag_match.end()
            continue

        closing_match: re.Match[str] | None = None
        for candidate in HTML_RAW_BLOCK_TAG_OR_CLOSING.finditer(
            text, tag_match.end()
        ):
            if re.fullmatch(
                rf"</{re.escape(tag)}[ \t\f\r\n]*>",
                candidate.group(0),
                re.IGNORECASE,
            ):
                closing_match = candidate
                break
        if closing_match is None:
            break
        content_end = closing_match.start()
        for position in range(tag_match.end(), content_end):
            if characters[position] not in "\r\n":
                characters[position] = " "
        html_pop_element_context(element_stack, tag)
        search_from = closing_match.end()
    return "".join(characters)


def mask_html_template_contents(text: str) -> str:
    """Mask inert template bodies while preserving their surrounding tags."""

    characters = list(text)
    element_stack: list[tuple[str, str, dict[str, str]]] = []
    template_depth = 0
    content_start: int | None = None
    for tag_match in MARKDOWN_HTML_TAG_OR_CLOSING.finditer(text):
        value = tag_match.group(0)
        name_match = re.match(r"</?([A-Za-z][A-Za-z0-9-]*)", value)
        if name_match is None:
            continue
        tag = name_match.group(1).casefold()
        is_closing = value.startswith("</")
        if template_depth:
            if tag != "template":
                continue
            if is_closing:
                template_depth -= 1
                if template_depth == 0 and content_start is not None:
                    for position in range(content_start, tag_match.start()):
                        if characters[position] not in "\r\n":
                            characters[position] = " "
                    content_start = None
            else:
                template_depth += 1
            continue
        if is_closing:
            html_pop_element_context(element_stack, tag)
            continue

        attributes: dict[str, str] = {}
        encoding_values = html_attribute_values(value, frozenset({"encoding"}))
        if encoding_values:
            attributes["encoding"] = html_attribute_unescape(
                encoding_values[0]
            )
        shadow_modes = html_attribute_values(
            value, frozenset({"shadowrootmode"})
        )
        if shadow_modes:
            attributes["shadowrootmode"] = html_attribute_unescape(
                shadow_modes[0]
            )
        namespace = html_start_tag_namespace(
            element_stack, tag, attributes
        )
        if (
            tag == "template"
            and namespace == HTML_NAMESPACE
            and not html_template_establishes_declarative_shadow_root(
                element_stack, namespace, attributes
            )
        ):
            template_depth = 1
            content_start = tag_match.end()
            continue
        html_push_element_context(element_stack, tag, namespace, attributes)
        if value.rstrip().endswith("/>") and html_slash_closes_context(
            html_canonical_tag_name(tag, namespace),
            inside_foreign=namespace != HTML_NAMESPACE,
        ):
            html_pop_element_context(element_stack, tag)
    if template_depth and content_start is not None:
        for position in range(content_start, len(characters)):
            if characters[position] not in "\r\n":
                characters[position] = " "
    return "".join(characters)


def html_style_contents(text: str) -> list[str]:
    """Return the bodies of complete rendered inline style elements."""

    contents: list[str] = []
    paragraph_boundaries = markdown_paragraph_boundaries(text)
    closing = re.compile(r"</style[ \t\f\r\n]*>", re.IGNORECASE)
    for tag in MARKDOWN_HTML_TAG.finditer(text):
        if not re.match(r"<style(?=[\s>])", tag.group(0), re.IGNORECASE):
            continue
        if not markdown_html_tag_is_rendered(text, tag, paragraph_boundaries):
            continue
        type_values = html_attribute_values(
            tag.group(0),
            frozenset({"type"}),
            tag_names=frozenset({"style"}),
        )
        if type_values and not html_style_type_uses_css(
            html_attribute_unescape(type_values[0])
        ):
            continue
        closing_match = closing.search(text, tag.end())
        if closing_match is None:
            continue
        contents.append(text[tag.end() : closing_match.start()])
    return contents


def html_effective_base(text: str, inherited_base: str = "") -> str:
    """Return the first valid rendered base URL, or the inherited base."""

    for value in html_context_base_hrefs(text):
        try:
            candidate = urljoin(
                html_url_for_resolution(inherited_base),
                html_url_for_resolution(value),
            )
            urlsplit(candidate)
        except ValueError:
            continue
        return candidate
    return inherited_base


def html_url_for_resolution(target: str) -> str:
    """Normalize browser path separators before resolving an HTML URL."""

    suffix_positions = [
        position
        for separator in ("?", "#")
        if (position := target.find(separator)) >= 0
    ]
    path_end = min(suffix_positions, default=len(target))
    return target[:path_end].replace("\\", "/") + target[path_end:]


def resolve_html_targets(
    targets: list[tuple[str, bool, bool]], base_url: str
) -> list[tuple[str, bool, bool]]:
    """Resolve collected HTML targets against the document base URL."""

    resolved: list[tuple[str, bool, bool]] = []
    for target, is_markdown, requires_file in targets:
        try:
            target = urljoin(
                html_url_for_resolution(base_url),
                html_url_for_resolution(target),
            )
        except ValueError:
            pass
        resolved.append((target, is_markdown, requires_file))
    return resolved


def html_resource_targets(
    text: str,
    *,
    additional_style_sources: list[str] | None = None,
    additional_module_script_sources: list[str] | None = None,
    stylesheet_targets: list[str] | None = None,
    embedded_document_targets: list[str] | None = None,
    module_script_targets: list[str] | None = None,
    used_custom_property_names: set[str] | None = None,
) -> list[tuple[str, bool, bool]]:
    """Collect navigations and resource requests from rendered HTML."""

    attribute_text = mask_html_template_contents(
        mask_html_raw_text_element_contents(text)
    )
    text = mask_html_template_contents(text)
    effective_base = html_effective_base(text)
    targets: list[tuple[str, bool, bool]] = []
    document_resource_targets: list[str] = []
    document_stylesheet_targets: list[str] = []
    document_module_script_targets: list[str] = []
    targets.extend(
        html_context_resource_targets(
            text,
            embedded_document_targets=document_resource_targets,
            stylesheet_targets=document_stylesheet_targets,
            module_script_targets=document_module_script_targets,
        )
    )
    for module_source in additional_module_script_sources or []:
        for target in javascript_static_module_specifiers(module_source):
            targets.append((target, False, True))
            document_module_script_targets.append(target)
    targets.extend(
        (candidate, False, True)
        for value in html_attribute_values(
            attribute_text,
            MARKDOWN_HTML_SRCSET_ATTRIBUTES,
            tag_names=MARKDOWN_HTML_SRCSET_TAGS,
        )
        for candidate in html_srcset_candidates(html_attribute_unescape(value))
    )
    style_sources = list(additional_style_sources or [])
    style_sources.extend(html_style_contents(text))
    style_sources.extend(
        html_attribute_unescape(style_attribute)
        for style_attribute in html_attribute_values(
            attribute_text,
            MARKDOWN_HTML_STYLE_ATTRIBUTES,
        )
    )
    used_custom_properties = css_used_custom_properties(style_sources)
    if used_custom_property_names is not None:
        used_custom_property_names.update(used_custom_properties)
    for style_source in style_sources:
        targets.extend(
            (target, False, requires_file)
            for target, requires_file in css_resource_references(
                style_source,
                used_custom_properties=used_custom_properties,
                imported_targets=document_stylesheet_targets,
            )
        )
    for content in html_attribute_values(
        attribute_text,
        MARKDOWN_HTML_CONTENT_ATTRIBUTES,
        tag_names=MARKDOWN_HTML_META_TAGS,
        required_attribute_values={"http-equiv": frozenset({"refresh"})},
    ):
        refresh_target = html_meta_refresh_target(
            html_attribute_unescape(content)
        )
        if refresh_target is not None:
            targets.append((refresh_target, False, False))

    targets = resolve_html_targets(targets, effective_base)
    if embedded_document_targets is not None:
        embedded_document_targets.extend(
            target
            for target, _, _ in resolve_html_targets(
                [
                    (target, False, True)
                    for target in document_resource_targets
                ],
                effective_base,
            )
        )
    if stylesheet_targets is not None:
        stylesheet_targets.extend(
            target
            for target, _, _ in resolve_html_targets(
                [
                    (target, False, True)
                    for target in document_stylesheet_targets
                ],
                effective_base,
            )
        )
    if module_script_targets is not None:
        module_script_targets.extend(
            target
            for target, _, _ in resolve_html_targets(
                [
                    (target, False, True)
                    for target in document_module_script_targets
                ],
                effective_base,
            )
        )

    for srcdoc in html_attribute_values(
        attribute_text,
        MARKDOWN_HTML_SRCDOC_ATTRIBUTES,
        tag_names=MARKDOWN_HTML_SRCDOC_TAGS,
    ):
        targets.extend(
            html_fragment_resource_targets(
                html_attribute_unescape(srcdoc),
                inherited_base=effective_base,
                stylesheet_targets=stylesheet_targets,
                embedded_document_targets=embedded_document_targets,
                module_script_targets=module_script_targets,
                used_custom_property_names=used_custom_property_names,
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

    lines_with_endings = markdown_splitlines(text, keepends=True)
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


def markdown_label_end(
    text: str,
    start: int,
    context: tuple[
        list[str],
        list[int],
        list[tuple[tuple[str, ...], str]],
        list[int],
    ]
    | None = None,
) -> int | None:
    """Find a label's closing bracket while respecting nested image/link labels."""

    depth = 1
    index = start + 1
    inline_block_end = markdown_inline_block_end(text, start, context)
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


def markdown_link_targets(
    text: str,
    *,
    stylesheet_targets: list[str] | None = None,
    embedded_document_targets: list[str] | None = None,
    module_script_targets: list[str] | None = None,
    used_custom_property_names: set[str] | None = None,
) -> list[tuple[str, bool, bool]]:
    """Extract destinations and whether they require Markdown parsing or a file."""

    style_content_spans: list[tuple[int, int]] = []
    nested_style_sources: list[str] = []
    module_script_content_spans: list[tuple[int, int]] = []
    rendered_text = markdown_searchable_text(
        text,
        style_content_spans=style_content_spans,
        nested_style_sources=nested_style_sources,
        module_script_content_spans=module_script_content_spans,
    )
    style_contents = [text[start:end] for start, end in style_content_spans]
    style_contents.extend(nested_style_sources)
    module_script_contents = [
        text[start:end] for start, end in module_script_content_spans
    ]
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
        html_resource_targets(
            rendered_html_text,
            additional_style_sources=style_contents,
            additional_module_script_sources=module_script_contents,
            stylesheet_targets=stylesheet_targets,
            embedded_document_targets=embedded_document_targets,
            module_script_targets=module_script_targets,
            used_custom_property_names=used_custom_property_names,
        )
    )
    return targets


def markdown_strip_inline_link_destinations(text: str) -> str:
    """Keep rendered labels while removing valid inline link destinations."""

    result: list[str] = []
    index = 0
    label_pairs = markdown_label_pairs(text)
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

        label_end = label_pairs.get(label_start)
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
    label_pairs = markdown_label_pairs(text)
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

        label_end = label_pairs.get(label_start)
        reference_start = None if label_end is None else label_end + 1
        if (
            reference_start is None
            or reference_start >= len(text)
            or text[reference_start] != "["
        ):
            result.append(text[index])
            index += 1
            continue
        reference_end = label_pairs.get(reference_start)
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
    heading = heading.replace(" ", "-")
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

    lines = markdown_splitlines(text)
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
    structure_lines = markdown_splitlines("".join(structure_characters))
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
    footnote_lines = markdown_splitlines("".join(footnote_characters))
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
    footnote_reference_counts: dict[str, int] = {}
    for footnote in MARKDOWN_FOOTNOTE_REFERENCE.finditer(footnote_text):
        label = MARKDOWN_BACKSLASH_ESCAPE.sub(r"\1", footnote.group("label"))
        normalized_label = markdown_unescape(label).casefold()
        if normalized_label not in footnote_labels:
            continue
        count = footnote_reference_counts.get(normalized_label, 0) + 1
        footnote_reference_counts[normalized_label] = count
        if count == 1:
            fragments.add(f"user-content-fn-{normalized_label}")
        suffix = "" if count == 1 else f"-{count}"
        fragments.add(f"user-content-fnref-{normalized_label}{suffix}")
    for definition in reference_definitions:
        start_line = structure_text.count("\n", 0, definition.start())
        end_line = structure_text.count(
            "\n", 0, max(definition.start(), definition.end() - 1)
        )
        reference_definition_lines.update(range(start_line, end_line + 1))
    anchor_text = mask_html_template_contents(
        markdown_html_anchor_searchable_text(text)
    )
    for anchor in html_attribute_values(anchor_text, MARKDOWN_HTML_ID_ATTRIBUTES):
        fragments.add(html_attribute_unescape(anchor))
    for anchor in html_attribute_values(
        anchor_text,
        MARKDOWN_HTML_NAME_ATTRIBUTES,
        tag_names=MARKDOWN_HTML_LEGACY_ANCHOR_TAGS,
    ):
        fragments.add(html_attribute_unescape(anchor))
    frontmatter_end = markdown_frontmatter_end(
        markdown_splitlines(text, keepends=True)
    )
    content_start = (
        len(markdown_splitlines(text[:frontmatter_end])) if frontmatter_end else 0
    )

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


def unquote_url_path(path: str) -> str:
    """Decode URL paths without turning encoded separators into directories."""

    return "".join(
        piece
        if PERCENT_ENCODED_PATH_SEPARATOR.fullmatch(piece)
        else unquote(piece)
        for piece in PERCENT_ENCODED_PATH_SEPARATOR.split(path)
    )


def javascript_string_token(text: str, start: int) -> tuple[str, int] | None:
    """Decode a JavaScript string token used as a module specifier."""

    quote = text[start]
    value: list[str] = []
    index = start + 1
    escapes = {
        "b": "\b",
        "f": "\f",
        "n": "\n",
        "r": "\r",
        "t": "\t",
        "v": "\v",
        "0": "\0",
    }
    while index < len(text):
        character = text[index]
        if character == quote:
            return "".join(value), index + 1
        if character in "\r\n":
            return None
        if character != "\\":
            value.append(character)
            index += 1
            continue
        index += 1
        if index >= len(text):
            return None
        escaped = text[index]
        if escaped == "\r":
            index += 1
            if index < len(text) and text[index] == "\n":
                index += 1
            continue
        if escaped == "\n":
            index += 1
            continue
        if escaped == "x" and index + 2 < len(text):
            digits = text[index + 1 : index + 3]
            if all(digit in CSS_HEX_DIGITS for digit in digits):
                value.append(chr(int(digits, 16)))
                index += 3
                continue
        if escaped == "u":
            if index + 1 < len(text) and text[index + 1] == "{":
                closing = text.find("}", index + 2)
                digits = text[index + 2 : closing] if closing >= 0 else ""
                if (
                    digits
                    and len(digits) <= 6
                    and all(digit in CSS_HEX_DIGITS for digit in digits)
                    and int(digits, 16) <= 0x10FFFF
                ):
                    value.append(chr(int(digits, 16)))
                    index = closing + 1
                    continue
            elif index + 4 < len(text):
                digits = text[index + 1 : index + 5]
                if all(digit in CSS_HEX_DIGITS for digit in digits):
                    value.append(chr(int(digits, 16)))
                    index += 5
                    continue
        value.append(escapes.get(escaped, escaped))
        index += 1
    return None


def javascript_skip_template(text: str, start: int) -> int:
    """Skip a JavaScript template literal without interpreting its contents."""

    index = start + 1
    while index < len(text):
        if text[index] == "\\":
            index += 2
            continue
        if text[index] == "`":
            return index + 1
        index += 1
    return len(text)


def javascript_regex_can_start(previous: tuple[str, str] | None) -> bool:
    """Approximate whether a slash begins a regex rather than division."""

    if previous is None:
        return True
    kind, value = previous
    if kind == "punct":
        return value in "([{=,:;!&|?+-*%^~<>"
    return kind == "identifier" and value in {
        "await",
        "case",
        "delete",
        "do",
        "else",
        "in",
        "instanceof",
        "of",
        "return",
        "throw",
        "typeof",
        "void",
        "yield",
    }


def javascript_tokens(text: str) -> list[tuple[str, str]]:
    """Tokenize enough JavaScript to identify static module declarations."""

    tokens: list[tuple[str, str]] = []
    index = 0
    while index < len(text):
        character = text[index]
        if character.isspace():
            index += 1
            continue
        if text.startswith("//", index):
            line_end = re.search(r"[\r\n]", text[index + 2 :])
            index = (
                len(text)
                if line_end is None
                else index + 2 + line_end.start()
            )
            continue
        if text.startswith("/*", index):
            closing = text.find("*/", index + 2)
            index = len(text) if closing < 0 else closing + 2
            continue
        if character in {'"', "'"}:
            token = javascript_string_token(text, index)
            if token is None:
                index += 1
                continue
            value, index = token
            tokens.append(("string", value))
            continue
        if character == "`":
            index = javascript_skip_template(text, index)
            tokens.append(("template", ""))
            continue
        if character == "/" and javascript_regex_can_start(
            tokens[-1] if tokens else None
        ):
            index += 1
            inside_class = False
            while index < len(text):
                if text[index] == "\\":
                    index += 2
                    continue
                if text[index] == "[":
                    inside_class = True
                elif text[index] == "]":
                    inside_class = False
                elif text[index] == "/" and not inside_class:
                    index += 1
                    while index < len(text) and (
                        text[index].isalnum() or text[index] in "_$"
                    ):
                        index += 1
                    break
                elif text[index] in "\r\n":
                    break
                index += 1
            tokens.append(("regex", ""))
            continue
        if character.isalpha() or character in "_$":
            end = index + 1
            while end < len(text) and (
                text[end].isalnum() or text[end] in "_$"
            ):
                end += 1
            tokens.append(("identifier", text[index:end]))
            index = end
            continue
        tokens.append(("punct", character))
        index += 1
    return tokens


def javascript_static_module_specifiers(text: str) -> list[str]:
    """Return relative specifiers from static import and re-export declarations."""

    tokens = javascript_tokens(text)
    specifiers: list[str] = []
    for index, token in enumerate(tokens):
        if token not in {("identifier", "import"), ("identifier", "export")}:
            continue
        if index and tokens[index - 1] == ("punct", "."):
            continue
        cursor = index + 1
        if cursor >= len(tokens):
            continue
        if token[1] == "import":
            if tokens[cursor][0] == "string":
                candidate = tokens[cursor][1]
                if candidate.startswith(("./", "../")):
                    specifiers.append(candidate)
                continue
            if tokens[cursor] in {("punct", "("), ("punct", ".")}:
                continue
        depth = 0
        while cursor < len(tokens):
            current = tokens[cursor]
            if current[0] == "punct" and current[1] in "([{":
                depth += 1
            elif current[0] == "punct" and current[1] in ")]}":
                depth = max(0, depth - 1)
            elif depth == 0 and current == ("punct", ";"):
                break
            elif (
                depth == 0
                and cursor > index + 1
                and current
                in {("identifier", "import"), ("identifier", "export")}
            ):
                break
            if depth == 0 and current == ("identifier", "from"):
                cursor += 1
                if cursor < len(tokens) and tokens[cursor][0] == "string":
                    candidate = tokens[cursor][1]
                    if candidate.startswith(("./", "../")):
                        specifiers.append(candidate)
                break
            cursor += 1
    return specifiers


def find_broken_links(root: Path) -> list[str]:
    errors: list[str] = []
    repository_root = root.resolve()
    skill_root = (repository_root / "build-robot-project").resolve()
    fragment_cache: dict[Path, set[str]] = {}
    decoded_text_cache: dict[Path, str | None] = {}

    def display_path(path: Path) -> Path:
        try:
            return path.relative_to(root)
        except ValueError:
            return path.resolve().relative_to(repository_root)

    def read_text_resource(path: Path) -> str | None:
        if path not in decoded_text_cache:
            decoded_text_cache[path] = decode_text_data(path.read_bytes())
            if decoded_text_cache[path] is None:
                errors.append(
                    f"{display_path(path)}: undecodable textual resource"
                )
        return decoded_text_cache[path]

    def stylesheet_context_custom_properties(
        document_path: Path,
        raw_targets: list[str],
        initially_used: set[str],
    ) -> set[str]:
        """Return live custom properties across one document's stylesheet graph."""

        stylesheet_texts: list[str] = []
        pending_stylesheets = [
            (document_path, target) for target in raw_targets
        ]
        seen_stylesheet_paths: set[Path] = set()
        while pending_stylesheets:
            source_path, raw_target = pending_stylesheets.pop()
            target = raw_target.strip("\t\n\f\r ")
            if not target:
                continue
            target = target.translate(URL_INTERNAL_ASCII_WHITESPACE_TRANSLATION)
            target = html_url_for_resolution(target)
            if target.startswith("/") or URI_SCHEME.match(target):
                continue
            try:
                parsed_target = urlsplit(target)
                path_target = unquote_url_path(parsed_target.path)
                if not path_target or "\x00" in path_target:
                    continue
                lexical_path = Path(
                    os.path.normpath(source_path.parent / path_target)
                )
                resolved = lexical_path.resolve()
            except (OSError, ValueError):
                continue
            if (
                resolved in seen_stylesheet_paths
                or not resolved.is_relative_to(repository_root)
                or not resolved.is_file()
            ):
                continue
            seen_stylesheet_paths.add(resolved)
            stylesheet_text = read_text_resource(resolved)
            if stylesheet_text is None:
                continue
            stylesheet_texts.append(stylesheet_text)
            imported_targets: list[str] = []
            css_resource_references(
                stylesheet_text, imported_targets=imported_targets
            )
            pending_stylesheets.extend(
                (lexical_path, imported_target)
                for imported_target in imported_targets
            )
        return css_used_custom_properties(
            stylesheet_texts, initially_used=initially_used
        )

    seen_stylesheets: set[tuple[Path, Path, Path]] = set()
    seen_html_documents: set[tuple[Path, Path]] = set()
    seen_svg_documents: set[tuple[Path, Path]] = set()
    seen_module_scripts: set[tuple[Path, Path]] = set()
    stylesheet_custom_property_usage: dict[Path, set[str]] = {}
    for path in markdown_files(root):
        text = read_text_resource(path)
        if text is None:
            continue
        for fragment_target in html_srcdoc_fragment_errors(text):
            errors.append(
                f"{path.relative_to(root)}: broken srcdoc fragment "
                f"{fragment_target!r}"
            )
        stylesheet_targets: list[str] = []
        embedded_document_targets: list[str] = []
        module_script_targets: list[str] = []
        document_used_custom_properties: set[str] = set()
        link_targets = markdown_link_targets(
            text,
            stylesheet_targets=stylesheet_targets,
            embedded_document_targets=embedded_document_targets,
            module_script_targets=module_script_targets,
            used_custom_property_names=document_used_custom_properties,
        )
        stylesheet_custom_property_usage[path] = (
            stylesheet_context_custom_properties(
                path,
                stylesheet_targets,
                document_used_custom_properties,
            )
        )
        stylesheet_target_set = set(stylesheet_targets)
        embedded_document_target_set = set(embedded_document_targets)
        module_script_target_set = set(module_script_targets)
        pending_targets = [
            (
                path,
                raw_target,
                is_markdown,
                requires_file,
                raw_target in stylesheet_target_set,
                raw_target in embedded_document_target_set,
                raw_target in module_script_target_set,
                path,
            )
            for raw_target, is_markdown, requires_file in link_targets
        ]
        for (
            source_path,
            raw_target,
            is_markdown,
            requires_file,
            scan_stylesheet,
            scan_embedded_document,
            scan_module_script,
            fragment_context_path,
        ) in pending_targets:
            target = raw_target.strip("\t\n\f\r ")
            if not target:
                if requires_file:
                    errors.append(
                        f"{display_path(source_path)}: resource target has no file path "
                        f"{raw_target!r}"
                    )
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
                target = target.translate(URL_INTERNAL_ASCII_WHITESPACE_TRANSLATION)
                target = html_url_for_resolution(target)
            if not target:
                if requires_file:
                    errors.append(
                        f"{display_path(source_path)}: resource target has no file path "
                        f"{raw_target!r}"
                    )
                continue
            if target.startswith("/") or URI_SCHEME.match(target):
                continue
            parsed_target = urlsplit(target)
            path_target = unquote_url_path(parsed_target.path)
            fragment = url_element_fragment(unquote(parsed_target.fragment))
            if requires_file and not path_target and not parsed_target.query:
                errors.append(
                    f"{display_path(source_path)}: resource target has no file path "
                    f"{raw_target!r}"
                )
                continue
            if "\x00" in path_target:
                errors.append(
                    f"{display_path(source_path)}: broken relative link {raw_target!r}"
                )
                continue
            resolution_source_path = (
                fragment_context_path
                if html_same_document_fragment(target) is not None
                else source_path
            )
            try:
                lexical_path = Path(
                    os.path.normpath(
                        resolution_source_path.parent / path_target
                        if path_target
                        else resolution_source_path
                    )
                )
                resolved = lexical_path.resolve()
            except (OSError, ValueError):
                errors.append(
                    f"{display_path(source_path)}: broken relative link {raw_target!r}"
                )
                continue
            if source_path.resolve().is_relative_to(
                skill_root
            ) and not resolved.is_relative_to(skill_root):
                errors.append(
                    f"{display_path(source_path)}: relative link escapes distributable skill "
                    f"directory {raw_target!r}"
                )
                continue
            if not resolved.is_relative_to(repository_root):
                errors.append(
                    f"{display_path(source_path)}: relative link escapes repository checkout "
                    f"{raw_target!r}"
                )
                continue
            if not resolved.exists():
                errors.append(
                    f"{display_path(source_path)}: broken relative link {raw_target!r}"
                )
                continue
            if path_target.endswith("/") and resolved.is_file():
                errors.append(
                    f"{display_path(source_path)}: broken relative link {raw_target!r}"
                )
                continue
            if requires_file and not resolved.is_file():
                errors.append(
                    f"{display_path(source_path)}: resource target is not a file "
                    f"{raw_target!r}"
                )
                continue
            if (
                scan_stylesheet
                and resolved.is_file()
                and (
                    resolved,
                    lexical_path,
                    fragment_context_path,
                )
                not in seen_stylesheets
            ):
                seen_stylesheets.add(
                    (resolved, lexical_path, fragment_context_path)
                )
                stylesheet_text = read_text_resource(resolved)
                if stylesheet_text is not None:
                    imported_targets: list[str] = []
                    stylesheet_references = css_resource_references(
                        stylesheet_text,
                        used_custom_properties=(
                            stylesheet_custom_property_usage.get(
                                fragment_context_path, set()
                            )
                        ),
                        imported_targets=imported_targets,
                    )
                    imported_target_set = set(imported_targets)
                    pending_targets.extend(
                        (
                            lexical_path,
                            stylesheet_target,
                            False,
                            stylesheet_requires_file,
                            stylesheet_target in imported_target_set,
                            False,
                            False,
                            fragment_context_path,
                        )
                        for stylesheet_target, stylesheet_requires_file
                        in stylesheet_references
                    )
            if (
                (not requires_file or scan_embedded_document)
                and resolved.is_file()
                and resolved.suffix.lower() in HTML_SUFFIXES
                and (resolved, lexical_path) not in seen_html_documents
            ):
                seen_html_documents.add((resolved, lexical_path))
                html_text = read_text_resource(resolved)
                if html_text is not None:
                    suffix = resolved.suffix.lower()
                    if suffix in HTML_TEXT_SUFFIXES:
                        for fragment_target in html_srcdoc_fragment_errors(html_text):
                            errors.append(
                                f"{display_path(lexical_path)}: broken srcdoc fragment "
                                f"{fragment_target!r}"
                            )
                    html_stylesheet_targets: list[str] = []
                    html_document_targets: list[str] = []
                    html_module_script_targets: list[str] = []
                    html_used_custom_properties: set[str] = set()
                    if suffix in XHTML_SUFFIXES:
                        html_targets = xhtml_document_resource_targets(
                            html_text,
                            stylesheet_targets=html_stylesheet_targets,
                            embedded_document_targets=html_document_targets,
                            module_script_targets=html_module_script_targets,
                            used_custom_property_names=(
                                html_used_custom_properties
                            ),
                        )
                    else:
                        html_targets = html_resource_targets(
                            html_text,
                            stylesheet_targets=html_stylesheet_targets,
                            embedded_document_targets=html_document_targets,
                            module_script_targets=html_module_script_targets,
                            used_custom_property_names=(
                                html_used_custom_properties
                            ),
                        )
                    stylesheet_custom_property_usage[lexical_path] = (
                        stylesheet_context_custom_properties(
                            lexical_path,
                            html_stylesheet_targets,
                            html_used_custom_properties,
                        )
                    )
                    html_stylesheet_target_set = set(html_stylesheet_targets)
                    html_document_target_set = set(html_document_targets)
                    html_module_script_target_set = set(
                        html_module_script_targets
                    )
                    pending_targets.extend(
                        (
                            lexical_path,
                            html_target,
                            html_is_markdown,
                            html_requires_file,
                            html_target in html_stylesheet_target_set,
                            html_target in html_document_target_set,
                            html_target in html_module_script_target_set,
                            lexical_path,
                        )
                        for html_target, html_is_markdown, html_requires_file
                        in html_targets
                    )
            if (
                (not requires_file or scan_embedded_document)
                and resolved.is_file()
                and resolved.suffix.lower() in SVG_SUFFIXES
                and (resolved, lexical_path) not in seen_svg_documents
            ):
                seen_svg_documents.add((resolved, lexical_path))
                svg_text = read_text_resource(resolved)
                if svg_text is not None:
                    svg_stylesheet_targets: list[str] = []
                    svg_document_targets: list[str] = []
                    svg_module_script_targets: list[str] = []
                    svg_used_custom_properties: set[str] = set()
                    svg_targets = svg_document_resource_targets(
                        svg_text,
                        stylesheet_targets=svg_stylesheet_targets,
                        embedded_document_targets=svg_document_targets,
                        module_script_targets=svg_module_script_targets,
                        used_custom_property_names=svg_used_custom_properties,
                    )
                    stylesheet_custom_property_usage[lexical_path] = (
                        stylesheet_context_custom_properties(
                            lexical_path,
                            svg_stylesheet_targets,
                            svg_used_custom_properties,
                        )
                    )
                    svg_stylesheet_target_set = set(svg_stylesheet_targets)
                    svg_document_target_set = set(svg_document_targets)
                    svg_module_script_target_set = set(
                        svg_module_script_targets
                    )
                    pending_targets.extend(
                        (
                            lexical_path,
                            svg_target,
                            svg_is_markdown,
                            svg_requires_file,
                            svg_target in svg_stylesheet_target_set,
                            svg_target in svg_document_target_set,
                            svg_target in svg_module_script_target_set,
                            lexical_path,
                        )
                        for svg_target, svg_is_markdown, svg_requires_file
                        in svg_targets
                    )
            if (
                scan_module_script
                and resolved.is_file()
                and (resolved, lexical_path) not in seen_module_scripts
            ):
                seen_module_scripts.add((resolved, lexical_path))
                module_text = read_text_resource(resolved)
                if module_text is not None:
                    pending_targets.extend(
                        (
                            lexical_path,
                            module_target,
                            False,
                            True,
                            False,
                            False,
                            True,
                            lexical_path,
                        )
                        for module_target in javascript_static_module_specifiers(
                            module_text
                        )
                    )
            if fragment and resolved.is_file():
                suffix = resolved.suffix.lower()
                fragment_kind: str | None = None
                fragment_loader: Callable[[str], set[str]] | None = None
                if suffix in MARKDOWN_SUFFIXES:
                    fragment_kind = "Markdown"
                    fragment_loader = markdown_heading_fragments
                elif suffix in HTML_TEXT_SUFFIXES:
                    fragment_kind = "HTML"
                    fragment_loader = html_document_fragments
                elif suffix in XHTML_SUFFIXES:
                    fragment_kind = "XHTML"
                    fragment_loader = xhtml_document_fragments
                elif suffix in SVG_SUFFIXES:
                    fragment_kind = "SVG"
                    fragment_loader = svg_document_fragments
                if fragment_loader is None:
                    continue
                if (
                    suffix in (MARKDOWN_SUFFIXES | HTML_SUFFIXES)
                    and html_fragment_is_special_top(fragment)
                ):
                    continue
                if (
                    suffix in SVG_SUFFIXES
                    and svg_fragment_is_view_specification(fragment)
                ):
                    continue
                if resolved not in fragment_cache:
                    resolved_text = read_text_resource(resolved)
                    if resolved_text is None:
                        continue
                    fragment_cache[resolved] = fragment_loader(resolved_text)
                if fragment not in fragment_cache[resolved]:
                    errors.append(
                        f"{display_path(source_path)}: broken {fragment_kind} fragment "
                        f"#{fragment!s} in {raw_target!r}"
                    )
    return errors


def remote_uri_spans(text: str) -> list[tuple[int, int]]:
    """Return spans for authority-based non-file URIs in portable text."""

    spans: list[tuple[int, int]] = []
    for match in URI_SPAN.finditer(text):
        try:
            parsed = urlsplit(match.group(0))
        except ValueError:
            continue
        if parsed.netloc and parsed.scheme.casefold() != "file":
            spans.append(match.span())
    return spans


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
        if (
            path.suffix.lower() not in PORTABLE_TEXT_SUFFIXES
            and data_looks_binary(data)
        ):
            continue
        text = decode_text_data(data)
        if text is None:
            if path.suffix.lower() in PORTABLE_TEXT_SUFFIXES:
                errors.append(
                    f"{path.relative_to(skill_root)}: undecodable textual resource"
                )
            continue
        uri_spans = remote_uri_spans(text)
        for label, pattern in PORTABILITY_PATTERNS.items():
            for match in pattern.finditer(text):
                if label.startswith("machine-specific ") and any(
                    start <= match.start() < end for start, end in uri_spans
                ):
                    continue
                line = text.count("\n", 0, match.start()) + 1
                errors.append(
                    f"{path.relative_to(skill_root)}:{line}: {label} in portable core"
                )
                break
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
            line_count = len(markdown_splitlines(skill_text))
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

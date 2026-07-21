from __future__ import annotations

import html
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

import validate_repository as validator  # noqa: E402


class FrontmatterTests(unittest.TestCase):
    def test_parses_required_scalar_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "SKILL.md"
            path.write_text(
                "---\nname: example-skill\ndescription: Use for an example.\n---\n\n# Example\n",
                encoding="utf-8",
            )
            data, body, errors = validator.parse_frontmatter(path)
            self.assertEqual([], errors)
            self.assertEqual("example-skill", data["name"])
            self.assertIn("# Example", body)

    def test_rejects_text_before_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "SKILL.md"
            path.write_text("# Heading\n---\nname: bad\n---\n", encoding="utf-8")
            _, _, errors = validator.parse_frontmatter(path)
            self.assertTrue(errors)

    def test_reports_invalid_utf8_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "SKILL.md"
            path.write_bytes(b"\xff")
            _, _, errors = validator.parse_frontmatter(path)
            self.assertEqual(1, len(errors))
            self.assertIn("valid UTF-8", errors[0])


class LinkTests(unittest.TestCase):
    def test_reports_missing_relative_link(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("[missing](docs/missing.md)\n", encoding="utf-8")
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))

    def test_accepts_existing_relative_link_and_external_url(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "target.md").write_text("ok\n", encoding="utf-8")
            (root / "README.md").write_text(
                "[target](target.md) [external](https://example.com)\n", encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_accepts_empty_same_document_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("[top]()\n", encoding="utf-8")
            self.assertEqual([], validator.find_broken_links(root))

    def test_rejects_empty_file_resource_destinations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "![bad]()\n<img src=\"\">\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(
                all("resource target has no file path" in error for error in errors)
            )

    def test_decodes_utf16_markdown_before_scanning_links(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[missing](missing.md)\n", encoding="utf-16"
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.md", errors[0])

    def test_decodes_utf16_markdown_fragment_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[details](guide.md#details)\n", encoding="utf-8"
            )
            (root / "guide.md").write_text("# Details\n", encoding="utf-16")
            self.assertEqual([], validator.find_broken_links(root))

    def test_strips_utf8_bom_from_markdown_fragment_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[details](guide.md#details)\n", encoding="utf-8"
            )
            (root / "guide.md").write_bytes(b"\xef\xbb\xbf# Details\n")
            self.assertEqual([], validator.find_broken_links(root))

    def test_accepts_mixed_case_external_uri_scheme(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[external](HTTPS://example.com)\n", encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_accepts_site_root_web_destinations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[issues](/zartosht/zari-robotic-project-skill/issues)\n"
                '<img src="/assets/project-logo.png">\n',
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_accepts_same_file_and_cross_file_heading_fragments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "# Setup\n\n[same](#setup) [cross](guide.md#details)\n", encoding="utf-8"
            )
            (root / "guide.md").write_text("# Details\n", encoding="utf-8")
            self.assertEqual([], validator.find_broken_links(root))

    def test_strips_balanced_inline_destination_from_heading_fragment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            docs = root / "docs"
            docs.mkdir()
            (docs / "(legacy).md").write_text("legacy\n", encoding="utf-8")
            (root / "README.md").write_text(
                "# [API](docs/(legacy).md)\n"
                "[rendered](#api)\n"
                "[stale](#apimd)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("#apimd", errors[0])

    def test_strips_nested_image_destination_from_linked_heading(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "badge.svg").write_text("<svg></svg>\n", encoding="utf-8")
            (root / "README.md").write_text(
                "# [![Build](badge.svg)](README.md)\n\n"
                "[section](#build)\n",
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_preserves_literal_underscores_in_heading_fragments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "# motor_driver\n"
                "# Motor _controller_\n"
                "[underscore](#motor_driver)\n"
                "[emphasis](#motor-controller)\n"
                "[wrong](#motordriver)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("#motordriver", errors[0])

    def test_strips_triple_underscore_emphasis_from_heading_fragments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "# ___foo___\n"
                "[rendered](#foo)\n"
                "[stale](#_foo_)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("#_foo_", errors[0])

    def test_preserves_unicode_combining_marks_in_heading_fragments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "# नमस्ते\n"
                "[devanagari](#नमस्ते)\n"
                "[truncated-devanagari](#नमसत)\n"
                "# cafe\u0301\n"
                "[decomposed](#cafe%CC%81)\n"
                "[truncated-decomposed](#cafe)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(any("#नमसत" in error for error in errors))
            self.assertTrue(any("#cafe" in error for error in errors))

    def test_strips_complete_inline_html_from_heading_fragments(self) -> None:
        headings = (
            "hello <!-- a > b --> world",
            'hello <span title="a > b"> world',
        )
        for heading in headings:
            with self.subTest(heading=heading), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "README.md").write_text(
                    f"# {heading}\n[rendered](#hello--world)\n", encoding="utf-8"
                )
                self.assertEqual([], validator.find_broken_links(root))

    def test_decodes_entities_before_generating_heading_fragments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "# A &amp; B\n"
                "[rendered](#a--b)\n"
                "[wrong](#a-amp-b)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("#a-amp-b", errors[0])

    def test_preserves_whitespace_around_filtered_heading_characters(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "# 🚀 Features\n"
                "# Features 🚀\n"
                "[leading](#-features)\n"
                "[trailing](#features-)\n"
                "[stale](#features)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("#features", errors[0])

    def test_preserves_visible_autolinks_in_heading_fragments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "# See <https://example.com>\n"
                "[rendered](#see-httpsexamplecom)\n"
                "[wrong](#see)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertTrue(errors[0].endswith("in '#see'"))

    def test_accumulates_multiline_setext_heading_fragments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "First line\n"
                "second line\n"
                "-----------\n"
                "[rendered](#first-line-second-line)\n"
                "[wrong](#second-line)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("#second-line", errors[0])

    def test_excludes_reference_definition_from_setext_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "guide.md").write_text("guide\n", encoding="utf-8")
            (root / "README.md").write_text(
                "[docs]: guide.md\n"
                "---\n"
                "[stale](#docs-guidemd)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("#docs-guidemd", errors[0])

    def test_excludes_footnote_definition_from_setext_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[^1]: note\n"
                "---\n"
                "[stale](#1-note)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("#1-note", errors[0])

    def test_strips_reference_style_markup_from_heading_fragments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "guide.md").write_text("guide\n", encoding="utf-8")
            (root / "diagram.png").write_bytes(b"diagram")
            (root / "README.md").write_text(
                "# [Setup][docs]\n"
                "# ![Robot][image]\n"
                "[docs]: guide.md\n"
                "[image]: diagram.png\n"
                "[rendered](#setup)\n"
                "[rendered-image](#robot)\n"
                "[wrong](#setupdocs)\n"
                "[wrong-image](#robotimage)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(any("#setupdocs" in error for error in errors))
            self.assertTrue(any("#robotimage" in error for error in errors))

    def test_preserves_unresolved_reference_markup_in_heading_fragments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "# [Setup][missing]\n"
                "[rendered](#setupmissing)\n"
                "[stale](#setup)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("#setup", errors[0])

    def test_accepts_headings_inside_markdown_containers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "> # Quoted heading\n"
                "> Quoted setext\n"
                "> --------------\n"
                "- # Listed heading\n"
                "> - # Nested heading\n"
                "[quoted](#quoted-heading)\n"
                "[setext](#quoted-setext)\n"
                "[listed](#listed-heading)\n"
                "[nested](#nested-heading)\n",
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_does_not_treat_non_one_list_marker_as_paragraph_interrupt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "paragraph\n"
                "2. # phantom\n\n"
                "2. # Real\n"
                "[real](#real)\n"
                "[stale](#phantom)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("#phantom", errors[0])

    def test_accepts_local_links_with_queries_and_fragments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[source](guide.md?plain=1) [details](guide.md?plain=1#details)\n",
                encoding="utf-8",
            )
            (root / "guide.md").write_text("# Details\n", encoding="utf-8")
            self.assertEqual([], validator.find_broken_links(root))

    def test_accepts_globally_disambiguated_heading_slug(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "# Foo\n\n# Foo-1\n\n# Foo\n\n[third](#foo-2)\n", encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_disambiguates_many_interleaved_heading_slugs_quickly(self) -> None:
        text = "".join(
            f"# foo-{index}\n# foo\n" for index in range(1, 6_001)
        )
        started = time.perf_counter()
        fragments = validator.markdown_heading_fragments(text)
        elapsed = time.perf_counter() - started
        self.assertIn("foo-6001", fragments)
        self.assertLess(elapsed, 2.0)

    def test_reuses_inline_context_for_many_footnote_definitions(self) -> None:
        text = "".join(f"[^note-{index}]: value\n" for index in range(400))
        with mock.patch.object(
            validator,
            "markdown_inline_block_context",
            wraps=validator.markdown_inline_block_context,
        ) as inline_context:
            validator.markdown_heading_fragments(text)
        self.assertLess(inline_context.call_count, 20)

    def test_reports_stale_same_file_and_cross_file_fragments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "# Setup\n\n[same](#old-setup) [cross](guide.md#old-details)\n",
                encoding="utf-8",
            )
            (root / "guide.md").write_text("# Details\n", encoding="utf-8")
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(all("broken Markdown fragment" in error for error in errors))

    def test_does_not_generate_heading_fragments_from_yaml_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "---\n"
                "title: Hello World\n"
                'preview: <a id="frontmatter-anchor" href="missing.md">\n'
                "---\n\n"
                "[title](#title-hello-world)\n"
                "[preview](#frontmatter-anchor)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(all("broken Markdown fragment" in error for error in errors))

    def test_masks_nested_yaml_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "---\n"
                "aliases:\n"
                '  - "[guide](missing.md)"\n'
                "---\n\n"
                "# Real heading\n",
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_does_not_mask_indented_frontmatter_delimiter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "    ---\n"
                "title: [bad](missing.md)\n"
                "---\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.md", errors[0])

    def test_keeps_heading_between_thematic_breaks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "---\n# Real heading\n---\n[go](#real-heading)\n",
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_excludes_lazy_blockquote_text_from_root_setext_fragments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "> foo\nbar\n---\n[bad](#bar)\n", encoding="utf-8"
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("#bar", errors[0])

    def test_scans_links_between_thematic_breaks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "---\nintro text\n[guide](missing.md)\n---\n", encoding="utf-8"
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.md", errors[0])

    def test_accepts_angle_bracketed_destination_with_spaces(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = root / "assets"
            assets.mkdir()
            (assets / "power path.png").write_bytes(b"diagram")
            (root / "README.md").write_text(
                "[diagram](<assets/power path.png>)\n", encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_preserves_leading_space_in_angle_bracketed_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "guide.md").write_text("wrong target\n", encoding="utf-8")
            (root / "README.md").write_text(
                "[guide](< guide.md>)\n", encoding="utf-8"
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("< guide.md>", errors[0])

            (root / " guide.md").write_text("rendered target\n", encoding="utf-8")
            self.assertEqual([], validator.find_broken_links(root))

    def test_preserves_tab_in_angle_bracketed_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "guide.md").write_text("wrong target\n", encoding="utf-8")
            (root / "README.md").write_text(
                "[guide](<guide\t.md>)\n", encoding="utf-8"
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn(r"<guide\t.md>", errors[0])

            (root / "guide\t.md").write_text("rendered target\n", encoding="utf-8")
            self.assertEqual([], validator.find_broken_links(root))

    def test_reports_html_looking_angle_bracketed_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[guide](<missing file.md>)\n", encoding="utf-8"
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing file.md", errors[0])

    def test_does_not_parse_html_attributes_inside_angle_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "object data=asset.bin").write_text("guide\n", encoding="utf-8")
            (root / "README.md").write_text(
                "[guide](<object data=asset.bin>)\n", encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_accepts_escaped_closer_in_angle_bracketed_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            docs = root / "docs"
            docs.mkdir()
            (docs / "a>b.md").write_text("guide\n", encoding="utf-8")
            (root / "README.md").write_text(
                "[guide](<docs/a\\>b.md>)\n", encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_ignores_angle_bracketed_destination_with_escaped_line_ending(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[guide](<missing\\\nfile.md>)\n", encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_accepts_tab_separator_before_link_title(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "guide.md").write_text("# Guide\n", encoding="utf-8")
            (root / "README.md").write_text(
                '[guide](guide.md\t"Guide")\n', encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_reports_missing_destination_before_link_title_whitespace(self) -> None:
        separators = ("\t", "\n", "\r\n")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for separator in separators:
                with self.subTest(separator=repr(separator)):
                    (root / "README.md").write_text(
                        f'[guide](missing.md{separator}"Guide")\n', encoding="utf-8"
                    )
                    errors = validator.find_broken_links(root)
                    self.assertEqual(1, len(errors))
                    self.assertIn("missing.md", errors[0])

    def test_ignores_inline_construct_with_invalid_bare_whitespace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[example](missing file.md)\n", encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_ignores_inline_link_crossing_blank_line(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for blank_line in ("\n\n", "\r\n\r\n"):
                with self.subTest(blank_line=repr(blank_line)):
                    (root / "README.md").write_text(
                        f"[example](missing.md{blank_line})\n", encoding="utf-8"
                    )
                    self.assertEqual([], validator.find_broken_links(root))

    def test_ignores_link_label_crossing_blank_line(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[example\n\ntext](missing.md)\n", encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_ignores_link_label_crossing_block_boundary(self) -> None:
        block_starts = ("# heading", "- item", "> quote", "```", "<!-- block")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for block_start in block_starts:
                with self.subTest(block_start=block_start):
                    (root / "README.md").write_text(
                        f"[guide\n{block_start}](missing.md)\n", encoding="utf-8"
                    )
                    self.assertEqual([], validator.find_broken_links(root))
            (root / "README.md").write_text(
                "[guide\ncontinuation](missing.md)\n", encoding="utf-8"
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.md", errors[0])

    def test_ignores_link_label_crossing_empty_atx_heading(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[guide\n#\n](missing.md)\n", encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_ignores_link_label_crossing_setext_heading_underline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[guide\n===\n](missing.md)\n", encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_scans_link_label_across_empty_unordered_markers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for marker in ("*", "+", "*   ", "+   "):
                with self.subTest(marker=repr(marker)):
                    (root / "README.md").write_text(
                        f"[guide\n{marker}\n](missing.md)\n", encoding="utf-8"
                    )
                    errors = validator.find_broken_links(root)
                    self.assertEqual(1, len(errors))
                    self.assertIn("missing.md", errors[0])

    def test_scans_link_label_across_empty_ordered_markers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for marker in ("1.", "1)", "1.   ", "1)   "):
                with self.subTest(marker=repr(marker)):
                    (root / "README.md").write_text(
                        f"[guide\n{marker}\n](missing.md)\n", encoding="utf-8"
                    )
                    errors = validator.find_broken_links(root)
                    self.assertEqual(1, len(errors))
                    self.assertIn("missing.md", errors[0])

    def test_scans_link_label_across_lazy_blockquote_continuation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "> [guide\ncontinued](missing.md)\n", encoding="utf-8"
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.md", errors[0])

    def test_accepts_destination_with_balanced_parentheses(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = root / "assets"
            assets.mkdir()
            (assets / "diagram(v2).png").write_bytes(b"diagram")
            (root / "README.md").write_text(
                "[diagram](assets/diagram(v2).png)\n", encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_ignores_bare_destination_with_backslash_before_space(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[guide](missing\\ file.md)\n", encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_ignores_bare_destination_with_ascii_control_character(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[guide](missing\x01.md)\n", encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_accepts_backslash_escaped_punctuation_in_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "asset(v2).md").write_text("asset\n", encoding="utf-8")
            (root / "README.md").write_text(
                "[asset](asset\\(v2\\).md)\n", encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_reports_escaped_openers_in_missing_destinations(self) -> None:
        destinations = ("missing\\[file.md", "missing\\<file.md")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for destination in destinations:
                with self.subTest(destination=destination):
                    (root / "README.md").write_text(
                        f"[guide]({destination})\n", encoding="utf-8"
                    )
                    errors = validator.find_broken_links(root)
                    self.assertEqual(1, len(errors))
                    self.assertIn("broken relative link", errors[0])
                    self.assertIn("missing", errors[0])

    def test_reports_missing_reference_style_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[guide][setup]\n\n[setup]: references/missing.md\n", encoding="utf-8"
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("references/missing.md", errors[0])

    def test_accepts_generated_gfm_footnote_fragment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "Use[^1].\n\n[^1]: Note\n\n[footnote](#user-content-fn-1)\n",
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_scans_indented_blocks_in_referenced_footnotes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "Reference[^note].\n\n"
                "[^note]: First paragraph\n\n"
                "    ![bad](missing.png)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.png", errors[0])

    def test_rejects_footnote_fragment_for_unused_definition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[^unused]: Note\n\n"
                "[stale](#user-content-fn-unused)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("#user-content-fn-unused", errors[0])

    def test_accepts_generated_gfm_footnote_reference_fragment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "Note[^1].\n\n"
                "[^1]: Footnote text\n\n"
                "[back](#user-content-fnref-1)\n",
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_ignores_footnote_reference_text_inside_inline_code(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "`[^1]`\n\n"
                "[^1]: Footnote text\n\n"
                "[stale](#user-content-fnref-1)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("#user-content-fnref-1", errors[0])

    def test_stops_code_spans_at_markdown_block_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "before `\n"
                "- [guide](missing.md)\n"
                "` after\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.md", errors[0])

    def test_ignores_footnote_reference_text_inside_link_title(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '[outer](README.md "[^1]")\n\n'
                "[^1]: Footnote text\n\n"
                "[stale](#user-content-fnref-1)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("#user-content-fnref-1", errors[0])

    def test_ignores_footnote_reference_text_inside_image_description(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "outer.png").write_bytes(b"image")
            (root / "README.md").write_text(
                "![alt[^1]](outer.png)\n\n"
                "[^1]: Footnote text\n\n"
                "[stale](#user-content-fnref-1)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("#user-content-fnref-1", errors[0])

    def test_ignores_footnote_definition_inside_code_fence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "```markdown\n"
                "[^1]: Literal example\n"
                "```\n\n"
                "[footnote](#user-content-fn-1)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("#user-content-fn-1", errors[0])

    def test_reports_shortcut_reference_before_paragraph_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[docs]\n\n[docs]: missing.md\n", encoding="utf-8"
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.md", errors[0])

    def test_reports_multiline_reference_definition_label(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[guide][foo bar]\n\n[foo\nbar]: missing.md\n", encoding="utf-8"
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.md", errors[0])

    def test_ignores_multiline_reference_definition_across_container_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[foo\n- bar]: missing.md\n\n[x][foo bar]\n", encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_reports_reference_label_with_escaped_closing_bracket(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[guide][a\\]]\n\n[a\\]]: missing.md\n", encoding="utf-8"
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.md", errors[0])

    def test_rejects_unescaped_opening_bracket_in_reference_label(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[a[b]: README.md\n"
                "---\n"
                "[heading](#ab-readmemd)\n",
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

            (root / "README.md").write_text(
                "[guide][a\\[]\n\n[a\\[]: missing.md\n", encoding="utf-8"
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.md", errors[0])

    def test_reports_reference_definitions_inside_markdown_containers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "> [quoted]: references/quoted-missing.md\n"
                "- [listed]: references/listed-missing.md\n"
                "[one][quoted] [two][listed]\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(any("quoted-missing.md" in error for error in errors))
            self.assertTrue(any("listed-missing.md" in error for error in errors))

    def test_reports_reference_definition_in_nested_list_continuation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "- outer\n"
                "    - inner\n\n"
                "      [r]: missing.md\n"
                "      [x][r]\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.md", errors[0])

    def test_reports_reference_destination_continued_on_next_line(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[guide][docs]\n\n"
                "[docs]:\n"
                "  references/missing.md\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("references/missing.md", errors[0])

    def test_reports_unindented_reference_destination_on_next_line(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[docs]:\nmissing.md\n\n[guide][docs]\n", encoding="utf-8"
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.md", errors[0])

    def test_reports_reference_with_multiline_title(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '[old]: missing.md "first\n  second"\n\n[guide][old]\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.md", errors[0])

    def test_ignores_reference_with_unbalanced_bare_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[old]: missing(foo.md\n\n[guide][old]\n", encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_ignores_reference_with_unclosed_angle_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[r]: <missing.md\n[x][r]\n", encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_ignores_reference_with_non_punctuation_escape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[r]: missing\\ file.md\n[x][r]\n", encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_reports_reference_destination_with_literal_backslash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[x][r]\n\n[r]: missing\\file.md\n", encoding="utf-8"
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing\\\\file.md", errors[0])

    def test_ignores_reference_label_longer_than_commonmark_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            valid_label = "a" * 999
            overlong_label = "b" * 1000
            (root / "README.md").write_text(
                f"[valid][{valid_label}]\n"
                f"[literal][{overlong_label}]\n\n"
                f"[{valid_label}]: missing.md\n"
                f"[{overlong_label}]: ignored-missing.md\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.md", errors[0])

    def test_ignores_overlong_reference_usage_label_before_normalization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[guide][" + (" " * 999) + "a]\n\n[a]: missing.md\n",
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_preserves_non_commonmark_whitespace_in_reference_labels(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[foo bar]: missing.md\n[x][foo\u00a0bar]\n",
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_ignores_unused_and_duplicate_reference_definitions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "target.md").write_text("target\n", encoding="utf-8")
            (root / "README.md").write_text(
                "[guide][docs]\n\n"
                "[docs]: target.md\n"
                "[unused]: unused-missing.md\n"
                "[docs]: duplicate-missing.md\n",
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_ignores_inline_link_markup_in_reference_definition_title(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '[guide][foo]\n\n[foo]: README.md "[example](missing.md)"\n',
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_ignores_html_resource_in_reference_definition_title(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '[guide][foo]\n\n[foo]: README.md "<img src=missing.png>"\n',
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_uses_first_duplicate_reference_definition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "target.md").write_text("target\n", encoding="utf-8")
            (root / "README.md").write_text(
                "[guide][docs]\n\n"
                "[docs]: first-missing.md\n"
                "[docs]: target.md\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("first-missing.md", errors[0])

    def test_reports_missing_outer_link_around_image(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = root / "assets"
            assets.mkdir()
            (assets / "diagram.png").write_bytes(b"diagram")
            (root / "README.md").write_text(
                "[![diagram](assets/diagram.png)](references/missing.md)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("references/missing.md", errors[0])

    def test_ignores_link_target_nested_inside_image_description(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "image.png").write_bytes(b"image")
            (root / "README.md").write_text(
                "![alt [guide](missing.md)](image.png)\n", encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_handles_deeply_nested_link_labels_without_recursion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = "[" * 1000 + "x" + "]" * 1000
            (root / "README.md").write_text(
                f"{nested}(README.md)\n", encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_parses_deeply_nested_labels_once_per_inline_block(self) -> None:
        nested = "[" * 4000 + "x" + "]" * 4000
        text = f"{nested}(README.md)\n"
        with mock.patch.object(
            validator,
            "markdown_inline_block_end",
            wraps=validator.markdown_inline_block_end,
        ) as inline_block_end:
            self.assertEqual(
                [("README.md", True, False)],
                validator.markdown_link_targets(text),
            )
        self.assertLess(inline_block_end.call_count, 10)

    def test_indexes_many_link_paragraphs_in_one_container_pass(self) -> None:
        text = "".join(
            f"[guide-{index}](README.md)\n\n" for index in range(2_000)
        )
        with mock.patch.object(
            validator,
            "markdown_container_lines",
            wraps=validator.markdown_container_lines,
        ) as container_lines:
            pairs = validator.markdown_label_pairs(text)
        self.assertEqual(2_000, len(pairs))
        self.assertEqual(1, container_lines.call_count)

    def test_scans_many_image_ranges_in_a_single_pass(self) -> None:
        text = "![a](image.png) [b](README.md)\n" * 200
        label_pairs = validator.markdown_label_pairs(text)
        ranges = validator.markdown_active_image_label_ranges(
            text, set(), label_pairs
        )

        class CountingRanges(list[tuple[int, int]]):
            iterations = 0

            def __iter__(self):
                self.iterations += 1
                return super().__iter__()

        counted_ranges = CountingRanges(ranges)
        with mock.patch.object(
            validator,
            "markdown_active_image_label_ranges",
            return_value=counted_ranges,
        ), mock.patch.object(
            validator,
            "markdown_paragraph_end",
            wraps=validator.markdown_paragraph_end,
        ) as paragraph_end:
            targets = validator.markdown_link_targets(text)
        self.assertEqual(400, len(targets))
        self.assertLess(counted_ranges.iterations, 10)
        self.assertLess(paragraph_end.call_count, 10)

    def test_indexes_reference_definition_lines_with_binary_search(self) -> None:
        text = "".join(f"[ref-{index}]: README.md\n" for index in range(500))
        with mock.patch.object(
            validator, "bisect_left", wraps=validator.bisect_left
        ) as bisect:
            definitions = validator.markdown_reference_definitions(text)
        self.assertEqual(500, len(definitions))
        self.assertEqual(1000, bisect.call_count)

    def test_rejects_markdown_image_targeting_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "assets").mkdir()
            (root / "README.md").write_text(
                "![diagram](assets/)\n", encoding="utf-8"
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("resource target is not a file", errors[0])

    def test_rejects_reference_image_targeting_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "assets").mkdir()
            (root / "README.md").write_text(
                "![diagram][asset]\n\n[asset]: assets/\n", encoding="utf-8"
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("resource target is not a file", errors[0])

    def test_rejects_directory_form_url_that_resolves_to_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[bad](README.md/)\n"
                "![bad](README.md/)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(all("README.md/" in error for error in errors))

    def test_rejects_empty_reference_image_without_scanning_its_alt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '[r]: <>\n\n![<img src="missing.png">][r]\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("resource target has no file path", errors[0])
            self.assertNotIn("missing.png", errors[0])

    def test_does_not_attach_spaced_reference_label_to_image(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docs").mkdir()
            (root / "README.md").write_text(
                "![alt] [ref]\n\n[ref]: docs\n", encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_scans_common_markdown_filename_variants(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "GUIDE.MD").write_text("[missing](first.md)\n", encoding="utf-8")
            (root / "notes.markdown").write_text("[missing](second.md)\n", encoding="utf-8")
            self.assertEqual(2, len(validator.find_broken_links(root)))

    def test_scans_additional_markdown_filename_variants(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for index, suffix in enumerate(
                (".mdown", ".mkd", ".mkdn", ".mkdown"), start=1
            ):
                (root / f"guide{suffix}").write_text(
                    f"[missing](missing-{index}.md)\n", encoding="utf-8"
                )
            self.assertEqual(4, len(validator.find_broken_links(root)))

    def test_ignores_literal_markdown_link_examples(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "\\[escaped](missing.md)\n"
                "`[inline](missing.md)`\n"
                "```markdown\n[fenced](missing.md)\n```\n"
                "> ```markdown\n> [quoted-fenced](missing.md)\n> ```\n",
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_masks_many_code_spans_quickly(self) -> None:
        text = " ".join("`literal`" for _ in range(8_000))
        started = time.perf_counter()
        masked = validator.markdown_searchable_text(text)
        elapsed = time.perf_counter() - started
        self.assertNotIn("literal", masked)
        self.assertLess(elapsed, 0.75)

    def test_ignores_code_span_closed_by_backslash_prefixed_tick(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "`[guide](missing.md)\\`\n", encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_does_not_pair_code_span_delimiters_across_blank_line(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "`literal\n\n[guide](missing.md)`\n", encoding="utf-8"
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.md", errors[0])

    def test_html_tag_scanner_handles_large_unterminated_input(self) -> None:
        text = "<widget " + ("x" * 10_000)
        self.assertIsNone(validator.MARKDOWN_HTML_TAG.search(text))

    def test_rejects_link_inside_malformed_inline_html_tag(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "<x foo==[guide](missing.md)>\n", encoding="utf-8"
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.md", errors[0])

    def test_rejects_link_after_invalid_backtick_fence_opener(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "``` bad ` info\n[guide](missing.md)\n```\n", encoding="utf-8"
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.md", errors[0])

    def test_rejects_link_after_tab_indented_fence_opener(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                " \t```\n[guide](missing.md)\n```\n", encoding="utf-8"
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.md", errors[0])

    def test_expands_list_marker_tab_when_scoping_fenced_block(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "-\t```\n  [guide](missing.md)\n", encoding="utf-8"
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.md", errors[0])
            (root / "README.md").write_text(
                "-\t```\n    [literal](missing.md)\n", encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_scopes_fenced_code_blocks_to_their_container(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "> ```\n"
                "> code\n"
                "```\n"
                "[literal](missing.md)\n",
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_keeps_nested_marker_text_inside_blockquote_fences(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "> ```\n"
                "> > ```\n"
                "> [literal](missing.md)\n"
                "> ```\n",
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_tracks_interleaved_list_and_blockquote_fence_containers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "- > ```\n"
                "  > [literal](missing.md)\n"
                "  > ```\n",
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_ignores_deactivated_outer_link_opener(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "valid.md").write_text("valid\n", encoding="utf-8")
            (root / "README.md").write_text(
                "[outer [inner](valid.md)](missing.md)\n", encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_reports_link_between_escaped_backticks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "\\`[guide](missing.md)\\`\n", encoding="utf-8"
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.md", errors[0])

    def test_reports_percent_encoded_nul_as_broken_link(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[guide](missing%00.md)\n", encoding="utf-8"
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("broken relative link", errors[0])

    def test_preserves_percent_encoded_path_separators(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docs").mkdir()
            (root / "docs" / "guide.md").write_text("guide\n", encoding="utf-8")
            (root / "README.md").write_text(
                "[guide](docs%2Fguide.md)\n", encoding="utf-8"
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("docs%2Fguide.md", errors[0])

    def test_ignores_indented_markdown_code_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "    [indented](missing.md)\n"
                "\t<img src=missing.png>\n"
                ">     [quoted](missing.md)\n",
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_ignores_indented_code_after_thematic_break(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for thematic_break in ("***", "___"):
                with self.subTest(thematic_break=thematic_break):
                    (root / "README.md").write_text(
                        f"{thematic_break}\n    [guide](missing.md)\n",
                        encoding="utf-8",
                    )
                    self.assertEqual([], validator.find_broken_links(root))

    def test_ignores_tab_indented_blockquote_like_code(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "\t> [guide](missing.md)\n"
                " \t> [second](also-missing.md)\n",
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_ignores_tab_indented_list_marker_as_code(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "\t- [guide](missing.md)\n"
                " \t+ [second](also-missing.md)\n",
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_scans_indented_paragraph_continuation_links(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "paragraph\n"
                "    [rendered](rendered-missing.md)\n"
                "\n"
                "    [code](code-missing.md)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("rendered-missing.md", errors[0])

    def test_distinguishes_list_continuations_from_indented_code(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "10. rendered item\n"
                "    [rendered](rendered-missing.md)\n"
                "-     [code](code-missing.md)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("rendered-missing.md", errors[0])

    def test_scans_list_continuation_links_inside_blockquotes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "> - item\n"
                ">     [guide](missing.md)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.md", errors[0])

    def test_ignores_literal_and_commented_html_anchor_examples(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<a id="real-anchor"></a>\n'
                '`<a id="inline-anchor"></a>`\n'
                '<!-- <a id="commented-anchor"></a> -->\n'
                '[real](#real-anchor)\n'
                '[inline](#inline-anchor)\n'
                '[commented](#commented-anchor)\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(any("#inline-anchor" in error for error in errors))
            self.assertTrue(any("#commented-anchor" in error for error in errors))

    def test_ignores_html_anchors_in_nonrendered_markdown_contexts(self) -> None:
        documents = {
            "inline title": '[outer](README.md "<a id=ghost>")\n',
            "reference title": (
                '[outer][ref]\n\n[ref]: README.md "<a name=ghost>"\n'
            ),
            "image description": "![<a id=ghost>](image.png)\n",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "image.png").write_bytes(b"image")
            for context, document in documents.items():
                with self.subTest(context=context):
                    (root / "README.md").write_text(
                        document + "[stale](#ghost)\n", encoding="utf-8"
                    )
                    errors = validator.find_broken_links(root)
                    self.assertEqual(1, len(errors))
                    self.assertIn("#ghost", errors[0])

    def test_preserves_link_after_escaped_html_comment_opener(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "\\<!-- [guide](missing.md) -->\n", encoding="utf-8"
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.md", errors[0])

    def test_stops_inline_html_comment_at_paragraph_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "text <!--\n\n[guide](missing.md) -->\n", encoding="utf-8"
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.md", errors[0])

    def test_preserves_link_inside_malformed_inline_html_comment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "text <!-- bad -- [guide](missing.md) -->\n", encoding="utf-8"
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.md", errors[0])

    def test_masks_special_inline_html_constructs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "text <? [one](first-missing.md) ?>\n"
                "text <!A [two](second-missing.md)>\n"
                "text <![CDATA[[three](third-missing.md)]]>\n",
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_stops_unclosed_special_html_blocks_when_container_ends(self) -> None:
        openers = ("<!-- unclosed", "<? unclosed", "<!DECLARATION", "<![CDATA[")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for opener in openers:
                with self.subTest(opener=opener):
                    (root / "README.md").write_text(
                        f"> {opener}\n[guide](missing.md)\n", encoding="utf-8"
                    )
                    errors = validator.find_broken_links(root)
                    self.assertEqual(1, len(errors))
                    self.assertIn("missing.md", errors[0])

    def test_excludes_commented_headings_but_keeps_inline_code_headings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "# Use `real`\n"
                "<!--\n"
                "# Removed section\n"
                "Removed setext\n"
                "---------------\n"
                "-->\n"
                "[real](#use-real)\n"
                "[removed](#removed-section)\n"
                "[setext](#removed-setext)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(any("#removed-section" in error for error in errors))
            self.assertTrue(any("#removed-setext" in error for error in errors))

    def test_keeps_html_looking_code_span_text_in_heading_fragments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "# Use `<div>`\n\n[section](#use-div)\n", encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_strips_opening_and_closing_html_tags_from_heading_fragments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "# <span>Foo</span>\n"
                "[rendered](#foo)\n"
                "[stale](#foospan)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("#foospan", errors[0])

    def test_normalizes_code_span_whitespace_in_heading_fragments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "# `foo   bar`\n"
                "[rendered](#foo-bar)\n"
                "[stale](#foo---bar)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("#foo---bar", errors[0])

    def test_validates_rendered_raw_html_targets_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = root / "assets"
            assets.mkdir()
            (root / "guide.md").write_text("guide\n", encoding="utf-8")
            (assets / "diagram v2.png").write_bytes(b"diagram")
            (root / "README.md").write_text(
                '<a href="guide.md">guide</a>\n'
                '<a href="">same page</a>\n'
                '<img src="assets/diagram v2.png">\n'
                '<a href="references/missing.md">missing</a>\n'
                '<img src=assets/missing.png>\n'
                '`<a href="inline-missing.md">`\n'
                '<!-- <img src="commented-missing.png"> -->\n'
                '\\<a href="escaped-missing.md">\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(any("references/missing.md" in error for error in errors))
            self.assertTrue(any("assets/missing.png" in error for error in errors))

    def test_ignores_href_on_elements_that_do_not_use_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<div href="missing-page.md">content</div>\n'
                '<img href="missing-image.md">\n',
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_ignores_duplicate_html_resource_attributes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "exists.png").write_bytes(b"image")
            (root / "README.md").write_text(
                '<img src="exists.png" src="missing.png">\n', encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_validates_html_target_after_quoted_greater_than(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<img alt="a > b" src="missing.png">\n', encoding="utf-8"
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.png", errors[0])

    def test_validates_local_html_srcset_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "small.png").write_bytes(b"small")
            (root / "README.md").write_text(
                '<img srcset="data:image/png;base64,AAAA 1x, small.png 2x, '
                'missing-large.png 3x">\n'
                '<source srcset="missing-wide.png 640w">\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(any("missing-large.png" in error for error in errors))
            self.assertTrue(any("missing-wide.png" in error for error in errors))

    def test_decodes_srcset_entities_before_parsing_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<img srcset="missing.png&#x20;nope">\n', encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_decodes_html_resource_attributes_exactly_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a&amp;.png").write_bytes(b"image")
            (root / "README.md").write_text(
                '<img srcset="a&amp;amp;.png 1x">\n', encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_discards_srcset_candidates_with_invalid_descriptors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "valid.png").write_bytes(b"valid")
            (root / "future.png").write_bytes(b"future")
            (root / "README.md").write_text(
                '<img srcset="missing-a.png nope, missing-b.png 1x 2x, '
                'missing-c.png 10w 20w, missing-d.png 0w, '
                'missing-e.png -1x, missing-f.png 10h, '
                'missing-g.png +1x, missing-h.png 1.x, '
                'valid.png 2x, future.png 100w 50h">\n',
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_preserves_ambiguous_ampersand_in_html_attribute_url(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a&notit;.md").write_text("target\n", encoding="utf-8")
            (root / "README.md").write_text(
                '<a href="a&notit;.md">target</a>\n', encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_normalizes_backslashes_in_raw_html_urls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            docs = root / "docs"
            assets = root / "assets"
            docs.mkdir()
            assets.mkdir()
            (docs / "guide.md").write_text("guide\n", encoding="utf-8")
            (assets / "image.png").write_bytes(b"image")
            (root / "README.md").write_text(
                '<a href="docs\\guide.md">guide</a>\n'
                '<img src="assets\\image.png">\n',
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_caches_paragraph_boundaries_while_scanning_html_tags(self) -> None:
        text = " ".join('<a href="README.md">guide</a>' for _ in range(500))
        with mock.patch.object(
            validator,
            "markdown_paragraph_end",
            wraps=validator.markdown_paragraph_end,
        ) as paragraph_end:
            values = validator.html_attribute_values(
                text,
                validator.MARKDOWN_HTML_HREF_ATTRIBUTES,
                tag_names=validator.MARKDOWN_HTML_HREF_TAGS,
            )
        self.assertEqual(500, len(values))
        self.assertLess(paragraph_end.call_count, 10)

    def test_validates_local_html_object_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<object data="missing.pdf"></object>\n'
                '<div data="ignored.bin"></div>\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.pdf", errors[0])

    def test_treats_resource_link_relations_as_file_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "# Heading\n\n"
                '<link rel="alternate stylesheet" href="#heading">\n'
                '<link rel="icon" href="#heading">\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(
                all("resource target has no file path" in error for error in errors)
            )

    def test_validates_svg_href_resources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<svg><symbol id="present"></symbol>'
                '<image href="missing.png"></image>'
                '<use href="missing.svg#icon"></use>'
                '<use href="#present"></use></svg>\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(any("missing.png" in error for error in errors))
            self.assertTrue(any("missing.svg#icon" in error for error in errors))

    def test_validates_src_only_for_resource_loading_elements(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "image.png").write_bytes(b"image")
            (root / "README.md").write_text(
                '<div src="ignored-div.png"></div>\n'
                '<input type="text" src="ignored-text.png">\n'
                '<input src="ignored-default.png">\n'
                '<input src="image.png" type="image">\n'
                '<input src="missing-image.png" type="image">\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing-image.png", errors[0])

    def test_preserves_resource_tags_inside_pre_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<pre>\n<img src="missing.png">\n</pre>\n', encoding="utf-8"
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.png", errors[0])

    def test_ignores_resource_tags_inside_raw_html_comments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<div>\n<!-- <img src="missing.png"> -->\n</div>\n',
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_ignores_resources_inside_unterminated_raw_html_specials(self) -> None:
        openers = ("<!--", "<?", "<![CDATA[")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for opener in openers:
                with self.subTest(opener=opener):
                    (root / "README.md").write_text(
                        f'<div>\n{opener} <img src="missing.png">\n</div>\n',
                        encoding="utf-8",
                    )
                    self.assertEqual([], validator.find_broken_links(root))

    def test_ignores_resources_inside_template_contents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<template>\n<img src="inert.png">\n</template>\n'
                '<img src="live.png">\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("live.png", errors[0])

    def test_ignores_markup_inside_html_raw_text_element_bodies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for tag_name in ("iframe", "noembed", "noframes", "title", "xmp"):
                with self.subTest(tag_name=tag_name):
                    (root / "README.md").write_text(
                        f'<{tag_name}>\n<img src="missing.png">\n</{tag_name}>\n',
                        encoding="utf-8",
                    )
                    self.assertEqual([], validator.find_broken_links(root))

    def test_ignores_html_resources_inside_image_description(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "outer.png").write_bytes(b"outer")
            (root / "README.md").write_text(
                '![<img src="missing.png">](outer.png)\n', encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_keeps_markdown_link_after_inline_html_crosses_blank_line(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<span title="\n\n[guide](missing.md)">\n', encoding="utf-8"
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.md", errors[0])

    def test_ignores_attribute_like_text_inside_quoted_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "<img alt='src=\"missing.png\"'>\n"
                "<div title='id=\"phantom\"'>\n"
                "\n"
                "[phantom](#phantom)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("#phantom", errors[0])

    def test_ignores_tag_shaped_text_inside_permissive_raw_html_attribute(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<div @="<img src=missing.png>">\n</div>\n',
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_preserves_link_after_comment_marker_in_html_attribute(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                'text <span title="<!--">x</span> [guide](missing.md)\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.md", errors[0])

    def test_accepts_name_fragment_only_from_anchor_elements(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<input name="phantom">\n'
                '<a name="legacy"></a>\n'
                "\n"
                "[phantom](#phantom)\n"
                "[legacy](#legacy)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("#phantom", errors[0])

    def test_rejects_raw_html_src_targeting_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "assets").mkdir()
            (root / "scripts").mkdir()
            (root / "README.md").write_text(
                '<img src="assets/">\n'
                '<script src="scripts/"></script>\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(all("target is not a file" in error for error in errors))

    def test_validates_raw_html_poster_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<video poster="missing.png"></video>\n', encoding="utf-8"
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.png", errors[0])

    def test_validates_iframe_srcdoc_resources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "existing.png").write_bytes(b"image")
            (root / "README.md").write_text(
                '<iframe srcdoc="<!-- <img src=\047commented.png\047> -->'
                '<img src=\047existing.png\047>'
                '<img src=\047missing.png\047>"></iframe>\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.png", errors[0])

    def test_validates_resources_beyond_eight_nested_srcdoc_documents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = '<img src="missing.png">'
            for _ in range(9):
                nested = f'<iframe srcdoc="{html.escape(nested, quote=True)}"></iframe>'
            (root / "README.md").write_text(nested + "\n", encoding="utf-8")
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.png", errors[0])

    def test_iframe_srcdoc_suppresses_src_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<iframe src="missing.html" srcdoc="<p>ok</p>"></iframe>\n',
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_resolves_iframe_srcdoc_resources_against_first_base(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "picture.png").write_bytes(b"image")
            (root / "other").mkdir()
            (root / "other" / "picture.png").write_bytes(b"image")
            (root / "README.md").write_text(
                '<iframe srcdoc="<base href=\047docs/\047>'
                '<base href=\047other/\047>'
                '<img src=\047picture.png\047>"></iframe>\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("docs/picture.png", errors[0])

    def test_validates_inline_style_attribute_resource_urls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<div style="background-image:url(missing.png)"></div>\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.png", errors[0])

    def test_decodes_escaped_css_resource_identifiers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<div style="background:u\\72l(missing.png)"></div>\n'
                "\n"
                '<style>@\\69mport "missing.css";</style>\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(any("missing.png" in error for error in errors))
            self.assertTrue(any("missing.css" in error for error in errors))

    def test_rejects_fragment_only_file_resources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "# Heading\n\n![bad](#heading)\n<img src=\"#heading\">\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(
                all("resource target has no file path" in error for error in errors)
            )

    def test_validates_style_block_resource_urls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "<style>\n"
                "/* url(commented.png) */\n"
                '.example::before { content: "url(string.png)"; }\n'
                "@import url('missing.css');\n"
                '@import "missing-theme.css";\n'
                ".example { background-image: url(missing.png); }\n"
                "</style>\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(3, len(errors))
            self.assertTrue(any("missing.css" in error for error in errors))
            self.assertTrue(any("missing-theme.css" in error for error in errors))
            self.assertTrue(any("missing.png" in error for error in errors))

    def test_decodes_css_escapes_in_resource_urls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "picture.png").write_bytes(b"image")
            (root / "icon.png").write_bytes(b"image")
            (root / "theme.css").write_text("/* theme */\n", encoding="utf-8")
            (root / "README.md").write_text(
                "<style>\n"
                '@import "theme\\2e css";\n'
                ".a { background: url(picture\\2e png); }\n"
                '.b { background: url("icon\\2e png"); }\n'
                "</style>\n",
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_applies_first_document_base_to_raw_html_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "picture.png").write_bytes(b"root image")
            (root / "other").mkdir()
            (root / "other" / "picture.png").write_bytes(b"other image")
            (root / "README.md").write_text(
                '<base href="docs/">\n'
                '<base href="other/">\n'
                '<img src="picture.png">\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("docs/picture.png", errors[0])

            (root / "docs").mkdir()
            (root / "docs" / "picture.png").write_bytes(b"docs image")
            self.assertEqual([], validator.find_broken_links(root))

    def test_validates_base_resolved_meta_refresh_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docs").mkdir()
            (root / "docs" / "existing.md").write_text("existing\n", encoding="utf-8")
            (root / "README.md").write_text(
                '<base href="docs/">\n'
                '<meta http-equiv="refresh" content="0; url=existing.md">\n'
                '<meta http-equiv="REFRESH" content="0; URL=missing.md">\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("docs/missing.md", errors[0])

    def test_validates_form_submission_destinations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<base href="docs/">\n'
                '<form action="missing-form.md">'
                '<button formaction="missing-button.md">Send</button>'
                '<input type="submit" formaction="missing-input.md">'
                '<button type="button" formaction="ignored-button.md">No submit</button>'
                '<input type="text" formaction="ignored-input.md">'
                "</form>\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(3, len(errors))
            self.assertTrue(any("docs/missing-form.md" in error for error in errors))
            self.assertTrue(any("docs/missing-button.md" in error for error in errors))
            self.assertTrue(any("docs/missing-input.md" in error for error in errors))

    def test_validates_fragments_in_local_html_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "page.html").write_text(
                '<div id="present"></div><a name="legacy"></a>\n',
                encoding="utf-8",
            )
            (root / "README.md").write_text(
                "[present](page.html#present) "
                "[legacy](page.html#legacy) "
                "[missing](page.html#missing)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("page.html#missing", errors[0])

    def test_masks_raw_html_block_bodies_but_validates_opening_tag_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "script.js").write_text("script\n", encoding="utf-8")
            (root / "README.md").write_text(
                '<script src="script.js">\n'
                'const example = "[example](missing.md)";\n'
                "# Hidden heading\n"
                "</script>\n"
                "[hidden](#hidden-heading)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("#hidden-heading", errors[0])

    def test_stops_unclosed_raw_html_block_when_container_ends(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "> <script>\n"
                '> const example = "[literal](ignored.md)";\n'
                "[guide](missing.md)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.md", errors[0])

    def test_stops_standard_raw_html_block_when_container_ends(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "> <div>\n"
                "> literal body\n"
                "[guide](missing.md)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.md", errors[0])

    def test_preserves_multiline_standard_raw_html_opening_tag_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "<iframe\n"
                '  src="missing.html">\n'
                "\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.html", errors[0])

    def test_excludes_heading_inside_multiline_html_attribute(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<div\n title="\n# phantom\n">\n\n[stale](#phantom)\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("#phantom", errors[0])

    def test_rejects_link_after_malformed_type_seven_html_opener(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "<x foo=>\n[guide](missing.md)\n", encoding="utf-8"
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.md", errors[0])

    def test_masks_malformed_type_six_raw_html_opening_line(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "<div [guide](missing.md)\n\n", encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_preserves_multiline_raw_html_opening_tag_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "<script\n"
                '  src="missing.js">\n'
                'const example = "[example](ignored-missing.md)";\n'
                "</script>\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.js", errors[0])

    def test_masks_standard_raw_html_block_bodies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "<div>\n"
                "[literal example](missing.md)\n"
                "</div>\n"
                "\n"
                "[rendered](rendered-missing.md)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("rendered-missing.md", errors[0])

    def test_reference_definition_ends_paragraph_before_type_seven_html(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[r]: README.md\n"
                "<custom>\n"
                "[guide](missing.md)\n"
                "</custom>\n\n",
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_validates_html_targets_inside_standard_raw_html_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "<div>\n"
                '<a href="missing.md">missing</a>\n'
                "[literal example](ignored-missing.md)\n"
                "</div>\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.md", errors[0])

    def test_validates_permissive_resource_tags_inside_raw_html_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "<div>\n"
                '<img @click="preview" src="missing.png">\n'
                "</div>\n\n"
                '<script @load="ready" src="missing.js"></script>\n\n'
                'Inline <img @click="preview" src="ignored.png"> text.\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(any("missing.png" in error for error in errors))
            self.assertTrue(any("missing.js" in error for error in errors))

    def test_recognizes_form_feed_separators_in_raw_html_tags(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<div>\n<img\f src="missing.png">\n</div>\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.png", errors[0])

    def test_preserves_non_ascii_whitespace_in_html_resource_urls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "existing.png").write_bytes(b"image")
            (root / "README.md").write_text(
                '<img src="\N{NO-BREAK SPACE}existing.png">\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("existing.png", errors[0])

    def test_handles_cr_only_line_end_after_type_one_html_block(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_bytes(
                b"<script></script>\r[guide](missing.md)\r"
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.md", errors[0])

    def test_ignores_indented_code_after_closed_type_one_html_block(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "<script></script>\n    [guide](missing.md)\n", encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_stops_incomplete_type_one_html_block_at_closer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "<script\n"
                "[literal](ignored.md)\n"
                '<a href="also-ignored.md">\n'
                "</script>\n"
                "[guide](missing.md)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.md", errors[0])

    def test_ignores_link_like_text_inside_inline_link_title(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '[outer](README.md "[inner](missing.md)")\n', encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_ignores_html_resource_inside_inline_link_title(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '[outer](README.md "<img src=missing.png>")\n', encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_stops_multiline_link_label_at_blank_blockquote_line(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "> [guide\n>\n> ](missing.md)\n", encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_stops_inline_link_title_at_blank_line(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '[outer](README.md "title\n\n[inner](missing.md)")\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.md", errors[0])

    def test_ignores_malformed_reference_definition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[guide][old]\n\n[old]: missing.md trailing garbage\n",
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_ignores_reference_definition_interrupting_paragraph(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "paragraph\n[old]: missing.md\n\n[guide][old]\n",
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_accepts_semicolonless_entity_like_filename(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "guide&copy.md").write_text("guide\n", encoding="utf-8")
            (root / "README.md").write_text(
                "[guide](guide&copy.md)\n", encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_rejects_skill_link_that_escapes_distributable_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill_root = root / "build-robot-project"
            skill_root.mkdir()
            (root / "README.md").write_text("repository docs\n", encoding="utf-8")
            (skill_root / "SKILL.md").write_text("[docs](../README.md)\n", encoding="utf-8")
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("escapes distributable skill directory", errors[0])

    def test_rejects_repository_link_that_escapes_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            root = workspace / "repository"
            root.mkdir()
            (workspace / "outside.md").write_text("outside\n", encoding="utf-8")
            (root / "README.md").write_text("[outside](../outside.md)\n", encoding="utf-8")
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("escapes repository checkout", errors[0])


class PortabilityTests(unittest.TestCase):
    def test_detects_client_specific_tool_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "references").mkdir()
            (root / "assets").mkdir()
            (root / "SKILL.md").write_text("Call request_user_input.\n", encoding="utf-8")
            errors = validator.find_portability_violations(root)
            self.assertEqual(1, len(errors))

    def test_accepts_capability_based_instruction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "references").mkdir()
            (root / "assets").mkdir()
            (root / "SKILL.md").write_text(
                "Use the agent's available structured input capability.\n", encoding="utf-8"
            )
            self.assertEqual([], validator.find_portability_violations(root))

    def test_skips_binary_portable_resource(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "references").mkdir()
            assets = root / "assets"
            assets.mkdir()
            (root / "SKILL.md").write_text("Portable instructions.\n", encoding="utf-8")
            (assets / "diagram.png").write_bytes(b"\x89PNG\r\n\x1a\n\xff")
            self.assertEqual([], validator.find_portability_violations(root))

    def test_skips_utf8_decodable_binary_portable_resource(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "SKILL.md").write_text("Portable instructions.\n", encoding="utf-8")
            (root / "model.bin").write_bytes(b"\x00codex\x00")
            self.assertEqual([], validator.find_portability_violations(root))

    def test_scans_bundled_scripts_for_portability_violations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "references").mkdir()
            (root / "assets").mkdir()
            scripts = root / "scripts"
            scripts.mkdir()
            (root / "SKILL.md").write_text("Portable instructions.\n", encoding="utf-8")
            (scripts / "helper.py").write_text("request_user_input()\n", encoding="utf-8")
            errors = validator.find_portability_violations(root)
            self.assertEqual(1, len(errors))
            self.assertIn("scripts/helper.py", errors[0])

    def test_scans_other_distributed_resources_for_portability_violations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            examples = root / "examples"
            examples.mkdir()
            (root / "SKILL.md").write_text("Portable instructions.\n", encoding="utf-8")
            (examples / "usage.md").write_text("Run codex exec.\n", encoding="utf-8")
            errors = validator.find_portability_violations(root)
            self.assertEqual(1, len(errors))
            self.assertIn("examples/usage.md", errors[0])

    def test_excludes_intentional_agent_metadata_from_portability_scan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            agents = root / "agents"
            agents.mkdir()
            (root / "SKILL.md").write_text("Portable instructions.\n", encoding="utf-8")
            (agents / "openai.yaml").write_text("Use Codex metadata.\n", encoding="utf-8")
            self.assertEqual([], validator.find_portability_violations(root))

    def test_scans_utf16_bundled_text_for_portability_violations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "references").mkdir()
            (root / "assets").mkdir()
            scripts = root / "scripts"
            scripts.mkdir()
            (root / "SKILL.md").write_text("Portable instructions.\n", encoding="utf-8")
            (scripts / "helper.ps1").write_text("Run codex exec.\n", encoding="utf-16")
            errors = validator.find_portability_violations(root)
            self.assertEqual(1, len(errors))
            self.assertIn("scripts/helper.ps1", errors[0])

    def test_detects_lowercase_client_cli_identifiers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "references").mkdir()
            (root / "assets").mkdir()
            skill_file = root / "SKILL.md"
            for instruction in ("Run codex exec.\n", "Run claude.\n", "Run gemini skills.\n"):
                with self.subTest(instruction=instruction):
                    skill_file.write_text(instruction, encoding="utf-8")
                    self.assertEqual(1, len(validator.find_portability_violations(root)))

    def test_detects_linux_user_home_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "references").mkdir()
            (root / "assets").mkdir()
            skill_file = root / "SKILL.md"
            for path in (
                "/home/alice/robot-project",
                "/home/alice",
                "/root/robot-project",
                "/root",
            ):
                with self.subTest(path=path):
                    skill_file.write_text(f"Open {path}.\n", encoding="utf-8")
                    errors = validator.find_portability_violations(root)
                    self.assertEqual(1, len(errors))
                    self.assertIn("machine-specific Linux path", errors[0])

    def test_detects_macos_user_home_without_trailing_slash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "references").mkdir()
            (root / "assets").mkdir()
            (root / "SKILL.md").write_text("Open /Users/alice\n", encoding="utf-8")
            errors = validator.find_portability_violations(root)
            self.assertEqual(1, len(errors))
            self.assertIn("machine-specific macOS path", errors[0])

    def test_detects_canonical_windows_user_home_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "references").mkdir()
            (root / "assets").mkdir()
            (root / "SKILL.md").write_text(
                r"Open C:\Users\alice\robot-project." + "\n", encoding="utf-8"
            )
            errors = validator.find_portability_violations(root)
            self.assertEqual(1, len(errors))
            self.assertIn("machine-specific Windows path", errors[0])

    def test_detects_forward_slash_windows_user_home_case_insensitively(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "references").mkdir()
            (root / "assets").mkdir()
            (root / "SKILL.md").write_text(
                "Open C:/users/alice/robot-project.\n", encoding="utf-8"
            )
            errors = validator.find_portability_violations(root)
            self.assertEqual(1, len(errors))
            self.assertIn("machine-specific Windows path", errors[0])


class SecretTests(unittest.TestCase):
    def test_detects_fine_grained_github_token_shape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            token = "github_" + "pat_1234567890abcdefghijklmnop"
            (root / "config.txt").write_text(
                f"token={token}\n", encoding="utf-8"
            )
            errors = validator.find_secret_like_content(root)
            self.assertEqual(1, len(errors))

    def test_accepts_documented_environment_variable_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config.txt").write_text("GITHUB_TOKEN is provided by CI.\n", encoding="utf-8")
            self.assertEqual([], validator.find_secret_like_content(root))

    def test_detects_secret_in_utf16_text_resource(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            token = "github_" + "pat_1234567890abcdefghijklmnop"
            (root / "script.ps1").write_text(
                f"token={token}\n", encoding="utf-16"
            )
            errors = validator.find_secret_like_content(root)
            self.assertEqual(1, len(errors))
            self.assertIn("script.ps1", errors[0])

    def test_skips_utf8_decodable_binary_resource(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "model.bin").write_bytes(b"\0AKIA1234567890ABCDEF\0")
            self.assertEqual([], validator.find_secret_like_content(root))

    def test_ignores_local_credentials_but_scans_env_example(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            token = "github_" + "pat_1234567890abcdefghijklmnop"
            for filename in (".env", ".env.local", "private.pem", "private.key"):
                (root / filename).write_text(f"token={token}\n", encoding="utf-8")
            (root / ".env.example").write_text(f"token={token}\n", encoding="utf-8")
            errors = validator.find_secret_like_content(root)
            self.assertEqual(1, len(errors))
            self.assertIn(".env.example", errors[0])


class ResourceTests(unittest.TestCase):
    def test_ignores_empty_files_in_virtual_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / ".venv" / "lib" / "package"
            package.mkdir(parents=True)
            (package / "__init__.py").write_bytes(b"")
            self.assertEqual([], validator.find_empty_resources(root))

    def test_ignores_empty_local_credential_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for filename in (".env", ".env.local", "private.pem", "private.key"):
                (root / filename).write_bytes(b"")
            self.assertEqual([], validator.find_empty_resources(root))


class InstallationDocumentationTests(unittest.TestCase):
    def test_copy_installation_commands_are_fail_closed(self) -> None:
        lines = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8").splitlines()
        checks = [line for line in lines if line.startswith("test ! -e ")]
        copies = [line for line in lines if line.strip().startswith("cp -R build-robot-project ")]
        self.assertTrue(checks)
        self.assertEqual(len(checks), len(copies))
        self.assertTrue(all(line.endswith(" &&") for line in checks))
        self.assertTrue(all(line.strip().endswith(" &&") for line in copies))
        project_commands = [line for line in lines if "/path/to/robot-project" in line]
        self.assertTrue(project_commands)
        self.assertTrue(
            all('"/path/to/robot-project' in line for line in project_commands)
        )


class SafetyDocumentationTests(unittest.TestCase):
    def test_readme_requires_physical_stop_for_all_hazardous_motion(self) -> None:
        readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("motion capable of injury or material property damage requires", readme)

    def test_first_body_contact_is_a_mandatory_gate(self) -> None:
        skill = (REPOSITORY_ROOT / "build-robot-project" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        safety = (
            REPOSITORY_ROOT
            / "build-robot-project"
            / "references"
            / "robotics-safety.md"
        ).read_text(encoding="utf-8")
        self.assertIn("first body contact", skill)
        self.assertIn("first body contact", safety)

    def test_local_sensitive_data_collection_and_storage_are_mandatory_gates(self) -> None:
        skill = (REPOSITORY_ROOT / "build-robot-project" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        safety = (
            REPOSITORY_ROOT
            / "build-robot-project"
            / "references"
            / "robotics-safety.md"
        ).read_text(encoding="utf-8")
        readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
        required_gate = "local sensitive-data collection or storage"
        self.assertIn(required_gate, skill)
        self.assertIn(required_gate, safety)
        self.assertIn(required_gate, readme)


class RepositoryTests(unittest.TestCase):
    def test_requires_executable_unit_test_module(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            errors = validator.validate_repository(Path(directory))
            self.assertIn(
                "missing required repository file: tests/test_validate_repository.py", errors
            )

    def test_rejects_required_skill_resource_symlink_outside_skill(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            root = workspace / "repository"
            references = root / "build-robot-project" / "references"
            references.mkdir(parents=True)
            outside = workspace / "outside.md"
            outside.write_text("outside\n", encoding="utf-8")
            (references / "discovery-interview.md").symlink_to(outside)
            errors = validator.validate_repository(root)
            self.assertIn(
                "required skill file resolves outside distributable skill directory: "
                "build-robot-project/references/discovery-interview.md",
                errors,
            )

    def test_rejects_optional_skill_resource_symlink_outside_skill(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            root = workspace / "repository"
            skill_root = root / "build-robot-project"
            skill_root.mkdir(parents=True)
            outside = workspace / "outside.txt"
            outside.write_text("outside\n", encoding="utf-8")
            (skill_root / "optional.txt").symlink_to(outside)
            errors = validator.validate_repository(root)
            self.assertIn(
                "build-robot-project/optional.txt: symlink resolves outside "
                "distributable skill directory",
                errors,
            )

    def test_rejects_absolute_symlink_target_inside_skill(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill_root = root / "build-robot-project"
            skill_root.mkdir()
            target = skill_root / "target.txt"
            target.write_text("target\n", encoding="utf-8")
            (skill_root / "absolute.txt").symlink_to(target.resolve())
            self.assertEqual(
                [
                    "build-robot-project/absolute.txt: symlink target is absolute "
                    "and not portable"
                ],
                validator.find_escaping_skill_symlinks(skill_root),
            )

    def test_rejects_dangling_optional_skill_resource_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill_root = root / "build-robot-project"
            skill_root.mkdir(parents=True)
            (skill_root / "optional.txt").symlink_to("missing.txt")
            errors = validator.validate_repository(root)
            self.assertIn(
                "build-robot-project/optional.txt: symlink target does not exist",
                errors,
            )

    def test_reports_invalid_skill_encoding_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill_root = root / "build-robot-project"
            skill_root.mkdir()
            (skill_root / "SKILL.md").write_bytes(b"\xff")
            errors = validator.validate_repository(root)
            self.assertTrue(any("valid UTF-8" in error for error in errors))

    def test_current_repository_passes(self) -> None:
        self.assertEqual([], validator.validate_repository(REPOSITORY_ROOT))


if __name__ == "__main__":
    unittest.main()

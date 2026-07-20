from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

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

    def test_accepts_tab_separator_before_link_title(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "guide.md").write_text("# Guide\n", encoding="utf-8")
            (root / "README.md").write_text(
                '[guide](guide.md\t"Guide")\n', encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

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
            (root / "README.md").write_text(
                "[example](missing.md\n\n)\n", encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

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

    def test_accepts_backslash_escaped_punctuation_in_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "asset(v2).md").write_text("asset\n", encoding="utf-8")
            (root / "README.md").write_text(
                "[asset](asset\\(v2\\).md)\n", encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_reports_missing_reference_style_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[guide][setup]\n\n[setup]: references/missing.md\n", encoding="utf-8"
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("references/missing.md", errors[0])

    def test_reports_reference_label_with_escaped_closing_bracket(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[guide][a\\]]\n\n[a\\]]: missing.md\n", encoding="utf-8"
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

    def test_reports_reference_destination_continued_on_next_line(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[guide][docs]\n"
                "[docs]:\n"
                "  references/missing.md\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("references/missing.md", errors[0])

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

    def test_ignores_code_span_closed_by_backslash_prefixed_tick(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "`[guide](missing.md)\\`\n", encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

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

    def test_preserves_link_after_escaped_html_comment_opener(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "\\<!-- [guide](missing.md) -->\n", encoding="utf-8"
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

    def test_validates_html_target_after_quoted_greater_than(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<img alt="a > b" src="missing.png">\n', encoding="utf-8"
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.png", errors[0])

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

    def test_current_repository_passes(self) -> None:
        self.assertEqual([], validator.validate_repository(REPOSITORY_ROOT))


if __name__ == "__main__":
    unittest.main()

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

    def test_scans_resources_in_linked_html_documents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[demo](page.html)\n", encoding="utf-8"
            )
            (root / "page.html").write_text(
                '<img src="missing.png">\n', encoding="utf-8"
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("page.html", errors[0])
            self.assertIn("missing.png", errors[0])

    def test_recursively_scans_linked_html_with_cycle_protection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[demo](page.html)\n", encoding="utf-8"
            )
            (root / "page.html").write_text(
                '<a href="nested.html">nested</a>\n', encoding="utf-8"
            )
            (root / "nested.html").write_text(
                '<a href="page.html">back</a>'
                '<script src="missing.js"></script>\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("nested.html", errors[0])
            self.assertIn("missing.js", errors[0])

    def test_scans_resources_in_embedded_html_documents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<iframe src="frame.html"></iframe>\n'
                '<object data="object.html"></object>\n'
                '<img src="image.html">\n'
                '<iframe srcdoc="<iframe src=&quot;nested.html&quot;>'
                '</iframe>"></iframe>\n',
                encoding="utf-8",
            )
            (root / "frame.html").write_text(
                '<img src="missing-frame.png">\n', encoding="utf-8"
            )
            (root / "object.html").write_text(
                '<script src="missing-object.js"></script>\n', encoding="utf-8"
            )
            (root / "nested.html").write_text(
                '<link rel="stylesheet" href="missing-nested.css">\n',
                encoding="utf-8",
            )
            (root / "image.html").write_text(
                '<img src="ignored-image-payload.png">\n', encoding="utf-8"
            )

            errors = validator.find_broken_links(root)
            self.assertEqual(3, len(errors))
            self.assertTrue(any("missing-frame.png" in error for error in errors))
            self.assertTrue(any("missing-object.js" in error for error in errors))
            self.assertTrue(any("missing-nested.css" in error for error in errors))
            self.assertFalse(
                any("ignored-image-payload.png" in error for error in errors)
            )

    def test_recursively_scans_linked_svg_documents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[diagram](diagram.svg)\n", encoding="utf-8"
            )
            (root / "diagram.svg").write_text(
                '<svg xmlns="http://www.w3.org/2000/svg">'
                '<a href="nested.svg"><text>nested</text></a></svg>\n',
                encoding="utf-8",
            )
            (root / "nested.svg").write_text(
                '<svg xmlns="http://www.w3.org/2000/svg">'
                '<a href="diagram.svg"><text>back</text></a>'
                '<image href="missing.png"/></svg>\n',
                encoding="utf-8",
            )

            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("nested.svg", errors[0])
            self.assertIn("missing.png", errors[0])

    def test_validates_svg_script_href_resources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<svg><script href="missing-inline.js"></script></svg>\n'
                "[diagram](diagram.svg)\n",
                encoding="utf-8",
            )
            (root / "diagram.svg").write_text(
                '<svg xmlns="http://www.w3.org/2000/svg">'
                '<script href="missing-standalone.js"/></svg>\n',
                encoding="utf-8",
            )

            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(any("missing-inline.js" in error for error in errors))
            self.assertTrue(
                any("missing-standalone.js" in error for error in errors)
            )

    def test_validates_svg_xml_stylesheet_processing_instructions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[diagram](diagram.svg)\n", encoding="utf-8"
            )
            (root / "theme.css").write_text(
                '@import "missing.css";\n', encoding="utf-8"
            )
            (root / "diagram.svg").write_text(
                '<?xml-stylesheet type="text/css" href="theme.css"?>\n'
                '<svg xmlns="http://www.w3.org/2000/svg">'
                '<?xml-stylesheet type="text/css" href="ignored-inside.css"?>'
                "</svg>\n",
                encoding="utf-8",
            )

            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.css", errors[0])

    def test_accepts_svg_view_specification_fragments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[view](diagram.svg#svgView(viewBox(0,0,100,100))) "
                "[invalid](diagram.svg#svgView(viewBox(0,0,-1,100)))\n",
                encoding="utf-8",
            )
            (root / "diagram.svg").write_text(
                '<svg xmlns="http://www.w3.org/2000/svg"/>\n',
                encoding="utf-8",
            )

            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("svgView(viewBox(0,0,-1,100))", errors[0])

    def test_validates_inline_svg_xlink_navigation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<svg><a xlink:href="missing-outer.html">outer</a></svg>\n'
                '<iframe srcdoc="<svg><a '
                'xlink:href=\047missing-srcdoc.html\047>srcdoc</a>'
                '</svg>"></iframe>\n',
                encoding="utf-8",
            )

            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(any("missing-outer.html" in error for error in errors))
            self.assertTrue(any("missing-srcdoc.html" in error for error in errors))

    def test_resolves_standalone_svg_resources_through_xml_base(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[diagram](diagram.svg)\n", encoding="utf-8"
            )
            (root / "assets" / "icons").mkdir(parents=True)
            (root / "assets" / "icons" / "pic.png").write_bytes(b"png")
            (root / "diagram.svg").write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" '
                'xml:base="assets/"><g xml:base="icons/">'
                '<image href="pic.png"/></g></svg>\n',
                encoding="utf-8",
            )

            self.assertEqual([], validator.find_broken_links(root))

    def test_scans_inline_module_script_bodies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<script type="module">import "./missing-markdown.js";</script>\n'
                "[html](page.html) [xhtml](page.xhtml)\n"
                '<iframe srcdoc="<script type=\047module\047>'
                'import &quot;./missing-srcdoc.js&quot;;</script>"></iframe>\n',
                encoding="utf-8",
            )
            (root / "page.html").write_text(
                '<script type="module">import "./missing-html.js";</script>\n',
                encoding="utf-8",
            )
            (root / "page.xhtml").write_text(
                '<html xmlns="http://www.w3.org/1999/xhtml">'
                '<script type="module">import "./missing-xhtml.js";</script>'
                "</html>\n",
                encoding="utf-8",
            )

            errors = validator.find_broken_links(root)
            self.assertEqual(4, len(errors))
            for target in (
                "missing-markdown.js",
                "missing-html.js",
                "missing-xhtml.js",
                "missing-srcdoc.js",
            ):
                self.assertTrue(any(target in error for error in errors))

    def test_traverses_svg_documents_loaded_in_embedded_contexts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<iframe src="frame.svg"></iframe>\n'
                '<object data="object.svg"></object>\n',
                encoding="utf-8",
            )
            (root / "frame.svg").write_text(
                '<svg xmlns="http://www.w3.org/2000/svg">'
                '<image href="missing-frame.png"/></svg>\n',
                encoding="utf-8",
            )
            (root / "object.svg").write_text(
                '<svg xmlns="http://www.w3.org/2000/svg">'
                '<image href="missing-object.png"/></svg>\n',
                encoding="utf-8",
            )

            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(any("missing-frame.png" in error for error in errors))
            self.assertTrue(any("missing-object.png" in error for error in errors))

    def test_resolves_xhtml_resources_through_inherited_xml_base(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[page](page.xhtml)\n", encoding="utf-8"
            )
            (root / "assets" / "icons").mkdir(parents=True)
            (root / "assets" / "icons" / "ok.png").write_bytes(b"png")
            (root / "page.xhtml").write_text(
                '<html xmlns="http://www.w3.org/1999/xhtml" '
                'xml:base="assets/"><body><div xml:base="icons/">'
                '<img src="ok.png"/></div></body></html>\n',
                encoding="utf-8",
            )

            self.assertEqual([], validator.find_broken_links(root))

    def test_processes_resources_inside_declarative_shadow_roots(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[page](page.html)\n"
                '<iframe srcdoc="<div><template shadowrootmode=\047closed\047>'
                '<img src=\047missing-srcdoc-shadow.png\047></template></div>'
                '"></iframe>\n',
                encoding="utf-8",
            )
            (root / "page.html").write_text(
                '<div><template shadowrootmode="open">'
                '<img src="missing-shadow.png">'
                "</template></div>"
                '<template><img src="ignored-inert.png"></template>\n',
                encoding="utf-8",
            )

            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(any("missing-shadow.png" in error for error in errors))
            self.assertTrue(
                any("missing-srcdoc-shadow.png" in error for error in errors)
            )
            self.assertFalse(any("ignored-inert.png" in error for error in errors))

    def test_scans_xhtml_resources_inside_standalone_svg_foreign_object(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[diagram](diagram.svg)\n", encoding="utf-8"
            )
            (root / "diagram.svg").write_text(
                '<svg xmlns="http://www.w3.org/2000/svg">'
                '<foreignObject><img xmlns="http://www.w3.org/1999/xhtml" '
                'src="missing-foreign-object.png"/></foreignObject></svg>\n',
                encoding="utf-8",
            )

            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing-foreign-object.png", errors[0])

    def test_ignores_resources_discarded_by_frameset_insertion_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[valid](valid.html) [broken](broken.html)\n", encoding="utf-8"
            )
            (root / "valid.html").write_text(
                '<html><frameset><img src="ignored.png">'
                '<frame src="existing.html"></frameset></html>\n',
                encoding="utf-8",
            )
            (root / "broken.html").write_text(
                '<html><frameset><frame src="missing-frame.html">'
                "</frameset></html>\n",
                encoding="utf-8",
            )
            (root / "existing.html").write_text("<p>ok</p>\n", encoding="utf-8")

            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing-frame.html", errors[0])
            self.assertNotIn("ignored.png", errors[0])

    def test_validates_stylesheet_local_fragments_in_the_styled_document(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[page](page.html)\n", encoding="utf-8"
            )
            (root / "page.html").write_text(
                '<link rel="stylesheet" href="theme.css">'
                '<svg><filter id="present"></filter></svg>\n',
                encoding="utf-8",
            )
            (root / "theme.css").write_text(
                ".ok { filter: url(#present); }\n"
                ".broken { filter: url(#missing); }\n",
                encoding="utf-8",
            )

            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertTrue(errors[0].startswith("theme.css:"))
            self.assertIn("broken HTML fragment #missing", errors[0])
            self.assertFalse(any("#present" in error for error in errors))

    def test_restricts_link_resources_to_the_html_namespace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<svg><link rel="stylesheet" href="ignored.css"></link></svg>\n'
                '<iframe srcdoc="<svg><link rel=\047stylesheet\047 '
                'href=\047ignored-srcdoc.css\047></link></svg>"></iframe>\n',
                encoding="utf-8",
            )

            self.assertEqual([], validator.find_broken_links(root))

    def test_validates_svg_presentation_attribute_urls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<svg><rect fill="url(missing-fill.svg#paint)" '
                'filter="url(missing-filter.svg#fx)"></rect></svg>\n'
                '<iframe srcdoc="<svg><path '
                'stroke=\047url(missing-stroke.svg#paint)\047>'
                '</path></svg>"></iframe>\n',
                encoding="utf-8",
            )

            errors = validator.find_broken_links(root)
            self.assertEqual(3, len(errors))
            for target in {
                "missing-fill.svg#paint",
                "missing-filter.svg#fx",
                "missing-stroke.svg#paint",
            }:
                self.assertTrue(any(target in error for error in errors))

    def test_accepts_the_special_top_fragment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "page.html").write_text("<p>page</p>\n", encoding="utf-8")
            (root / "README.md").write_text(
                "[same](#ToP) [page](page.html#TOP)\n"
                '<iframe srcdoc="<a href=\047#tOp\047>up</a>"></iframe>\n',
                encoding="utf-8",
            )

            self.assertEqual([], validator.find_broken_links(root))

    def test_traverses_static_imports_from_module_scripts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<script type="module" src="main.js"></script>\n'
                "[page](page.html)\n"
                '<iframe srcdoc="<script type=\047module\047 '
                'src=\047srcdoc.js\047></script>"></iframe>\n',
                encoding="utf-8",
            )
            (root / "page.html").write_text(
                '<script type="module" src="page.js"></script>\n',
                encoding="utf-8",
            )
            (root / "main.js").write_text(
                'import "./nested.js";\n', encoding="utf-8"
            )
            (root / "nested.js").write_text(
                'import "./main.js";\n'
                "export const present = 1\n"
                'export { missing } from "./missing.js";\n',
                encoding="utf-8",
            )
            (root / "page.js").write_text(
                'import "./missing-page.js";\n', encoding="utf-8"
            )
            (root / "srcdoc.js").write_text(
                'export * from "./missing-srcdoc.js";\n', encoding="utf-8"
            )

            errors = validator.find_broken_links(root)
            self.assertEqual(3, len(errors))
            for target in {
                "missing.js",
                "missing-page.js",
                "missing-srcdoc.js",
            }:
                self.assertTrue(any(target in error for error in errors))

    def test_parses_xhtml_targets_with_xml_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "[page](page.xhtml)\n", encoding="utf-8"
            )
            (root / "page.xhtml").write_text(
                '<html xmlns="http://www.w3.org/1999/xhtml"><head>'
                '<SCRIPT SRC="ignored-uppercase.js"/>'
                '<script src="missing-lowercase.js"/>'
                '</head><body/></html>\n',
                encoding="utf-8",
            )

            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing-lowercase.js", errors[0])
            self.assertFalse(any("ignored-uppercase.js" in error for error in errors))

    def test_ignores_non_static_module_specifiers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<script type="module" src="main.js"></script>\n',
                encoding="utf-8",
            )
            (root / "main.js").write_text(
                'const text = \'import "./ignored-string.js"\';\n'
                '// import "./ignored-comment.js";\n'
                'const pattern = /import "\\.\\/ignored-regex\\.js"/;\n'
                'import("./ignored-dynamic.js");\n'
                'import.meta.resolve("./ignored-meta.js");\n'
                'import "bare-package";\n',
                encoding="utf-8",
            )

            self.assertEqual([], validator.find_broken_links(root))

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

    def test_drops_non_ascii_separators_from_heading_fragments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "# foo&nbsp;bar\n\n[working](#foobar) [stale](#foo-bar)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("#foo-bar", errors[0])

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

    def test_does_not_reparse_each_reference_definition_suffix(self) -> None:
        text = "# Heading\n" + "".join(
            f"[ref-{index}]: file-{index}.md\n" for index in range(2_000)
        )
        with mock.patch.object(
            validator,
            "markdown_label_end",
            wraps=validator.markdown_label_end,
        ) as label_end:
            fragments = validator.markdown_heading_fragments(text)
        self.assertIn("heading", fragments)
        self.assertLess(label_end.call_count, 10)

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

    def test_keeps_indented_blocks_in_unused_footnotes_masked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "`[^unused]`\n\n"
                "[^unused]: First paragraph\n\n"
                "    ![inert](missing.png)\n",
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

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

    def test_preserves_line_alignment_when_indented_code_contains_form_feed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "\t\fx\n# Heading\n[working](#heading)\n",
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
                '<picture><source srcset="missing-wide.png 640w"></picture>\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(any("missing-large.png" in error for error in errors))
            self.assertTrue(any("missing-wide.png" in error for error in errors))

    def test_validates_responsive_image_preload_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<link rel="preload" as="image" '
                'imagesrcset="missing-preload.png 1x">\n'
                '<iframe srcdoc="<link rel=\047preload\047 as=\047image\047 '
                'imagesrcset=\047missing-srcdoc.png 1x\047>"></iframe>\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(any("missing-preload.png" in error for error in errors))
            self.assertTrue(any("missing-srcdoc.png" in error for error in errors))

    def test_suppresses_img_src_only_when_srcset_replaces_its_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "existing.png").write_bytes(b"image")
            (root / "README.md").write_text(
                '<img src="overridden.png" srcset="existing.png 1x">\n'
                '<img src="fallback.png" srcset="existing.png 2x">\n'
                '<img src="width-overridden.png" srcset="existing.png 640w">\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("fallback.png", errors[0])

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

    def test_restricts_object_data_to_the_html_namespace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<object data="missing-html.bin"></object>\n'
                '<svg><object data="ignored-svg.bin"></object></svg>\n'
                '<math><object data="ignored-math.bin"></object></math>\n'
                '<iframe srcdoc="<object data=\047missing-srcdoc-html.bin\047>'
                '</object><svg><object data=\047ignored-srcdoc-svg.bin\047>'
                '</object></svg>"></iframe>\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(any("missing-html.bin" in error for error in errors))
            self.assertTrue(
                any("missing-srcdoc-html.bin" in error for error in errors)
            )
            self.assertFalse(any("ignored-" in error for error in errors))

    def test_restricts_src_loading_to_html_namespace_elements(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<script src="missing-html.js"></script>\n'
                '<svg><script src="ignored-svg.js"></script>'
                '<video src="ignored-svg-video.mp4"></video>'
                '<input type="image" src="ignored-svg-input.png"></svg>\n'
                '<math><script src="ignored-math.js"></script></math>\n'
                '<iframe srcdoc="<script src=\047missing-srcdoc-html.js\047>'
                '</script><svg><script src=\047ignored-srcdoc-svg.js\047>'
                '</script><input type=\047image\047 '
                'src=\047ignored-srcdoc-svg-input.png\047></svg>'
                '"></iframe>\n',
                encoding="utf-8",
            )

            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(any("missing-html.js" in error for error in errors))
            self.assertTrue(
                any("missing-srcdoc-html.js" in error for error in errors)
            )
            self.assertFalse(any("ignored-" in error for error in errors))

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
                '<feImage href="missing-filter.png"></feImage>'
                '<use href="missing.svg#icon"></use>'
                '<use href="#present"></use></svg>\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(3, len(errors))
            self.assertTrue(any("missing.png" in error for error in errors))
            self.assertTrue(
                any("missing-filter.png" in error for error in errors)
            )
            self.assertTrue(any("missing.svg#icon" in error for error in errors))

    def test_ignores_svg_named_href_elements_in_the_html_namespace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<use href="ignored.svg#icon"></use>\n'
                '<feImage href="ignored-filter.png"></feImage>\n'
                '<iframe srcdoc="<use href=\047ignored-srcdoc.svg#icon\047>'
                '</use><feImage href=\047ignored-srcdoc-filter.png\047>'
                '</feImage>"></iframe>\n',
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_validates_contextual_source_src_resources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "existing.png").write_bytes(b"image")
            (root / "README.md").write_text(
                '<picture><source src="ignored-picture.png" '
                'srcset="existing.png 1x"></picture>\n'
                '<video><source src="missing-video.mp4"></video>\n'
                '<audio><source src="missing-audio.mp3"></audio>\n'
                '<iframe srcdoc="<picture><source src=\047ignored-srcdoc-picture.png\047 '
                'srcset=\047existing.png 1x\047></picture>'
                '<video><source src=\047missing-srcdoc-video.mp4\047></video>'
                '<audio><source src=\047missing-srcdoc-audio.mp3\047></audio>'
                '"></iframe>\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(4, len(errors))
            self.assertTrue(any("missing-video.mp4" in error for error in errors))
            self.assertTrue(any("missing-audio.mp3" in error for error in errors))
            self.assertTrue(
                any("missing-srcdoc-video.mp4" in error for error in errors)
            )
            self.assertTrue(
                any("missing-srcdoc-audio.mp3" in error for error in errors)
            )
            self.assertFalse(any("ignored-picture.png" in error for error in errors))
            self.assertFalse(
                any("ignored-srcdoc-picture.png" in error for error in errors)
            )

    def test_checks_the_source_elements_direct_parent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<picture><audio><source src="missing-nested-audio.mp3">'
                '</audio></picture>\n'
                '<audio><div><source src="ignored-indirect-audio.mp3">'
                '</div></audio>\n'
                '<iframe srcdoc="<picture><video><source '
                'src=\047missing-srcdoc-nested-video.mp4\047></video></picture>'
                '<video><div><source src=\047ignored-srcdoc-indirect-video.mp4\047>'
                '</div></video>"></iframe>\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(
                any("missing-nested-audio.mp3" in error for error in errors)
            )
            self.assertTrue(
                any(
                    "missing-srcdoc-nested-video.mp4" in error
                    for error in errors
                )
            )
            self.assertFalse(any("ignored-" in error for error in errors))

    def test_preserves_nonvoid_slash_tag_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<video/><source src="missing-video.mp4">\n'
                '<iframe srcdoc="<video/><source '
                'src=\047missing-srcdoc-video.mp4\047>"></iframe>\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(any("missing-video.mp4" in error for error in errors))
            self.assertTrue(
                any("missing-srcdoc-video.mp4" in error for error in errors)
            )

    def test_restricts_source_srcset_to_picture_contexts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "existing.mp4").write_bytes(b"video")
            (root / "README.md").write_text(
                '<picture><source srcset="missing-picture.png 1x"></picture>\n'
                '<video><source src="existing.mp4" '
                'srcset="ignored-video.png 1x"></video>\n'
                '<source srcset="ignored-orphan.png 1x">\n'
                '<iframe srcdoc="<picture><source '
                'srcset=\047missing-srcdoc-picture.png 1x\047></picture>'
                '<video><source src=\047existing.mp4\047 '
                'srcset=\047ignored-srcdoc-video.png 1x\047></video>'
                '<source srcset=\047ignored-srcdoc-orphan.png 1x\047>'
                '"></iframe>\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(any("missing-picture.png" in error for error in errors))
            self.assertTrue(
                any("missing-srcdoc-picture.png" in error for error in errors)
            )
            self.assertFalse(any("ignored-video.png" in error for error in errors))
            self.assertFalse(any("ignored-orphan.png" in error for error in errors))

    def test_recognizes_legacy_html_image_alias(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "existing.png").write_bytes(b"image")
            (root / "README.md").write_text(
                '<image src="missing-alias.png">\n'
                '<image src="overridden-alias.png" srcset="existing.png 1x">\n'
                '<svg><image src="ignored-svg.png"></image></svg>\n'
                '<iframe srcdoc="<image src=\047missing-srcdoc-alias.png\047>'
                '<svg><image src=\047ignored-srcdoc-svg.png\047></image></svg>'
                '"></iframe>\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(any("missing-alias.png" in error for error in errors))
            self.assertTrue(
                any("missing-srcdoc-alias.png" in error for error in errors)
            )
            self.assertFalse(any("overridden-alias.png" in error for error in errors))
            self.assertFalse(any("ignored-svg.png" in error for error in errors))
            self.assertFalse(
                any("ignored-srcdoc-svg.png" in error for error in errors)
            )

    def test_recognizes_html_image_alias_at_svg_integration_points(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<svg><foreignObject><image src="missing-foreign-object.png">'
                '</foreignObject><image src="ignored-svg.png"></image></svg>\n'
                '<iframe srcdoc="<svg><foreignObject><image '
                'src=\047missing-srcdoc-foreign-object.png\047>'
                '</foreignObject><image src=\047ignored-srcdoc-svg.png\047>'
                '</image></svg>"></iframe>\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(
                any("missing-foreign-object.png" in error for error in errors)
            )
            self.assertTrue(
                any(
                    "missing-srcdoc-foreign-object.png" in error
                    for error in errors
                )
            )
            self.assertFalse(any("ignored-svg.png" in error for error in errors))
            self.assertFalse(
                any("ignored-srcdoc-svg.png" in error for error in errors)
            )

    def test_reprocesses_html_breakout_tags_inside_foreign_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<svg><div><picture><source srcset="missing-breakout.png 1x">'
                '</picture></div></svg>\n'
                '<iframe srcdoc="<svg><div><picture><source '
                'srcset=\047missing-srcdoc-breakout.png 1x\047></picture>'
                '</div></svg>"></iframe>\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(any("missing-breakout.png" in error for error in errors))
            self.assertTrue(
                any("missing-srcdoc-breakout.png" in error for error in errors)
            )

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

    def test_ignores_src_on_non_executable_script_data_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<script type="application/json" src="ignored.json">{}</script>\n'
                '<script type="module" src="missing-module.js"></script>\n'
                '<iframe srcdoc="<script type=\047application/ld+json\047 '
                'src=\047ignored-srcdoc.json\047>{}</script>'
                '<script src=\047missing-srcdoc.js\047></script>"></iframe>\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(any("missing-module.js" in error for error in errors))
            self.assertTrue(any("missing-srcdoc.js" in error for error in errors))

    def test_uses_legacy_script_language_to_decide_src_loading(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<script language="json" src="ignored-data.json"></script>\n'
                '<script language="javascript" src="missing-script.js"></script>\n'
                '<iframe srcdoc="<script language=\047json\047 '
                'src=\047ignored-srcdoc-data.json\047></script>'
                '<script language=\047javascript\047 '
                'src=\047missing-srcdoc-script.js\047></script>"></iframe>\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(any("missing-script.js" in error for error in errors))
            self.assertTrue(
                any("missing-srcdoc-script.js" in error for error in errors)
            )
            self.assertFalse(any("ignored-data.json" in error for error in errors))
            self.assertFalse(
                any("ignored-srcdoc-data.json" in error for error in errors)
            )

    def test_preserves_resource_tags_inside_pre_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<pre>\n<img src="missing.png">\n</pre>\n', encoding="utf-8"
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.png", errors[0])

    def test_ignores_apparent_resource_tags_inside_inline_raw_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                'prefix <textarea><img src="ignored-textarea.png"></textarea>\n'
                'prefix <script><img src="ignored-script.png"></script>\n'
                'prefix <style>.hero { background: url(missing-style.png); } '
                '<img src="ignored-style.png"></style>\n'
                'prefix <textarea>done</textarea><img src="missing-live.png">\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(any("missing-style.png" in error for error in errors))
            self.assertTrue(any("missing-live.png" in error for error in errors))
            self.assertFalse(any("ignored-" in error for error in errors))

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

    def test_preserves_foreign_namespace_template_contents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "page.html").write_text(
                '<svg><template><g id="svg-page"></g></template></svg>'
                '<math><template><mrow id="math-page"></mrow></template></math>\n',
                encoding="utf-8",
            )
            (root / "README.md").write_text(
                '<svg><template><g id="svg-local"></g></template></svg>\n'
                '<math><template><mrow id="math-local"></mrow></template></math>\n\n'
                '[svg-local](#svg-local) [math-local](#math-local) '
                '[svg-page](page.html#svg-page) [math-page](page.html#math-page)\n',
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_excludes_inert_template_ids_from_fragment_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<template id="shell"><div id="hidden"></div></template>\n\n'
                "[shell](#shell) [hidden](#hidden)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("#hidden", errors[0])

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

    def test_validates_legacy_html_background_resources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<table background="missing-outer.png"></table>\n'
                '<svg><tbody background="ignored-outer.png"></tbody></svg>\n'
                '<iframe srcdoc="<table '
                'background=\047missing-srcdoc.png\047></table>'
                '<svg><tbody background=\047ignored-srcdoc.png\047>'
                '</tbody></svg>"></iframe>\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(any("missing-outer.png" in error for error in errors))
            self.assertTrue(any("missing-srcdoc.png" in error for error in errors))
            self.assertFalse(any("ignored-outer.png" in error for error in errors))
            self.assertFalse(any("ignored-srcdoc.png" in error for error in errors))

    def test_validates_area_links_only_inside_html_maps(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<area href="ignored-outer.html">\n'
                '<map><area href="missing-outer.html"></map>\n'
                '<iframe srcdoc="<area href=\047ignored-srcdoc.html\047>'
                '<map><area href=\047missing-srcdoc.html\047></map>"></iframe>\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(any("missing-outer.html" in error for error in errors))
            self.assertTrue(any("missing-srcdoc.html" in error for error in errors))
            self.assertFalse(any("ignored-outer.html" in error for error in errors))
            self.assertFalse(any("ignored-srcdoc.html" in error for error in errors))

    def test_ignores_poster_on_foreign_video_elements(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<svg><video poster="ignored-outer.png"></video></svg>\n'
                '<iframe srcdoc="<svg><video '
                'poster=\047ignored-srcdoc.png\047></video></svg>"></iframe>\n',
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

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

    def test_applies_img_srcset_precedence_inside_srcdoc(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "existing.png").write_bytes(b"image")
            (root / "README.md").write_text(
                '<iframe srcdoc="<img src=\'missing.png\' '
                'srcset=\'existing.png 1x\'>"></iframe>\n',
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_validates_fragment_only_srcdoc_urls_in_the_nested_document(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<div id="host-only"></div>\n'
                '<iframe srcdoc="<svg><filter id=\047blur\047></filter></svg>'
                '<div style=\047filter:url(#blur)\047></div>'
                '<a href=\047#missing\047>missing</a>'
                '<a href=\047#host-only\047>host only</a>'
                '"></iframe>\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(any("#missing" in error for error in errors))
            self.assertTrue(any("#host-only" in error for error in errors))
            self.assertFalse(any("#blur" in error for error in errors))

    def test_ignores_srcdoc_markup_inside_raw_text_elements(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<textarea><iframe srcdoc="&lt;a href=\047#ignored\047&gt;">'
                "</iframe></textarea>\n"
                '<iframe srcdoc="<a href=\047#missing\047>missing</a>">'
                "</iframe>\n",
                encoding="utf-8",
            )

            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("#missing", errors[0])
            self.assertFalse(any("#ignored" in error for error in errors))

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

    def test_ignores_urls_in_non_resource_css_declarations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<style>.ignored { example: url(ignored-unknown.png); '
                'color: url(ignored-invalid.png); '
                '--color-url: url(ignored-custom.png); '
                'color: var(--color-url); '
                'example-image: image-set("ignored-set.png" 1x); } '
                '.valid { background-image: url(missing-background.png); '
                'filter: url(missing-filter.svg); } '
                '.adjacent-one { background: url(missing-adjacent-one.png) } '
                '.adjacent-two { background: url(missing-adjacent-two.png) } '
                '@font-face { src: url(missing-font.woff2); } '
                '@counter-style images { system: symbolic; '
                'symbols: url(missing-symbol.svg); }</style>\n'
                '<div style="example:url(ignored-inline.png); '
                'background:url(missing-inline.png)"></div>\n',
                encoding="utf-8",
            )

            errors = validator.find_broken_links(root)
            self.assertEqual(7, len(errors))
            for target in (
                "missing-background.png",
                "missing-filter.svg",
                "missing-adjacent-one.png",
                "missing-adjacent-two.png",
                "missing-font.woff2",
                "missing-symbol.svg",
                "missing-inline.png",
            ):
                self.assertTrue(any(target in error for error in errors))
            self.assertFalse(any("ignored-" in error for error in errors))

    def test_ignores_resources_in_unused_css_custom_properties(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<div style="--unused-inline:url(ignored-inline.png); '
                '--used-inline:url(missing-inline.png); '
                'background:var(--used-inline)"></div>\n\n'
                '<style>:root { --unused: url(ignored-block.png); '
                '--used: url(missing-block.png); --chain: var(--used); '
                'background-image: var(--chain); }</style>\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(any("missing-block.png" in error for error in errors))
            self.assertTrue(any("missing-inline.png" in error for error in errors))
            self.assertFalse(any("ignored-" in error for error in errors))

    def test_tracks_css_custom_property_usage_across_style_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<style>:root{--asset:url(missing-cross-source.png)}</style>'
                '<div style="background:var(--asset)"></div>\n'
                '<iframe srcdoc="<style>:root{--asset:url('
                'missing-srcdoc-cross-source.png)}</style>'
                '<div style=\047background:var(--asset)\047></div>"></iframe>\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(
                any("missing-cross-source.png" in error for error in errors)
            )
            self.assertTrue(
                any(
                    "missing-srcdoc-cross-source.png" in error
                    for error in errors
                )
            )

    def test_accepts_all_html_whitespace_in_closing_style_tags(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                'prefix <style>body{background:url(missing-line-feed.png)}'
                '</style\n>\n'
                '<iframe srcdoc="<style>body{background:url('
                'missing-srcdoc-line-feed.png)}</style&#10;>"></iframe>\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(
                any("missing-line-feed.png" in error for error in errors)
            )
            self.assertTrue(
                any(
                    "missing-srcdoc-line-feed.png" in error
                    for error in errors
                )
            )

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

    def test_validates_string_candidates_in_css_image_set_functions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<div style="background-image:image-set(\'missing-inline.png\' 1x)"></div>\n'
                "\n"
                '<style>.hero { background-image: image-set("missing-block.png" 2x); }</style>\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(any("missing-inline.png" in error for error in errors))
            self.assertTrue(any("missing-block.png" in error for error in errors))

    def test_validates_same_document_css_url_fragments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<svg><filter id="blur"></filter></svg>\n'
                '<div style="filter:url(#blur)"></div>\n'
                '<div style="filter:url(#missing)"></div>\n'
                "\n"
                '<style>@import "#theme"; @import url(#theme-url);</style>\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(3, len(errors))
            self.assertFalse(any("#blur" in error for error in errors))
            self.assertTrue(
                any(
                    "broken Markdown fragment #missing" in error
                    for error in errors
                )
            )
            self.assertTrue(
                any(
                    "resource target has no file path '#theme'" in error
                    for error in errors
                )
            )
            self.assertTrue(
                any(
                    "resource target has no file path '#theme-url'" in error
                    for error in errors
                )
            )

    def test_ignores_css_namespace_uris(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<style>@namespace svg url(ignored.xml); '
                '@namespace url("ignored-default.xml"); '
                '.hero { background: url(missing.png); }</style>\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.png", errors[0])

    def test_ignores_resource_tokens_in_supports_conditions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<style>@supports (background: url(ignored.png)) '
                'and (background-image: image-set("ignored-set.png" 1x)) {'
                '.hero { background: url(missing.png); }}</style>\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.png", errors[0])
            self.assertFalse(any("ignored.png" in error for error in errors))
            self.assertFalse(any("ignored-set.png" in error for error in errors))

    def test_ignores_late_and_nested_css_imports(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<style>@import "missing-early.css"; '
                'body {} @import "ignored-late.css"; '
                '@media print { @import "ignored-nested.css"; '
                '.hero { background: url(missing.png); }}</style>\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(any("missing-early.css" in error for error in errors))
            self.assertTrue(any("missing.png" in error for error in errors))
            self.assertFalse(any("ignored-late.css" in error for error in errors))
            self.assertFalse(any("ignored-nested.css" in error for error in errors))

    def test_recursively_validates_imported_stylesheets_with_cycle_protection(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / "styles" / "nested"
            nested.mkdir(parents=True)
            (root / "README.md").write_text(
                '<style>@import url("styles/theme.css");</style>\n',
                encoding="utf-8",
            )
            (root / "styles" / "theme.css").write_text(
                '@import url("nested/child.css");\n',
                encoding="utf-8",
            )
            (nested / "child.css").write_text(
                '@import url("../theme.css");\n'
                '.hero { background-image: url("missing.png"); }\n',
                encoding="utf-8",
            )

            self.assertEqual(
                [
                    "styles/nested/child.css: broken relative link "
                    "'missing.png'"
                ],
                validator.find_broken_links(root),
            )

    def test_uses_lexical_url_base_for_symlinked_stylesheets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shared = root / "shared"
            first_alias = root / "first"
            second_alias = root / "second"
            shared.mkdir()
            first_alias.mkdir()
            second_alias.mkdir()
            (root / "README.md").write_text(
                '<link rel="stylesheet" href="first/theme.css">\n'
                '<link rel="stylesheet" href="second/theme.css">\n',
                encoding="utf-8",
            )
            (shared / "theme.css").write_text(
                'body { background-image: url(asset.png); }\n',
                encoding="utf-8",
            )
            (first_alias / "theme.css").symlink_to("../shared/theme.css")
            (second_alias / "theme.css").symlink_to("../shared/theme.css")
            (first_alias / "asset.png").write_bytes(b"ok")
            (shared / "asset.png").write_bytes(b"wrong canonical base")

            self.assertEqual(
                ["second/theme.css: broken relative link 'asset.png'"],
                validator.find_broken_links(root),
            )

    def test_skips_css_comments_around_url_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<style>.quoted { background: url(/* before */'
                '"missing-quoted.png"/* after */); } '
                '.unquoted { background: url(/* before */'
                'missing-unquoted.png/* after */); } '
                '.joined { background: url(missing-joined/* middle */.png); }'
                "</style>\n",
                encoding="utf-8",
            )

            errors = validator.find_broken_links(root)
            self.assertEqual(3, len(errors))
            self.assertTrue(any("missing-quoted.png" in error for error in errors))
            self.assertTrue(
                any("missing-unquoted.png" in error for error in errors)
            )
            self.assertTrue(any("missing-joined.png" in error for error in errors))

    def test_scans_each_css_identifier_once(self) -> None:
        with mock.patch.object(
            validator,
            "css_identifier_value",
            wraps=validator.css_identifier_value,
        ) as identifier:
            self.assertEqual([], validator.css_resource_references("a" * 8_000))
        self.assertLess(identifier.call_count, 10)

    def test_resolves_query_only_file_resources_to_the_current_document(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<iframe src="?view=compact"></iframe>\n', encoding="utf-8"
            )
            self.assertEqual([], validator.find_broken_links(root))

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
                "@import url('missing.css');\n"
                '@import "missing-theme.css";\n'
                '@import/* note */"missing-commented.css";\n'
                '.example::before { content: "url(string.png)"; }\n'
                ".example { background-image: url(missing.png); }\n"
                "</style>\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(4, len(errors))
            self.assertTrue(any("missing.css" in error for error in errors))
            self.assertTrue(any("missing-theme.css" in error for error in errors))
            self.assertTrue(
                any("missing-commented.css" in error for error in errors)
            )
            self.assertTrue(any("missing.png" in error for error in errors))

    def test_ignores_malformed_unquoted_css_urls_with_whitespace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<style>.bad { background: url(foo bar.png); } '
                '.good { background: url(missing.png); }</style>\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("missing.png", errors[0])

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

    def test_consumes_complete_hexadecimal_escapes_in_css_urls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<style>.outer { background: url(missing\\2e png); }</style>\n'
                '<iframe srcdoc="<style>.nested { background: '
                'url(missing-srcdoc\\2e png); }</style>"></iframe>\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(any("missing.png" in error for error in errors))
            self.assertTrue(
                any("missing-srcdoc.png" in error for error in errors)
            )

    def test_ignores_non_css_style_element_bodies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<style type="text/plain">a{background:url(ignored.png)}</style>\n'
                '<style type="text/css">a{background:url(missing.png)}</style>\n'
                '<iframe srcdoc="<style type=\047text/plain\047>'
                'a{background:url(ignored-srcdoc.png)}</style>'
                '<style>a{background:url(missing-srcdoc.png)}</style>"></iframe>\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(any("missing.png" in error for error in errors))
            self.assertTrue(any("missing-srcdoc.png" in error for error in errors))
            self.assertFalse(any("ignored.png" in error for error in errors))
            self.assertFalse(
                any("ignored-srcdoc.png" in error for error in errors)
            )

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

    def test_normalizes_backslashes_before_resolving_html_base_urls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docs").mkdir()
            (root / "docs" / "picture.png").write_bytes(b"docs image")
            (root / "README.md").write_text(
                '<base href="docs\\\\"><img src="picture.png">\n',
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_ignores_foreign_namespace_base_elements(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "picture.png").write_bytes(b"image")
            (root / "README.md").write_text(
                '<svg><base href="docs/"></base></svg>'
                '<math><base href="other/"></base></math>'
                '<img src="picture.png">\n'
                '<iframe srcdoc="<svg><base href=\047docs/\047></base></svg>'
                '<math><base href=\047other/\047></base></math>'
                '<img src=\047picture.png\047>"></iframe>\n',
                encoding="utf-8",
            )
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

    def test_stops_quoted_meta_refresh_targets_at_the_closing_quote(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "existing.html").write_text("existing\n", encoding="utf-8")
            (root / "existing-srcdoc.html").write_text(
                "existing\n", encoding="utf-8"
            )
            (root / "README.md").write_text(
                '<meta http-equiv="refresh" '
                'content="0;url=\047existing.html\047;ignored">\n'
                '<iframe srcdoc="<meta http-equiv=\047refresh\047 '
                'content=\0470;url=&quot;existing-srcdoc.html&quot;;ignored\047>'
                '"></iframe>\n',
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

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

    def test_validates_formaction_only_for_controls_with_form_owners(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<form><button formaction="missing-ancestor.html">Send</button>'
                "</form>\n"
                '<button form="later" formaction="missing-explicit.html">'
                'Send</button><form id="later"></form>\n'
                '<button formaction="ignored-ownerless.html">Send</button>\n'
                '<form><button form="absent" '
                'formaction="ignored-override.html">Send</button></form>\n'
                '<div id="collision"></div><form id="collision"></form>'
                '<button form="collision" '
                'formaction="ignored-id-collision.html">Send</button>\n'
                '<iframe srcdoc="<form><input type=\047submit\047 '
                'formaction=\047missing-srcdoc-ancestor.html\047></form>'
                '<input type=\047submit\047 form=\047srcdoc-later\047 '
                'formaction=\047missing-srcdoc-explicit.html\047>'
                '<form id=\047srcdoc-later\047></form>'
                '<button form=\047absent\047 '
                'formaction=\047ignored-srcdoc-ownerless.html\047>'
                '"></iframe>\n',
                encoding="utf-8",
            )

            errors = validator.find_broken_links(root)
            self.assertEqual(4, len(errors))
            self.assertTrue(
                any("missing-ancestor.html" in error for error in errors)
            )
            self.assertTrue(
                any("missing-explicit.html" in error for error in errors)
            )
            self.assertTrue(
                any(
                    "missing-srcdoc-ancestor.html" in error
                    for error in errors
                )
            )
            self.assertTrue(
                any(
                    "missing-srcdoc-explicit.html" in error
                    for error in errors
                )
            )
            self.assertFalse(any("ignored-" in error for error in errors))

    def test_ignores_action_on_discarded_nested_forms(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "existing.html").write_text("ok\n", encoding="utf-8")
            (root / "README.md").write_text(
                '<form action="existing.html">'
                '<form action="missing-nested.html"></form>'
                '<iframe srcdoc="<form action=\047existing.html\047>'
                '<form action=\047missing-srcdoc-nested.html\047></form>'
                '"></iframe>\n',
                encoding="utf-8",
            )

            self.assertEqual([], validator.find_broken_links(root))

    def test_validates_fragments_in_local_html_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "page.html").write_text(
                '<div id="present"></div><a name="legacy"></a>'
                '<template id="shell"><div id="hidden"></div></template>\n',
                encoding="utf-8",
            )
            (root / "README.md").write_text(
                "[present](page.html#present) "
                "[legacy](page.html#legacy) "
                "[shell](page.html#shell) "
                "[hidden](page.html#hidden) "
                "[missing](page.html#missing)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(any("page.html#hidden" in error for error in errors))
            self.assertTrue(any("page.html#missing" in error for error in errors))

    def test_excludes_ids_inside_scripting_enabled_noscript_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "page.html").write_text(
                '<noscript><div id="fallback"></div></noscript>'
                '<div id="live"></div>\n',
                encoding="utf-8",
            )
            (root / "README.md").write_text(
                "[fallback](page.html#fallback) [live](page.html#live)\n",
                encoding="utf-8",
            )

            self.assertEqual(
                [
                    "README.md: broken HTML fragment #fallback in "
                    "'page.html#fallback'"
                ],
                validator.find_broken_links(root),
            )

    def test_recognizes_text_fragment_directives_before_id_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "page.html").write_text(
                '<div id="present">Hello world</div>\n', encoding="utf-8"
            )
            (root / "README.md").write_text(
                "[text](page.html#:~:text=Hello%20world) "
                "[anchored](page.html#present:~:text=Hello) "
                "[missing](page.html#missing:~:text=Hello)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("page.html#missing:~:text=Hello", errors[0])

    def test_excludes_ids_on_elements_ignored_inside_selects(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "page.html").write_text(
                '<select><div id="hidden"></div>'
                '<option id="shown"><span id="ignored"></span></option>'
                '<input id="breakout"></select>\n',
                encoding="utf-8",
            )
            (root / "README.md").write_text(
                "[hidden](page.html#hidden) "
                "[shown](page.html#shown) "
                "[ignored](page.html#ignored) "
                "[breakout](page.html#breakout)\n",
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(2, len(errors))
            self.assertTrue(any("page.html#hidden" in error for error in errors))
            self.assertTrue(any("page.html#ignored" in error for error in errors))

    def test_ignores_resource_tags_discarded_inside_selects(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                '<select><img src="ignored-outer.png"></select>\n'
                '<iframe srcdoc="<select><img '
                'src=\047ignored-srcdoc.png\047></select>"></iframe>\n',
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

    def test_validates_fragments_in_local_svg_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "icons.svg").write_text(
                '<svg xmlns="http://www.w3.org/2000/svg">'
                '<symbol id="present"></symbol></svg>\n',
                encoding="utf-8",
            )
            (root / "README.md").write_text(
                '<svg><use href="icons.svg#present"></use>'
                '<use href="icons.svg#missing"></use></svg>\n',
                encoding="utf-8",
            )
            errors = validator.find_broken_links(root)
            self.assertEqual(1, len(errors))
            self.assertIn("icons.svg#missing", errors[0])

    def test_recognizes_xml_id_fragments_in_local_svg_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "icons.svg").write_text(
                '<svg xmlns="http://www.w3.org/2000/svg">'
                '<g xml:id="target"></g></svg>\n',
                encoding="utf-8",
            )
            (root / "README.md").write_text(
                '<svg><use href="icons.svg#target"></use></svg>\n',
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

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
                '<img\f src\f=\f"missing.png">\n',
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

    def test_removes_internal_url_tabs_and_newlines_before_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "existing.png").write_bytes(b"image")
            (root / "README.md").write_text(
                '<img src="exis\nting.png">\n'
                '<img src="ht\ntps://example.com/image.png">\n',
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_broken_links(root))

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

    def test_excludes_remote_url_paths_from_home_directory_detection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill_file = root / "SKILL.md"
            skill_file.write_text(
                "Read https://example.com/root/guide.\n"
                "Read https://example.com/home/widgets/docs.\n",
                encoding="utf-8",
            )
            self.assertEqual([], validator.find_portability_violations(root))

            skill_file.write_text(
                "Read https://example.com/root/guide.\n"
                "Read https://example.com/home/widgets/docs.\n"
                "Open /root/robot-project.\n",
                encoding="utf-8",
            )
            errors = validator.find_portability_violations(root)
            self.assertEqual(1, len(errors))
            self.assertIn("SKILL.md:3", errors[0])
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


class WorkflowTests(unittest.TestCase):
    def test_checkout_does_not_persist_github_credentials(self) -> None:
        workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "validate.yml").read_text(
            encoding="utf-8"
        )
        checkout_step = workflow[
            workflow.index("uses: actions/checkout@") : workflow.index(
                "- name: Set up Python"
            )
        ]
        self.assertIn("persist-credentials: false", checkout_step)

    def test_secret_scan_is_isolated_from_pr_controlled_commands(self) -> None:
        workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "validate.yml").read_text(
            encoding="utf-8"
        )
        validate_start = workflow.index("  validate:\n")
        secret_scan_start = workflow.index("  secret-scan:\n")
        validate_job = workflow[validate_start:secret_scan_start]
        secret_scan_job = workflow[secret_scan_start:]
        self.assertNotIn("GITHUB_TOKEN", validate_job)
        self.assertNotIn("gitleaks/gitleaks-action@", validate_job)
        self.assertIn("GITHUB_TOKEN", secret_scan_job)
        self.assertIn("gitleaks/gitleaks-action@", secret_scan_job)
        self.assertEqual(2, workflow.count("uses: actions/checkout@"))
        self.assertEqual(2, workflow.count("persist-credentials: false"))


class SkillWorkflowTests(unittest.TestCase):
    def test_explicit_stage_limits_are_completion_boundaries(self) -> None:
        skill = (REPOSITORY_ROOT / "build-robot-project" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("explicit earlier stage or scope limit", skill)
        self.assertIn("scaffold-only", skill)
        self.assertIn("Honor every explicit stage or scope limit", skill)


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

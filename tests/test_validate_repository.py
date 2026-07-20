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


class RepositoryTests(unittest.TestCase):
    def test_current_repository_passes(self) -> None:
        self.assertEqual([], validator.validate_repository(REPOSITORY_ROOT))


if __name__ == "__main__":
    unittest.main()

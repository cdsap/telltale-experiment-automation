import tempfile
import unittest
from pathlib import Path
from unittest import mock

from orchestrator.generator import Generator
from orchestrator.main import DEFAULT_DEVELOCITY_URL, parse_project_options


class GeneratorTest(unittest.TestCase):
    def test_default_project_options_include_develocity_url(self):
        self.assertEqual(
            {"modules": 100, "develocity_url": DEFAULT_DEVELOCITY_URL},
            parse_project_options([]),
        )

    def test_generate_project_passes_develocity_url_to_project_generator(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = root / "projectGenerator"
            binary.write_text("#!/bin/sh\n", encoding="utf-8")
            binary.chmod(0o755)

            with mock.patch("orchestrator.generator.subprocess.run") as run:
                Generator(binary).generate_project(root / "output", parse_project_options([]))

            run.assert_called_once_with(
                [
                    str(binary),
                    "generate-project",
                    "--output-dir",
                    str(root / "output"),
                    "--modules",
                    "100",
                    "--develocity-url",
                    DEFAULT_DEVELOCITY_URL,
                ],
                check=True,
                text=True,
                capture_output=True,
            )


if __name__ == "__main__":
    unittest.main()

from pathlib import Path
import unittest


class RenovateExperimentWorkflowTest(unittest.TestCase):
    def test_fetches_latest_project_generator_release(self):
        workflow = Path(".github/workflows/renovate-experiment.yml").read_text(encoding="utf-8")

        self.assertIn(
            "https://github.com/cdsap/ProjectGenerator/releases/latest/download/projectGenerator",
            workflow,
        )
        self.assertNotIn("PROJECT_GENERATOR_VERSION", workflow)
        self.assertNotIn("releases/download/v0.", workflow)


if __name__ == "__main__":
    unittest.main()

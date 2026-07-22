from pathlib import Path
import unittest


class RenovateExperimentWorkflowTest(unittest.TestCase):
    def test_fetches_tracked_project_generator_release(self):
        workflow = Path(".github/workflows/renovate-experiment.yml").read_text(encoding="utf-8")

        self.assertIn('json.load(open("versions_to_monitor.json"))["projectGenerator"]', workflow)
        self.assertIn("https://github.com/cdsap/ProjectGenerator/releases/download/${PROJECT_GENERATOR_VERSION}/projectGenerator", workflow)
        self.assertNotIn("releases/download/v0.", workflow)


if __name__ == "__main__":
    unittest.main()

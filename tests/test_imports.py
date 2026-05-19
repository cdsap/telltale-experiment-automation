import unittest

import orchestrator


class ImportsTest(unittest.TestCase):
    def test_root_package_exports_real_implementation(self):
        self.assertTrue(hasattr(orchestrator, "Detector"))
        self.assertTrue(hasattr(orchestrator, "Modifier"))
        self.assertTrue(hasattr(orchestrator, "WorkflowDispatch"))
        self.assertTrue(hasattr(orchestrator, "detect_changes_from_git"))


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from pathlib import Path

from orchestrator.detector import Detector


class DetectorTest(unittest.TestCase):
    def test_detects_changes_against_state_and_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            versions = root / "versions.json"
            state = root / "state.json"
            versions.write_text(json.dumps({"agp": "9.2.0", "kotlin": "2.3.20", "projectGenerator": "v0.6.4"}), encoding="utf-8")
            state.write_text(json.dumps({"agp": "9.1.0", "kotlin": "2.3.20", "projectGenerator": "v0.6.3"}), encoding="utf-8")

            changes = Detector(versions, state).detect_changes()

            self.assertEqual(1, len(changes))
            self.assertEqual("agp", changes[0].component)
            self.assertEqual("9.1.0", changes[0].old_version)
            self.assertEqual("9.2.0", changes[0].new_version)
            self.assertEqual(
                {"agp": "9.2.0", "kotlin": "2.3.20", "projectGenerator": "v0.6.4"},
                json.loads(state.read_text(encoding="utf-8")),
            )


if __name__ == "__main__":
    unittest.main()

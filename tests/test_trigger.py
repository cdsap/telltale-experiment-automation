import unittest

from orchestrator.trigger import Trigger, WorkflowDispatch


class TriggerTest(unittest.TestCase):
    def test_dry_run_payload_matches_telltale_workflow_inputs(self):
        dispatch = WorkflowDispatch(repository="cdsap/experiment-agp-9.2.0", variant_a="baseline", variant_b="agp-9.2.0")

        payload = Trigger(None).trigger_experiment(dispatch, dry_run=True)

        self.assertEqual("main", payload["ref"])
        self.assertEqual("cdsap/experiment-agp-9.2.0", payload["inputs"]["repository"])
        self.assertEqual("baseline", payload["inputs"]["variantA"])
        self.assertEqual("agp-9.2.0", payload["inputs"]["variantB"])
        self.assertEqual("assembleDebug", payload["inputs"]["task"])
        self.assertIn("extra_report_args", payload["inputs"])

    def test_renovate_merge_supports_dry_run_gate(self):
        self.assertTrue(Trigger(None).merge_renovate_pr(123, renovate_repo="cdsap/Telltale", dry_run=True))


if __name__ == "__main__":
    unittest.main()

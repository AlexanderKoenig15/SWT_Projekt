from __future__ import annotations

import unittest
from pathlib import Path

import yaml

WORKFLOW_FILE = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "pages.yml"


class PagesWorkflowTests(unittest.TestCase):
    def test_reconciliation_builds_only_changed_inputs_and_deploys_main(self) -> None:
        workflow = yaml.safe_load(WORKFLOW_FILE.read_text(encoding="utf-8"))
        jobs = workflow["jobs"]

        self.assertEqual("0 6-21 * * *", workflow[True]["schedule"][0]["cron"])
        workflow_dispatch = workflow[True]["workflow_dispatch"]
        self.assertEqual(
            "Optional source-id=SHA values, one per line",
            workflow_dispatch["inputs"]["source_revisions"]["description"],
        )
        self.assertNotIn("documents_revision", workflow_dispatch["inputs"])
        self.assertEqual(
            "${{ steps.decision.outputs.build_required }}",
            jobs["preflight"]["outputs"]["build_required"],
        )
        preflight_steps = {step["name"]: step for step in jobs["preflight"]["steps"]}
        self.assertEqual(
            "github.event_name == 'schedule'",
            preflight_steps["Compare scheduled deployment inputs"]["if"],
        )
        self.assertIn(
            "--github-output \"$GITHUB_OUTPUT\"",
            preflight_steps["Compare scheduled deployment inputs"]["run"],
        )

        self.assertEqual("preflight", jobs["build"]["needs"])
        self.assertEqual(
            "needs.preflight.outputs.build_required == 'true'", jobs["build"]["if"]
        )
        self.assertEqual("build", jobs["deploy"]["needs"])
        self.assertIn("github.ref == 'refs/heads/main'", jobs["deploy"]["if"])

        build_steps = {step["name"]: step for step in jobs["build"]["steps"]}
        materialize_step = build_steps["Materialize registered content sources"]
        self.assertEqual(
            "${{ inputs.source_revisions }}",
            materialize_step["env"]["SOURCE_REVISIONS"],
        )
        self.assertIn(
            'source_arguments+=(--revision "$revision")', materialize_step["run"]
        )
        self.assertIn(
            "--dashboard-ref \"${{ github.ref }}\"",
            build_steps["Validate assembled tests and docs"]["run"],
        )
        self.assertEqual(
            'cp "$RUNNER_TEMP/deployment-manifest.json" site/deployment-manifest.json',
            build_steps["Publish deployment manifest in site output"]["run"],
        )


if __name__ == "__main__":
    unittest.main()

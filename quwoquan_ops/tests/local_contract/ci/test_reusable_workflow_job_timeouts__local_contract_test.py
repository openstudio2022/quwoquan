from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]
WORKFLOWS = (
    ".github/workflows/service_pipeline.yml",
    ".github/workflows/app_pipeline.yml",
    ".github/workflows/delivery-gate.yml",
)
SUMMARY_JOBS = frozenset(
    {
        "service_pipeline_summary",
        "aggregate",
        "delivery_gate_summary",
    }
)
MAX_RUNNER_JOB_TIMEOUT_MINUTES = 40


class ReusableWorkflowJobTimeoutContractTest(unittest.TestCase):
    def test_every_runner_job_has_a_bounded_hard_timeout(self) -> None:
        checked: set[tuple[str, str]] = set()
        for relative in WORKFLOWS:
            payload = yaml.safe_load((ROOT / relative).read_text(encoding="utf-8"))
            self.assertIsInstance(payload, dict, relative)
            jobs = payload.get("jobs")
            self.assertIsInstance(jobs, dict, relative)
            for job_name, job in jobs.items():
                self.assertIsInstance(job, dict, f"{relative}:{job_name}")
                if "uses" in job:
                    continue
                self.assertIn("runs-on", job, f"{relative}:{job_name}")
                timeout = job.get("timeout-minutes")
                self.assertIs(type(timeout), int, f"{relative}:{job_name}")
                self.assertGreater(timeout, 0, f"{relative}:{job_name}")
                # App/Service integration jobs intentionally have 20-40 minute
                # hard guards; the former blanket 10 minute assertion directly
                # contradicted their reviewed, job-level timeout contracts.
                self.assertLessEqual(
                    timeout,
                    MAX_RUNNER_JOB_TIMEOUT_MINUTES,
                    f"{relative}:{job_name}",
                )
                if job_name in SUMMARY_JOBS:
                    self.assertLessEqual(timeout, 5, f"{relative}:{job_name}")
                checked.add((relative, str(job_name)))

        self.assertEqual(len(checked), 20)


if __name__ == "__main__":
    unittest.main()

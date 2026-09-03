from __future__ import annotations

import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone

from quwoquan_ops.ci.github_actions_timing import (
    APPROVAL_EVIDENCE_REASON,
    calculate,
    classify_job_attempt,
)


def job(name: str, created: str, started: str, completed: str) -> dict:
    setup_completed = (
        datetime.fromisoformat(started.replace("Z", "+00:00"))
        + timedelta(seconds=5)
    ).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "name": name,
        "conclusion": "success",
        "created_at": created,
        "started_at": started,
        "completed_at": completed,
        "steps": [
            {
                "name": "Set up job",
                "started_at": started,
                "completed_at": setup_completed,
            }
        ],
    }


class GithubActionsTimingTest(unittest.TestCase):
    def test_delivery_service_packaging_sibling_uses_parallel_max_not_sum(self) -> None:
        run = {"created_at": "2026-08-18T00:00:00Z"}
        jobs = [
            job(
                "Delivery Gate — Topology",
                "2026-08-18T00:00:00Z",
                "2026-08-18T00:00:05Z",
                "2026-08-18T00:01:41Z",
            ),
            job(
                "Delivery Gate — Service Core (L2)",
                "2026-08-18T00:01:41Z",
                "2026-08-18T00:01:41Z",
                "2026-08-18T00:16:41Z",
            ),
            job(
                "Delivery Gate — Service Packaging",
                "2026-08-18T00:01:41Z",
                "2026-08-18T00:01:41Z",
                "2026-08-18T00:15:01Z",
            ),
            job(
                "Delivery Gate — App Tests Shard 1",
                "2026-08-18T00:01:41Z",
                "2026-08-18T00:01:41Z",
                "2026-08-18T00:21:13Z",
            ),
        ]

        values = calculate(
            run,
            jobs,
            phases={
                "topology": "Delivery Gate — Topology",
                "service": "Delivery Gate — Service Core (L2)",
                "service_packaging": "Delivery Gate — Service Packaging",
                "app": "Delivery Gate — App Tests Shard",
            },
            required_counts={
                "topology": 1,
                "service": 1,
                "service_packaging": 1,
                "app": 1,
            },
            candidate_job="Delivery Gate — App Tests Shard 1",
            prod_job="",
            critical_start="run",
            dag_layers=[
                ("topology",),
                ("service", "service_packaging", "app"),
            ],
        )

        self.assertEqual(values["machine_critical_path_seconds"], 1268)
        self.assertEqual(values["calendar_lead_time_seconds"], 1273)

    def test_independent_common_branch_overlaps_topology_and_scope_branch(self) -> None:
        run = {"created_at": "2026-09-03T00:00:00Z"}
        jobs = [
            job("common", "2026-09-03T00:00:00Z", "2026-09-03T00:00:01Z", "2026-09-03T00:03:21Z"),
            job("topology", "2026-09-03T00:00:00Z", "2026-09-03T00:00:01Z", "2026-09-03T00:01:41Z"),
            job("scope", "2026-09-03T00:01:41Z", "2026-09-03T00:01:42Z", "2026-09-03T00:06:42Z"),
        ]

        values = calculate(
            run,
            jobs,
            phases={"common": "common", "topology": "topology", "scope": "scope"},
            required_counts={"common": 1, "topology": 1, "scope": 1},
            candidate_job="scope",
            prod_job="",
            critical_start="run",
            dag_layers=[],
            dag_branches=[(("common",),), (("topology",), ("scope",))],
        )

        self.assertEqual(values["machine_critical_path_seconds"], 400)

    def test_exact_data_job_does_not_capture_prefix_selected_shards(self) -> None:
        run = {"created_at": "2026-09-03T00:00:00Z"}
        jobs = [
            job(
                "Delivery Gate — Data",
                "2026-09-03T00:00:00Z",
                "2026-09-03T00:00:01Z",
                "2026-09-03T00:00:11Z",
            ),
            *[
                job(
                    f"Delivery Gate — Data Tests Shard {index}",
                    "2026-09-03T00:00:00Z",
                    "2026-09-03T00:00:01Z",
                    f"2026-09-03T00:00:{20 + index:02d}Z",
                )
                for index in range(4)
            ],
        ]

        values = calculate(
            run,
            jobs,
            phases={
                "data": "Delivery Gate — Data",
                "data_tests": "Delivery Gate — Data Tests Shard ",
            },
            required_counts={"data": 1, "data_tests": 4},
            candidate_job="",
            prod_job="",
            critical_start="run",
            dag_layers=[("data", "data_tests")],
            phase_match_modes={"data": "exact", "data_tests": "prefix"},
        )

        self.assertEqual(values["phase_data"], 10)
        self.assertEqual(values["phase_data_tests"], 22)
        self.assertEqual(values["machine_critical_path_seconds"], 22)

    def test_delivery_workflow_declares_exact_main_and_prefix_matrix_selectors(
        self,
    ) -> None:
        workflow = (
            Path(__file__).resolve().parents[4]
            / ".github/workflows/delivery-gate.yml"
        ).read_text(encoding="utf-8")

        self.assertIn(
            '--phase-exact "data=Delivery Gate — Data"', workflow
        )
        for selector in (
            "service_packaging=Delivery Gate — Service Packaging",
            "data_tests=Delivery Gate — Data Tests Shard ",
            "app_tests=Delivery Gate — App Tests Shard ",
        ):
            self.assertIn(f'--phase-prefix "{selector}"', workflow)
        self.assertNotIn('--phase "data=Delivery Gate — Data"', workflow)

    def test_official_job_and_step_timestamps_drive_longest_matrix(self) -> None:
        run = {"created_at": "2026-07-28T00:00:00Z"}
        jobs = [
            job(
                "Prepare canonical release transport",
                "2026-07-28T00:00:00Z",
                "2026-07-28T00:00:10Z",
                "2026-07-28T00:00:30Z",
            ),
            job(
                "构建 chat-service 不可变镜像",
                "2026-07-28T00:00:30Z",
                "2026-07-28T00:00:35Z",
                "2026-07-28T00:01:35Z",
            ),
            job(
                "构建 user-service 不可变镜像",
                "2026-07-28T00:00:30Z",
                "2026-07-28T00:00:36Z",
                "2026-07-28T00:01:50Z",
            ),
            job(
                "校验 Kustomize 部署",
                "2026-07-28T00:01:50Z",
                "2026-07-28T00:01:55Z",
                "2026-07-28T00:02:20Z",
            ),
        ]
        values = calculate(
            run,
            jobs,
            phases={
                "prepare": "Prepare canonical release transport",
                "images": "构建 ",
                "validate": "校验 Kustomize 部署",
            },
            required_counts={"images": 2},
            candidate_job="校验 Kustomize 部署",
            prod_job="",
            critical_start="run",
            dag_layers=[("prepare",), ("images",), ("validate",)],
        )
        self.assertEqual(values["machine_critical_path_seconds"], 119)
        self.assertEqual(values["calendar_lead_time_seconds"], 140)
        self.assertEqual(values["phase_images"], 74)
        self.assertEqual(values["queue_seconds"], 10)
        self.assertIn("setup_seconds", values)
        self.assertIn("execution_seconds", values)

    def test_missing_setup_step_is_omitted_not_zero_filled(self) -> None:
        run = {"created_at": "2026-07-28T00:00:00Z"}
        jobs = [
            {
                "name": "candidate",
                "conclusion": "success",
                "created_at": "2026-07-28T00:00:00Z",
                "started_at": "2026-07-28T00:00:10Z",
                "completed_at": "2026-07-28T00:00:20Z",
                "steps": [],
            }
        ]
        values = calculate(
            run,
            jobs,
            phases={"candidate": "candidate"},
            required_counts={"candidate": 1},
            candidate_job="candidate",
            prod_job="",
            critical_start="run",
            dag_layers=[("candidate",)],
        )
        self.assertNotIn("setup_seconds", values)
        self.assertNotIn("execution_seconds", values)
        self.assertEqual(values["queue_seconds"], 10)

    def test_missing_job_created_at_is_explicitly_incomplete_not_zero_filled(
        self,
    ) -> None:
        run = {"created_at": "2026-07-28T00:00:00Z"}
        candidate = job(
            "candidate",
            "2026-07-28T00:00:00Z",
            "2026-07-28T00:00:10Z",
            "2026-07-28T00:00:20Z",
        )
        candidate.pop("created_at")

        values = calculate(
            run,
            [candidate],
            phases={"candidate": "candidate"},
            required_counts={"candidate": 1},
            candidate_job="candidate",
            prod_job="",
            critical_start="run",
            dag_layers=[("candidate",)],
        )

        self.assertNotIn("queue_seconds", values)
        self.assertEqual(values["missing_evidence"], "githubJobs.createdAt")
        self.assertEqual(values["calendar_lead_time_seconds"], 20)
        self.assertEqual(values["machine_critical_path_seconds"], 10)

    def test_required_matrix_count_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires 2 completed jobs"):
            calculate(
                {"created_at": "2026-07-28T00:00:00Z"},
                [
                    job(
                        "candidate",
                        "2026-07-28T00:00:00Z",
                        "2026-07-28T00:00:01Z",
                        "2026-07-28T00:00:10Z",
                    )
                ],
                phases={"matrix": "matrix"},
                required_counts={"matrix": 2},
                candidate_job="candidate",
                prod_job="",
                critical_start="run",
                dag_layers=[("matrix",)],
            )

    def test_reusable_workflow_outputs_join_the_mainline_dag(self) -> None:
        run = {"created_at": "2026-07-28T00:00:00Z"}
        jobs = [
            job(
                "Resolve exact mainline source",
                "2026-07-28T00:00:00Z",
                "2026-07-28T00:00:02Z",
                "2026-07-28T00:00:12Z",
            ),
            job(
                "Seal canonical candidate and prepare promotion",
                "2026-07-28T00:02:12Z",
                "2026-07-28T00:02:14Z",
                "2026-07-28T00:02:44Z",
            ),
            job(
                "Prod rollout transaction",
                "2026-07-28T00:03:44Z",
                "2026-07-28T00:03:46Z",
                "2026-07-28T00:09:46Z",
            ),
        ]
        values = calculate(
            run,
            jobs,
            phases={
                "source": "Resolve exact mainline source",
                "seal": "Seal canonical candidate and prepare promotion",
                "prod": "Prod rollout transaction",
            },
            required_counts={"source": 1, "seal": 1, "prod": 1},
            candidate_job="Seal canonical candidate and prepare promotion",
            prod_job="Prod rollout transaction",
            critical_start="run",
            dag_layers=[
                ("source",),
                ("service", "app", "delivery"),
                ("seal",),
                ("alpha", "beta", "gamma"),
                ("prod",),
            ],
            external_phases={
                "service": 120,
                "app": 90,
                "delivery": 80,
                "alpha": 50,
                "beta": 60,
                "gamma": 40,
            },
        )
        self.assertEqual(values["machine_critical_path_seconds"], 580)
        self.assertEqual(values["calendar_lead_time_seconds"], 586)
        self.assertEqual(values["phase_service"], 120)
        self.assertNotIn("approval_requested_at", values)
        self.assertNotIn("approval_approved_at", values)
        self.assertNotIn("approval_wait_seconds", values)
        self.assertNotIn("human_decision_wait_seconds", values)
        self.assertEqual(values["approval_evidence_reason"], APPROVAL_EVIDENCE_REASON)
        self.assertIn("deployment_review", APPROVAL_EVIDENCE_REASON)
        self.assertIn("runner/concurrency queue", APPROVAL_EVIDENCE_REASON)

    def test_calendar_time_includes_waits_that_machine_dag_does_not(self) -> None:
        run = {"created_at": "2026-07-28T00:00:00Z"}
        jobs = [
            job(
                "candidate",
                "2026-07-28T00:05:00Z",
                "2026-07-28T00:10:00Z",
                "2026-07-28T00:11:00Z",
            ),
            job(
                "Prod rollout transaction",
                "2026-07-28T00:11:00Z",
                "2026-07-28T00:30:00Z",
                "2026-07-28T00:31:00Z",
            ),
        ]
        values = calculate(
            run,
            jobs,
            phases={"candidate": "candidate", "prod": "Prod rollout transaction"},
            required_counts={"candidate": 1, "prod": 1},
            candidate_job="candidate",
            prod_job="Prod rollout transaction",
            critical_start="run",
            dag_layers=[("candidate",), ("prod",)],
        )

        self.assertEqual(values["machine_critical_path_seconds"], 120)
        self.assertEqual(values["calendar_lead_time_seconds"], 1860)
        self.assertNotIn("approval_wait_seconds", values)

    def test_pr_calendar_includes_push_evidence_wait_while_machine_uses_external_phases(
        self,
    ) -> None:
        run = {"created_at": "2026-08-26T00:00:00Z"}
        jobs = [
            job(
                "Delivery Gate — Topology",
                "2026-08-26T00:00:00Z",
                "2026-08-26T00:00:01Z",
                "2026-08-26T00:01:00Z",
            ),
            job(
                "Delivery Gate — Service Core (L2)",
                "2026-08-26T00:01:00Z",
                "2026-08-26T00:01:01Z",
                "2026-08-26T00:05:00Z",
            ),
            job(
                "Delivery Gate — App (L1)",
                "2026-08-26T00:01:00Z",
                "2026-08-26T00:01:01Z",
                "2026-08-26T00:12:00Z",
            ),
        ]
        values = calculate(
            run,
            jobs,
            phases={
                "topology": "Delivery Gate — Topology",
                "service": "Delivery Gate — Service Core (L2)",
                "app_evidence": "Delivery Gate — App (L1)",
            },
            required_counts={"topology": 1, "service": 1, "app_evidence": 1},
            candidate_job="",
            prod_job="",
            critical_start="run",
            dag_layers=[
                ("topology",),
                (
                    "service",
                    "app_static",
                    "app_tests",
                    "app_serial",
                    "app_coverage",
                ),
            ],
            external_phases={
                "app_static": 120,
                "app_tests": 300,
                "app_serial": 180,
                "app_coverage": 480,
            },
        )
        self.assertEqual(values["calendar_lead_time_seconds"], 720)
        self.assertEqual(values["candidate_ready_at"], "2026-08-26T00:12:00Z")
        self.assertEqual(values["machine_critical_path_seconds"], 539)
        self.assertEqual(values["phase_app_coverage"], 480)

    def test_jobs_start_cannot_replace_official_run_start(self) -> None:
        with self.assertRaisesRegex(ValueError, "must start at workflow run"):
            calculate(
                {"created_at": "2026-07-28T00:00:00Z"},
                [
                    job(
                        "candidate",
                        "2026-07-28T00:00:10Z",
                        "2026-07-28T00:00:11Z",
                        "2026-07-28T00:00:20Z",
                    )
                ],
                phases={"candidate": "candidate"},
                required_counts={"candidate": 1},
                candidate_job="candidate",
                prod_job="",
                critical_start="jobs",
                dag_layers=[("candidate",)],
            )

    def test_job_attempt_policy_distinguishes_all_four_states(self) -> None:
        attempted = job(
            "attempted", "2026-07-28T00:00:00Z",
            "2026-07-28T00:00:01Z", "2026-07-28T00:00:02Z"
        )
        runnable = {"name": "runnable", "status": "queued", "conclusion": None}
        skipped = {"name": "skipped", "status": "completed", "conclusion": "skipped"}
        infra = {"name": "infra", "status": "completed", "conclusion": "timed_out"}
        self.assertEqual(classify_job_attempt(attempted), "attempted")
        self.assertEqual(classify_job_attempt(runnable), "runnable")
        self.assertEqual(classify_job_attempt(skipped), "skipped")
        self.assertEqual(classify_job_attempt(infra), "infra")

    def test_calculation_exposes_attempt_classification_counts(self) -> None:
        attempted = job(
            "candidate", "2026-07-28T00:00:00Z",
            "2026-07-28T00:00:01Z", "2026-07-28T00:00:02Z"
        )
        values = calculate(
            {"created_at": "2026-07-28T00:00:00Z"},
            [attempted, {"name": "typed skip", "status": "completed", "conclusion": "skipped"}],
            phases={"candidate": "candidate"}, required_counts={"candidate": 1},
            candidate_job="candidate", prod_job="", critical_start="run",
            dag_layers=[("candidate",)],
        )
        self.assertEqual(values["jobs_attempted"], 1)
        self.assertEqual(values["jobs_skipped"], 1)
        self.assertEqual(values["jobs_runnable"], 0)
        self.assertEqual(values["jobs_infra"], 0)


if __name__ == "__main__":
    unittest.main()

"""Review Board v2 bounded-dispatch contract.

# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-003.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-003.t2
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-003.t3
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-004.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-004.t2
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-004.t3
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-006.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-006.t2
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest import mock

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[4]
_CLI = _REPO_ROOT / "quwoquan_ops/cli/review_dispatch.py"
_REGISTRY = _REPO_ROOT / ".agents/skills/review/references/registry.yaml"
_GOVERNANCE_CONTRACT = _REPO_ROOT / "quwoquan_ops/policies/agent_governance_contract.yaml"
_OUTPUT_ROOT = _REPO_ROOT / ".qwq_output/env/repo/local/review-dispatch-tests"


def _load_cli() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_review_dispatch", _CLI)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_cli = _load_cli()
_registry = yaml.safe_load(_REGISTRY.read_text(encoding="utf-8"))
_governance_contract = yaml.safe_load(_GOVERNANCE_CONTRACT.read_text(encoding="utf-8"))


def _plan(
    workflow: str,
    segment: str,
    paths: list[str],
    deliverable: str | None = None,
    **kwargs: object,
) -> dict:
    return _cli.build_plan(
        _registry,
        workflow,
        segment,
        deliverable,
        paths,
        **kwargs,
    )


def _context_manifest(
    *contexts: dict[str, str | None],
) -> dict[str, object]:
    return {
        "schema_version": _governance_contract["feature_context_manifest"][
            "schema_version"
        ],
        "target": "README.md",
        "resolved_owner": "specs/feature-tree/spec.md",
        "owner_chain": [
            {
                "level": 0,
                "node_id": "app-root",
                "path": "specs/feature-tree/spec.md",
            }
        ],
        "canonical_contexts": list(contexts),
        "applicable_agents": ["AGENTS.md"],
        "profiles": [],
        "open_items": [],
    }


class ReviewDispatchBoundedAssemblyTest(unittest.TestCase):
    def test_plan_and_terminal_shapes_follow_canonical_contract(self) -> None:
        plan = _plan(
            "dev",
            "POST",
            ["README.md"],
            context_manifest=_context_manifest(
                {"path": "README.md", "anchor": None, "kind": "spec"}
            ),
        )
        self.assertEqual(
            set(_governance_contract["review_plan"]["required_fields"]),
            set(plan),
        )
        self.assertEqual(2, _governance_contract["review_plan"]["schema_version"])
        for field, declaration in (
            ("contexts", "context_fields"),
            ("reviewers", "reviewer_fields"),
            ("evidence", "evidence_fields"),
        ):
            for item in plan[field]:
                self.assertEqual(
                    set(_governance_contract["review_plan"][declaration]),
                    set(item),
                )
        self.assertEqual(
            set(_governance_contract["review_plan"]["context_bytes_fields"]),
            set(plan["context_bytes"]),
        )
        self.assertEqual(
            set(_governance_contract["review_plan"]["terminal_fields"]),
            set(plan["terminal"]),
        )
        for code, terminal in _governance_contract["terminal_codes"].items():
            with self.subTest(code=code):
                self.assertIn(terminal["severity"], {"GATE_BLOCK", "PR_WARN"})
                self.assertIs(terminal["automatic_retry"], False)
                self.assertTrue(terminal["recovery"])

    def test_contract_inner_field_drift_fails_closed(self) -> None:
        # GWT-002.t1 / GWT-004.t1
        contract_module = sys.modules[_cli.declared_object.__module__]
        original = contract_module.declared_fields

        def drift(section: str, declaration: str) -> tuple[str, ...]:
            fields = original(section, declaration)
            if section == "review_plan" and declaration == "fingerprint_inputs":
                return (*fields, "new_undeclared_input")
            return fields

        with (
            mock.patch.object(contract_module, "declared_fields", side_effect=drift),
            self.assertRaisesRegex(ValueError, "fingerprint_inputs"),
        ):
            _plan("dev", "POST", ["README.md"])

        def context_drift(section: str, declaration: str) -> tuple[str, ...]:
            fields = original(section, declaration)
            if section == "review_plan" and declaration == "context_fields":
                return (*fields, "new_context_field")
            return fields

        with (
            mock.patch.object(
                contract_module,
                "declared_fields",
                side_effect=context_drift,
            ),
            self.assertRaisesRegex(ValueError, "context_fields"),
        ):
            _plan(
                "dev",
                "POST",
                ["README.md"],
                context_manifest=_context_manifest(
                    {"path": "README.md", "anchor": None, "kind": "spec"}
                ),
            )

    def test_manifest_and_previous_plan_inputs_fail_closed(self) -> None:
        legacy_manifest = {
            "contexts": [{"path": "README.md", "anchor": None, "kind": "spec"}]
        }
        with self.assertRaises(_cli.ReviewDispatchError) as legacy:
            _plan(
                "dev",
                "POST",
                ["README.md"],
                context_manifest=legacy_manifest,
            )
        self.assertEqual("REVIEW.CONTEXT_MANIFEST_INVALID", legacy.exception.code)

        version_drift = _context_manifest(
            {"path": "README.md", "anchor": None, "kind": "spec"}
        )
        version_drift["schema_version"] = 999
        with self.assertRaises(_cli.ReviewDispatchError) as invalid_manifest:
            _plan(
                "dev",
                "POST",
                ["README.md"],
                context_manifest=version_drift,
            )
        self.assertEqual(
            "REVIEW.CONTEXT_MANIFEST_INVALID",
            invalid_manifest.exception.code,
        )

        initial = _plan("dev", "POST", ["README.md"])
        invalid_previous = json.loads(json.dumps(initial))
        invalid_previous["schema_version"] = 1
        with self.assertRaises(_cli.ReviewDispatchError) as previous:
            _plan(
                "dev",
                "POST",
                ["README.md"],
                round_name="rereview",
                finding_owners=["developer"],
                previous_plan=invalid_previous,
            )
        self.assertEqual("REVIEW.PREVIOUS_PLAN_INVALID", previous.exception.code)

    def test_pre_has_zero_reviewers_and_zero_evidence(self) -> None:
        # GWT-003.t1
        for workflow, path in (
            ("prd", "specs/feature-tree/runtime/spec.md"),
            ("design", "specs/feature-tree/runtime/design.md"),
            ("dev", "quwoquan_app/lib/design_system/pageflip/example.dart"),
            ("environment-ops", "quwoquan_ops/environments/prod/example.yaml"),
            ("content-production", "quwoquan_data/example.py"),
        ):
            with self.subTest(workflow=workflow):
                plan = _plan(workflow, "PRE", [path])
                self.assertEqual([], plan["reviewers"])
                self.assertEqual([], plan["evidence"])
                self.assertEqual(0, plan["invocation_count"])

    def test_pageflip_and_python_gate_have_only_primary_and_one_specialist(self) -> None:
        # GWT-003.t1
        pageflip = _plan(
            "dev",
            "POST",
            ["quwoquan_app/lib/design_system/pageflip/backward_render_frame_builder.dart"],
        )
        self.assertEqual(
            ["developer", "ux"], [item["role"] for item in pageflip["reviewers"]]
        )
        self.assertEqual(
            ["app-pageflip-back-mainline"],
            [item["id"] for item in pageflip["evidence"]],
        )
        self.assertEqual(
            ["make verify-app-pageflip-back-mainline"],
            [item["command"] for item in pageflip["evidence"]],
        )
        self.assertEqual(
            ["pageflip-backward-static", "pageflip-backward-tests"],
            pageflip["evidence"][0]["covers"],
        )

        python_gate = _plan(
            "dev",
            "POST",
            ["quwoquan_ops/gate/verify_agent_context_budget.py"],
        )
        self.assertEqual(
            ["developer", "ops"],
            [item["role"] for item in python_gate["reviewers"]],
        )
        self.assertEqual(["agent-context-budget"], [item["id"] for item in python_gate["evidence"]])
        self.assertNotIn(
            "app-",
            " ".join(item["command"] for item in python_gate["evidence"]),
        )

    def test_ordinary_and_nonautomatic_workflows_are_bounded(self) -> None:
        # GWT-003.t2
        ordinary = _plan("dev", "POST", ["README.md"])
        self.assertEqual(["developer"], [item["role"] for item in ordinary["reviewers"]])
        for workflow in ("explore", "plan-next", "continue", "review", "commit"):
            with self.subTest(workflow=workflow):
                plan = _plan(workflow, "POST", ["README.md"])
                self.assertEqual([], plan["reviewers"])
                self.assertEqual([], plan["evidence"])
        for path in (
            "quwoquan_app/lib/design_system/pageflip/example.dart",
            "quwoquan_service/services/user-service/example.go",
            "quwoquan_ops/environments/prod/example.yaml",
        ):
            self.assertLessEqual(len(_plan("dev", "POST", [path])["reviewers"]), 2)

    def test_multi_profile_selection_is_deterministic_and_uses_highest_priority(self) -> None:
        # GWT-003.t2
        path = "quwoquan_app/lib/service/recommendation_service/feed/presentation/page.dart"
        first = _plan("dev", "POST", [path])
        second = _plan("dev", "POST", [path])
        self.assertEqual(
            ["developer", "recommendation"],
            [item["role"] for item in first["reviewers"]],
        )
        self.assertEqual(first["profiles"], second["profiles"])
        self.assertEqual(first["reviewers"], second["reviewers"])

        tied = _plan(
            "dev",
            "POST",
            [
                "quwoquan_app/lib/runtime/example.dart",
                "quwoquan_service/services/user-service/example.go",
            ],
        )
        self.assertEqual(
            ["developer", "test"],
            [item["role"] for item in tied["reviewers"]],
        )
        self.assertEqual("dart-app", tied["reviewers"][1]["profile"])
        self.assertEqual(
            "roles/test/checklists/dev/app.md",
            tied["reviewers"][1]["checklist"],
        )

    def test_named_evidence_is_deduplicated_by_id(self) -> None:
        # GWT-004.t1: product and UX both reference feature-tree.
        plan = _plan("prd", "POST", [], deliverable="page")
        self.assertEqual(["product", "ux"], [item["role"] for item in plan["reviewers"]])
        self.assertEqual(["feature-tree"], [item["id"] for item in plan["evidence"]])
        self.assertEqual(
            ["product", "ux"],
            plan["evidence"][0]["consumers"],
        )

    def test_fingerprint_covers_tracked_untracked_deleted_and_content_change(self) -> None:
        # GWT-004.t1
        tracked = _cli._snapshot_path(
            ".agents/skills/review/references/registry.yaml"
        )
        self.assertTrue(tracked["tracked"])
        with (
            mock.patch.object(_cli, "_is_tracked", return_value=True),
            mock.patch.object(_cli, "_exists_at_head", return_value=True),
            mock.patch.object(_cli, "_head_blob_digest", return_value="head-digest"),
        ):
            deleted = _cli._snapshot_path(
                ".qwq_output/env/repo/local/review-dispatch-tests/deleted.txt"
            )
            self.assertEqual("deleted", deleted["state"])
            self.assertEqual("head-digest", deleted["content_digest"])

        _OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=_OUTPUT_ROOT) as directory:
            path = Path(directory) / "untracked.txt"
            path.write_text("first\n", encoding="utf-8")
            relative = path.relative_to(_REPO_ROOT).as_posix()
            first = _plan("dev", "POST", [relative])
            self.assertFalse(_cli._snapshot_path(relative)["tracked"])
            path.write_text("second\n", encoding="utf-8")
            second = _plan("dev", "POST", [relative])
            self.assertNotEqual(first["fingerprint"], second["fingerprint"])

    def test_rereview_is_finding_owner_only_and_never_exceeds_four_calls(self) -> None:
        # GWT-004.t2
        path = "quwoquan_app/lib/design_system/pageflip/example.dart"
        initial = _plan("dev", "POST", [path], scope="pageflip")
        rereview = _plan(
            "dev",
            "POST",
            [path],
            scope="pageflip",
            round_name="rereview",
            finding_owners=["developer", "ux"],
            previous_plan=initial,
        )
        self.assertEqual(
            ["developer", "ux"],
            [item["role"] for item in rereview["reviewers"]],
        )
        self.assertEqual(4, rereview["invocation_count"])
        self.assertLessEqual(rereview["invocation_count"], 4)

    def test_invalid_rereview_inputs_are_typed_refusals(self) -> None:
        # GWT-004.t2
        path = "quwoquan_app/lib/design_system/pageflip/example.dart"
        initial = _plan("dev", "POST", [path])
        with self.assertRaises(_cli.ReviewDispatchError) as invalid_owner:
            _plan(
                "dev",
                "POST",
                [path],
                round_name="rereview",
                finding_owners=["architect"],
                previous_plan=initial,
            )
        self.assertEqual("REVIEW.INVALID_FINDING_OWNER", invalid_owner.exception.code)

        first_rereview = _plan(
            "dev",
            "POST",
            [path],
            round_name="rereview",
            finding_owners=["ux"],
            previous_plan=initial,
        )
        with self.assertRaises(_cli.ReviewDispatchError) as third_round:
            _plan(
                "dev",
                "POST",
                [path],
                round_name="rereview",
                finding_owners=["ux"],
                previous_plan=first_rereview,
            )
        self.assertEqual("REVIEW.REREVIEW_CHAIN_FORBIDDEN", third_round.exception.code)

        with self.assertRaises(_cli.ReviewDispatchError) as changed_scope:
            _plan(
                "dev",
                "POST",
                [path],
                scope="different",
                round_name="rereview",
                finding_owners=["ux"],
                previous_plan=initial,
            )
        self.assertEqual("REVIEW.NEW_REVIEW_REQUIRED", changed_scope.exception.code)

    def test_fingerprint_change_invalidates_evidence_without_expanding_reviewers(self) -> None:
        # GWT-004.t1 / GWT-004.t2
        _OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=_OUTPUT_ROOT) as directory:
            path = Path(directory) / "fix.py"
            path.write_text("before\n", encoding="utf-8")
            relative = path.relative_to(_REPO_ROOT).as_posix()
            initial = _plan("dev", "POST", [relative])
            path.write_text("after\n", encoding="utf-8")
            rereview = _plan(
                "dev",
                "POST",
                [relative],
                round_name="rereview",
                finding_owners=["developer"],
                previous_plan=initial,
            )
            self.assertFalse(rereview["evidence_reusable"])
            self.assertIn(
                "REVIEW.FINGERPRINT_CHANGED",
                [item["code"] for item in rereview["invalidations"]],
            )
            self.assertEqual(["developer"], [item["role"] for item in rereview["reviewers"]])

    def test_incomplete_and_evidence_failures_have_typed_terminals(self) -> None:
        # GWT-006.t1 / GWT-006.t2
        path = "quwoquan_app/lib/design_system/pageflip/example.dart"
        optional = _plan(
            "dev",
            "POST",
            [path],
            incomplete_roles=[{"role": "ux", "reason": "timeout"}],
        )
        self.assertEqual("PR_WARN", optional["terminal"]["status"])
        self.assertIn(
            "REVIEW.OPTIONAL_REVIEWER_INCOMPLETE", optional["terminal"]["codes"]
        )
        required = _plan(
            "dev",
            "POST",
            [path],
            incomplete_roles=[{"role": "developer", "reason": "resource_exhausted"}],
        )
        self.assertEqual("GATE_BLOCK", required["terminal"]["status"])
        self.assertIn(
            "REVIEW.REQUIRED_REVIEWER_INCOMPLETE", required["terminal"]["codes"]
        )
        evidence = _plan(
            "dev",
            "POST",
            [path],
            failed_evidence_ids=["app-pageflip-back-mainline"],
        )
        self.assertEqual("GATE_BLOCK", evidence["terminal"]["status"])
        self.assertIn("REVIEW.EVIDENCE_FAILED", evidence["terminal"]["codes"])
        self.assertEqual([], evidence["reviewers"])
        self.assertEqual(0, evidence["invocation_count"])
        self.assertEqual(
            ["developer", "ux"],
            [item["role"] for item in evidence["skipped_reviewers"]],
        )

    def test_plan_fields_context_budget_and_old_cli_arguments_remain_supported(self) -> None:
        plan = _plan("dev", "POST", ["README.md"])
        required_fields = {
            "contexts",
            "reviewers",
            "evidence",
            "fingerprint",
            "invocation_count",
            "context_bytes",
            "incomplete_roles",
        }
        self.assertLessEqual(required_fields, set(plan))
        self.assertLessEqual(plan["context_bytes"]["max_reviewer"], 24576)

        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(_CLI),
                "--workflow",
                "dev",
                "--segment",
                "POST",
                "--changed-paths",
                "README.md",
            ],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(2, json.loads(result.stdout)["schema_version"])

    def test_cli_refuses_runtime_output_outside_canonical_root(self) -> None:
        forbidden = "specs/feature-tree/runtime/review-dispatch-forbidden-output"
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(_CLI),
                "--workflow",
                "dev",
                "--segment",
                "POST",
                "--changed-paths",
                "README.md",
                "--out",
                forbidden,
            ],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("REVIEW.OUTPUT_PATH_OUTSIDE_RUNTIME_ROOT", result.stderr)
        self.assertFalse((_REPO_ROOT / forbidden).exists())


if __name__ == "__main__":
    unittest.main()

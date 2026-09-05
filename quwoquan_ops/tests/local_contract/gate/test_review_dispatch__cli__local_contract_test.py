"""Review Board v2 bounded-dispatch contract.

# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-003.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-003.t2
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-003.t3
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-004.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-004.t2
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-004.t3
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-006.t1
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-006.t2
# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-006.t3
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest import mock

import yaml

from quwoquan_ops.cli.lib.evidence_fingerprint import canonical_json_bytes
from quwoquan_ops.cli.lib.candidate_evidence import build_candidate_evidence

_REPO_ROOT = Path(__file__).resolve().parents[4]
_CLI = _REPO_ROOT / "quwoquan_ops/cli/review_dispatch.py"
_REGISTRY = _REPO_ROOT / ".agents/skills/review/references/registry.yaml"
_GOVERNANCE_CONTRACT = _REPO_ROOT / "quwoquan_ops/policies/agent_governance_contract.yaml"
_OUTPUT_ROOT = _REPO_ROOT / ".qwq_output/env/repo/local/review-dispatch-tests"
_MANIFEST_REFS: dict[int, str] = {}


def _owner_manifest_ref(raw: bytes) -> str:
    prefix = ".qwq_output/env/repo/runs/feature-tree/by-fingerprint/"
    return prefix + hashlib.sha256(raw).hexdigest() + ".json"


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

from lib.feature_tree.nodes import discover_nodes as _discover_feature_nodes

_DISCOVERED_NODES = tuple(_discover_feature_nodes())


def _write_owner_fixture(manifest: dict[str, object]) -> str:
    raw = canonical_json_bytes(manifest)
    root = _REPO_ROOT / ".qwq_output/env/repo/runs/feature-tree/by-fingerprint"
    root.mkdir(parents=True, exist_ok=True)
    path = root / (hashlib.sha256(raw).hexdigest() + ".json")
    path.write_bytes(raw)
    ref = path.relative_to(_REPO_ROOT).as_posix()
    _MANIFEST_REFS[id(manifest)] = ref
    return ref


def _plan(
    workflow: str, segment: str, paths: list[str],
    deliverable: str | None = None, **kwargs: object,
) -> dict:
    auto_identity = bool(kwargs.pop("auto_identity", True))
    automatic = _registry["workflows"][workflow].get("automatic_review") is not False
    previous = kwargs.get("previous_plan")
    if isinstance(previous, dict) and "context_manifest_ref" not in kwargs:
        owner_ref = (previous.get("owner_identity") or {}).get("ref")
        if isinstance(owner_ref, str) and owner_ref:
            kwargs["context_manifest_ref"] = owner_ref
            kwargs["context_manifest"] = json.loads((_REPO_ROOT / owner_ref).read_text(encoding="utf-8"))
    if segment == "POST" and automatic and auto_identity and "context_manifest" not in kwargs:
        exact_target = paths[0] if paths else "specs/feature-tree/spec.md"
        if exact_target.startswith(".qwq_output/"):
            exact_target = "README.md"
        from lib.feature_tree.nodes import parent_chain
        from lib.feature_tree.ownership import resolve_target_details
        discovered = _DISCOVERED_NODES
        resolution = resolve_target_details(exact_target, discovered)
        by_dir = {node.directory.resolve(): node for node in discovered}
        manifest = {
            "schema_version": _governance_contract["feature_context_manifest"]["schema_version"],
            "target": resolution.target.resolve().relative_to(_REPO_ROOT.resolve()).as_posix(),
            "resolved_owner": resolution.node.rel,
            "owner_chain": [
                {"level": item.level, "node_id": item.node_id, "path": item.rel}
                for item in parent_chain(resolution.node, by_dir)
            ],
            "canonical_contexts": [{"path": resolution.node.rel, "anchor": None, "kind": "spec"}],
            "applicable_agents": ["AGENTS.md"],
            "open_items": [],
        }
        manifest["evidence_fingerprint"] = _cli.embedded_fingerprint_binding(
            _cli.build_feature_context_fingerprint(manifest, repo_root=_REPO_ROOT)
        )
        kwargs["context_manifest"] = manifest
        kwargs["context_manifest_ref"] = _write_owner_fixture(manifest)
    manifest = kwargs.get("context_manifest")
    if isinstance(manifest, dict) and "context_manifest_ref" not in kwargs:
        ref = _MANIFEST_REFS.get(id(manifest)) or _write_owner_fixture(manifest)
        kwargs["context_manifest_ref"] = ref
    candidate_override = kwargs.pop("candidate_paths", None)
    candidate_paths = list(candidate_override or paths or ([str(manifest.get("target"))] if isinstance(manifest, dict) else []))
    review_paths = candidate_paths if candidate_override is not None else paths
    if candidate_paths and candidate_paths[0].startswith(".qwq_output/"):
        candidate_paths = [str(manifest.get("target"))]
    if segment == "POST" and automatic and auto_identity and "candidate_evidence_ref" not in kwargs:
        ref = kwargs.get("context_manifest_ref")
        if isinstance(ref, str):
            candidate = build_candidate_evidence(ref, candidate_paths, repo_root=_REPO_ROOT)
            candidate_raw = canonical_json_bytes(candidate)
            candidate_path = (_REPO_ROOT / ".qwq_output/env/repo/runs/feature-tree/by-fingerprint/candidates/by-fingerprint" / (hashlib.sha256(candidate_raw).hexdigest() + ".json"))
            candidate_path.parent.mkdir(parents=True, exist_ok=True)
            candidate_path.write_bytes(candidate_raw)
            kwargs["candidate_evidence_ref"] = candidate_path.relative_to(_REPO_ROOT).as_posix()
    return _cli.build_plan(_registry, workflow, segment, deliverable, review_paths, **kwargs)


def _context_manifest(*contexts: dict[str, str | None]) -> dict[str, object]:
    from lib.feature_tree.commands import _context_manifest as build_manifest
    from lib.feature_tree.ownership import resolve_target_details
    nodes = _DISCOVERED_NODES
    manifest = build_manifest("README.md", resolve_target_details("README.md", nodes), nodes)
    existing = list(manifest["canonical_contexts"])
    for item in contexts:
        if item not in existing:
            existing.append(item)
    manifest["canonical_contexts"] = existing
    manifest["evidence_fingerprint"] = _cli.embedded_fingerprint_binding(
        _cli.build_feature_context_fingerprint(manifest, repo_root=_REPO_ROOT)
    )
    _write_owner_fixture(manifest)
    return manifest


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
        self.assertEqual(5, _governance_contract["review_plan"]["schema_version"])
        self.assertNotIn("fingerprint_inputs", _governance_contract["review_plan"])
        self.assertEqual(
            "canonical-evidence-fingerprint-receipt",
            _governance_contract["review_plan"]["fingerprint_identity"],
        )
        self.assertRegex(plan["fingerprint"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(
            plan["fingerprint"], plan["fingerprint_receipt"]["digest"]
        )
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
                auto_identity=False,
            )
        self.assertEqual("IDENTITY.MIGRATION_REQUIRED", legacy.exception.code)

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
                auto_identity=False,
            )
        self.assertEqual(
            "IDENTITY.MIGRATION_REQUIRED",
            invalid_manifest.exception.code,
        )

        stale_manifest = _context_manifest(
            {"path": "README.md", "anchor": None, "kind": "spec"}
        )
        stale_manifest["target"] = "AGENTS.md"
        with self.assertRaises(_cli.ReviewDispatchError) as stale:
            _plan(
                "dev",
                "POST",
                ["README.md"],
                context_manifest=stale_manifest,
                auto_identity=False,
            )
        self.assertEqual("REVIEW.OWNER_MANIFEST_STALE", stale.exception.code)

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
            ["review-baseline", "code-health-delta", "app-pageflip-back-mainline"],
            [item["id"] for item in pageflip["evidence"]],
        )
        self.assertEqual(
            ["python3 -B quwoquan_ops/gate/verify_review_baseline.py", "python3 -B quwoquan_ops/gate/verify_review_code_health.py", "make verify-app-pageflip-back-mainline"],
            [item["command"] for item in pageflip["evidence"]],
        )
        self.assertEqual(
            ["pageflip-backward-static", "pageflip-backward-tests"],
            pageflip["evidence"][2]["covers"],
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
        self.assertEqual(
            ["review-baseline", "code-health-delta", "portal-test", "portal-build"],
            [item["id"] for item in python_gate["evidence"]],
        )
        self.assertNotIn(
            "agent-context-budget", [item["id"] for item in python_gate["evidence"]]
        )
        self.assertNotIn(
            "app-",
            " ".join(item["command"] for item in python_gate["evidence"]),
        )

    def test_ordinary_and_nonautomatic_workflows_are_bounded(self) -> None:
        # GWT-003.t2
        ordinary = _plan("dev", "POST", ["README.md"])
        self.assertEqual(["developer"], [item["role"] for item in ordinary["reviewers"]])
        self.assertEqual(
            ["review-baseline", "code-health-delta"],
            [item["id"] for item in ordinary["evidence"]],
        )
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

        tied = _plan("dev", "POST", ["quwoquan_app/lib/runtime/example.dart"])
        self.assertEqual(["developer", "test"], [item["role"] for item in tied["reviewers"]])
        self.assertEqual("dart-app", tied["reviewers"][1]["profile"])

    def test_governance_profiles_outrank_recommendation_for_mixed_worktree(self) -> None:
        governance_paths = (
            "quwoquan_ops/ci/local_readiness_planner.py",
            "quwoquan_ops/cli/lib/hosted_authority/client.py",
            "quwoquan_ops/cli/objective_execution.py",
            "quwoquan_ops/gate/verify_governance_pipeline_admission.py",
            "quwoquan_service/control-plane/platform-ops/cmd/api/main.go",
            "quwoquan_ops/portal/src/domains/platform/HumanAuthorityPage.tsx",
            "specs/feature-tree/runtime/runtime-control-plane-foundation/human-authority-role-cards/spec.md",
        )
        recommendation_path = (
            "quwoquan_service/services/recommendation-service/"
            "generated/recommendation/recommendation_model_release/"
            "control_plane/portal_menu.py"
        )

        for governance_path in governance_paths:
            with self.subTest(path=governance_path):
                plan = _plan(
                    "dev",
                    "POST",
                    [governance_path],
                )
                self.assertEqual(
                    ["developer", "ops"],
                    [item["role"] for item in plan["reviewers"]],
                )
                self.assertEqual("gate", plan["reviewers"][1]["profile"])
                self.assertEqual(
                    ["review-baseline", "code-health-delta", "portal-test", "portal-build"],
                    [item["id"] for item in plan["evidence"]],
                )
                self.assertLessEqual(len(plan["reviewers"]), 2)

    def test_governance_tests_have_one_public_make_owner_outside_commit_fast_path(self) -> None:
        source = (_REPO_ROOT / "Makefile").read_text(encoding="utf-8")
        expected = {
            "quwoquan_ops/tests/local_contract/gate/test_review_dispatch__cli__local_contract_test.py":
                "test-review-dispatch",
            "quwoquan_ops/tests/local_contract/gate/test_hosted_authority_adapter__local_contract_test.py":
                "test-hosted-authority-adapter-local-contract",
            "quwoquan_ops/tests/local_contract/gate/test_governance_pipeline_admission__evidence_bundle__local_contract_test.py":
                "test-governance-pipeline-admission",
            "quwoquan_ops/tests/local_contract/ci/test_delivery_gate_ci_bootstrap__local_contract_test.py":
                "test-delivery-ci-local-contract",
            "quwoquan_ops/tests/local_contract/ci/test_hosted_ci_timing_ledger__local_contract_test.py":
                "test-delivery-ci-local-contract",
        }

        def target_block(name: str) -> str:
            start = source.index(f"\n{name}:")
            recipe_start = source.index("\n", start + 1) + 1
            match = re.search(
                r"(?m)^[-A-Za-z0-9_.%]+\s*:", source[recipe_start:]
            )
            end = recipe_start + match.start() if match else len(source)
            return source[start:end]

        gate_header = next(
            line
            for line in source.splitlines()
            if line.startswith("test-gate-companion-local-contract:")
        )
        for public_target in {
            "test-review-dispatch",
            "test-hosted-authority-adapter-local-contract",
            "test-governance-pipeline-admission",
            "test-delivery-ci-local-contract",
        }:
            self.assertIn(public_target, gate_header)

        for path, owner in expected.items():
            with self.subTest(path=path):
                self.assertEqual(1, source.count(path))
                self.assertIn(path, target_block(owner))

        commit_fast_path = (
            _REPO_ROOT / "quwoquan_ops/gate/commit_gate.sh"
        ).read_text(encoding="utf-8")
        self.assertNotIn("test-delivery-ci-local-contract", commit_fast_path)
        self.assertNotIn(
            "test-hosted-authority-adapter-local-contract", commit_fast_path
        )
        self.assertNotIn("test-governance-pipeline-admission", commit_fast_path)

    def test_named_evidence_is_deduplicated_by_id(self) -> None:
        # GWT-004.t1: product and UX both reference feature-tree.
        plan = _plan("prd", "POST", ["README.md"], deliverable="page")
        self.assertEqual(["product", "ux"], [item["role"] for item in plan["reviewers"]])
        self.assertEqual(
            ["review-baseline", "feature-tree"],
            [item["id"] for item in plan["evidence"]],
        )
        self.assertEqual(
            ["product", "ux"],
            plan["evidence"][1]["consumers"],
        )
        for evidence in plan["evidence"]:
            self.assertRegex(evidence["command_digest"], r"^sha256:[0-9a-f]{64}$")

    def test_fingerprint_covers_tracked_untracked_deleted_and_content_change(self) -> None:
        # GWT-004.t1
        tracked = _cli._snapshot_path(
            ".agents/skills/review/references/registry.yaml"
        )
        self.assertTrue(tracked["tracked"])
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            source = repo / "deleted.txt"
            source.write_text("before\n", encoding="utf-8")
            subprocess.run(["git", "add", "deleted.txt"], cwd=repo, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Fixture",
                    "-c",
                    "user.email=fixture@example.invalid",
                    "commit",
                    "-qm",
                    "fixture",
                ],
                cwd=repo,
                check=True,
            )
            source.unlink()
            deleted = _cli.snapshot_path("deleted.txt", repo_root=repo)
            self.assertEqual("deleted", deleted["state"])
            self.assertTrue(deleted["content_digest"].startswith("sha256:"))

        _OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=_REPO_ROOT / "quwoquan_ops/cli") as directory:
            path = Path(directory) / "untracked.txt"
            path.write_text("first\n", encoding="utf-8")
            relative = path.relative_to(_REPO_ROOT).as_posix()
            first = _plan("dev", "POST", [relative])
            self.assertFalse(_cli._snapshot_path(relative)["tracked"])
            path.write_text("second\n", encoding="utf-8")
            second = _plan("dev", "POST", [relative])
            self.assertNotEqual(first["fingerprint"], second["fingerprint"])

    def test_legacy_fingerprint_is_never_consumed_for_rereview(self) -> None:
        initial = _plan("dev", "POST", ["README.md"])
        legacy = json.loads(json.dumps(initial))
        legacy["fingerprint"] = "0" * 64
        with self.assertRaises(_cli.ReviewDispatchError) as previous:
            _plan(
                "dev",
                "POST",
                ["README.md"],
                round_name="rereview",
                finding_owners=["developer"],
                previous_plan=legacy,
            )
        self.assertEqual("REVIEW.PREVIOUS_PLAN_INVALID", previous.exception.code)

    def test_canonical_digest_is_stable_across_receipt_capture_time(self) -> None:
        first = _cli._fingerprint_receipt(
            workflow="dev",
            deliverable="code",
            scope="",
            owner_identity={"ref": None, "canonical_bytes_sha256": None, "target": "", "scope": "", "resolved_owner": "", "fingerprint_ref": None, "fingerprint_digest": None},
            candidate_evidence_identity={"ref": None, "canonical_bytes_sha256": None, "schema_version": None, "owner_identity_ref": None, "delivery_owner": None, "lead_lane": None, "delivery_policy_digests": None, "target": "", "resolved_owner": "", "impacted_owner_groups_digest": None, "changed_paths_digest": None, "workspace_digests": None, "fingerprint_ref": None, "fingerprint_digest": None, "impact_plan_ref": None, "impact_plan_digest": None},
            terminal={"status": "READY", "codes": [], "failed_evidence": []},
            changed_paths=["README.md"],
            profiles=[],
            contexts=[],
            initial_reviewers=[],
            evidence=[],
        )
        second = _cli._fingerprint_receipt(
            workflow="dev",
            deliverable="code",
            scope="",
            owner_identity={"ref": None, "canonical_bytes_sha256": None, "target": "", "scope": "", "resolved_owner": "", "fingerprint_ref": None, "fingerprint_digest": None},
            candidate_evidence_identity={"ref": None, "canonical_bytes_sha256": None, "schema_version": None, "owner_identity_ref": None, "delivery_owner": None, "lead_lane": None, "delivery_policy_digests": None, "target": "", "resolved_owner": "", "impacted_owner_groups_digest": None, "changed_paths_digest": None, "workspace_digests": None, "fingerprint_ref": None, "fingerprint_digest": None, "impact_plan_ref": None, "impact_plan_digest": None},
            terminal={"status": "READY", "codes": [], "failed_evidence": []},
            changed_paths=["README.md"],
            profiles=[],
            contexts=[],
            initial_reviewers=[],
            evidence=[],
        )
        self.assertEqual(first["digest"], second["digest"])
        self.assertEqual(
            "review_plan.fingerprint", first["captured_metadata"]["consumer"]
        )

    def test_review_fingerprint_binds_symlink_target_content_and_broken_state(self) -> None:
        _OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=_REPO_ROOT / "quwoquan_ops/cli") as directory:
            root = Path(directory)
            target = root / "target.txt"
            link = root / "link.txt"
            target.write_text("first\n", encoding="utf-8")
            link.symlink_to("target.txt")
            relative = link.relative_to(_REPO_ROOT).as_posix()
            first = _plan("dev", "POST", [relative])
            target.write_text("second\n", encoding="utf-8")
            second = _plan("dev", "POST", [relative])
            target.unlink()
            broken = _plan("dev", "POST", [relative])
            self.assertNotEqual(first["fingerprint"], second["fingerprint"])
            self.assertNotEqual(second["fingerprint"], broken["fingerprint"])

    def test_rereview_is_finding_owner_only_and_never_exceeds_four_calls(self) -> None:
        # GWT-004.t2
        path = "quwoquan_app/lib/design_system/pageflip/example.dart"
        initial = _plan("dev", "POST", [path], scope=path)
        rereview = _plan(
            "dev",
            "POST",
            [path],
            scope=path,
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
        self.assertEqual(
            "REVIEW.OWNER_MANIFEST_SCOPE_MISMATCH",
            changed_scope.exception.code,
        )

    def test_fingerprint_change_invalidates_evidence_without_expanding_reviewers(self) -> None:
        # GWT-004.t1 / GWT-004.t2
        _OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=_REPO_ROOT / "quwoquan_ops/cli") as directory:
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

    def test_cancelled_review_is_gate_blocked_without_automatic_retry(self) -> None:
        # GWT-006.t3：cancelled 不得包装为通过，恢复只能由显式用户请求触发。
        plan = _plan(
            "dev",
            "POST",
            ["README.md"],
            cancelled=True,
        )
        self.assertEqual("GATE_BLOCK", plan["terminal"]["status"])
        self.assertEqual(["REVIEW.CANCELLED"], plan["terminal"]["codes"])
        terminal = _governance_contract["terminal_codes"]["REVIEW.CANCELLED"]
        self.assertIs(terminal["automatic_retry"], False)
        self.assertEqual(
            "resume_only_after_explicit_user_request", terminal["recovery"]
        )

    def test_final_reviewer_input_counts_wrapper_finding_and_context_bytes(self) -> None:
        plan = _plan("dev", "POST", ["README.md"])
        evidence_identity = {
            "receipt_ref": "receipt.json",
            "canonical_bytes_sha256": "sha256:" + "a" * 64,
        }
        baseline = _cli.build_reviewer_input(
            plan,
            evidence_identity,
            evidence_summary={"findings": []},
            reviewer_role="developer",
        )
        long_finding = _cli.build_reviewer_input(
            plan,
            evidence_identity,
            evidence_summary={
                "findings": [{
                    "id": "F-LONG", "owner": "developer", "severity": "PR_WARN",
                    "path": "README.md", "summary": "长" * 12000,
                }]
            },
            reviewer_role="developer",
        )
        self.assertGreater(
            long_finding["assembled_input_byte_count"],
            baseline["assembled_input_byte_count"],
        )
        self.assertLessEqual(long_finding["assembled_input_byte_count"], 24576)
        self.assertTrue(long_finding["compression"]["applied"])
        from lib.review_context_assembler import canonical_json_bytes, sha256_digest
        raw = canonical_json_bytes(long_finding["assembled_input"])
        self.assertEqual(len(raw), long_finding["assembled_input_byte_count"])
        self.assertEqual(sha256_digest(raw), long_finding["assembled_input_digest"])
        identity = long_finding["assembled_input"]["identity"]
        self.assertEqual(plan["owner_identity"], identity["owner_identity"])
        self.assertEqual(
            plan["candidate_evidence_identity"],
            identity["candidate_evidence_identity"],
        )

    def test_large_candidate_code_health_artifact_compresses_with_auditable_identity(self) -> None:
        plan = _plan("dev", "POST", [f"quwoquan_ops/generated/path-{index}.py" for index in range(300)])
        findings = [
            {
                "code": "CODE_HEALTH.COMPLEXITY_ADVISORY",
                "path": f"quwoquan_ops/generated/path-{index}.py",
                "terminal": "PR_WARN",
                "symbol": f"function_{index}",
                "message": "changed function complexity exceeds advisory " * 4,
                "measure": {"ratio": 1.043},
            }
            for index in range(50)
        ]
        artifact = {
            "kind": "code-health-report-v1",
            "canonical_bytes_sha256": "sha256:" + "b" * 64,
            "terminal": "PR_WARN",
            "summary": {"changedFiles": 300, "duplicationPercent": 1.043},
            "findings": findings,
        }
        payload = _cli.build_reviewer_input(
            plan,
            {"receipt_ref": "receipt.json", "canonical_bytes_sha256": "sha256:" + "a" * 64},
            evidence_summary={"terminal": {"status": "PASS"}, "evidence": [{"id": "code-health-delta", "artifact": artifact}]},
            reviewer_role="developer",
        )

        self.assertLessEqual(payload["assembled_input_byte_count"], 24576)
        self.assertNotEqual("full", payload["compression"]["mode"])
        projected = payload["assembled_input"]["evidence_summary"]["results"][0]["artifact"]
        self.assertEqual(50, projected["findings_projection"]["original_count"])
        self.assertEqual("sha256:" + "b" * 64, projected["canonical_bytes_sha256"])
        self.assertTrue(all("message" not in item and "measure" not in item for item in projected["findings"]))
        path_summary = payload["assembled_input"]["changed_paths_and_diff_summary"]
        self.assertEqual([], path_summary["paths"])
        self.assertEqual(
            plan["candidate_evidence_identity"]["ref"],
            path_summary["paths_projection"]["ref"],
        )
        self.assertEqual(300, path_summary["paths_projection"]["original_count"])


    def test_final_reviewer_input_refuses_when_wrapper_and_identity_alone_exceed_limit(self) -> None:
        plan = _plan("dev", "POST", ["README.md"])
        plan["context_bytes"]["limit"] = 512
        with self.assertRaises(_cli.ReviewDispatchError) as blocked:
            _cli.build_reviewer_input(
                plan,
                {"receipt_ref": "x" * 4096},
                evidence_summary={"findings": []},
                reviewer_role="developer",
            )
        self.assertEqual("REVIEW.CONTEXT_BUDGET_EXCEEDED", blocked.exception.code)

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
                "review",
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
        self.assertEqual(5, json.loads(result.stdout)["schema_version"])

    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t3
    def test_post_requires_current_owner_manifest_and_matches_scope(self) -> None:
        with self.assertRaises(_cli.ReviewDispatchError) as missing:
            _cli.build_plan(_registry, "dev", "POST", None, ["README.md"])
        self.assertEqual("REVIEW.OWNER_MANIFEST_REQUIRED", missing.exception.code)

        manifest = _context_manifest(
            {"path": "README.md", "anchor": None, "kind": "spec"}
        )
        with self.assertRaises(_cli.ReviewDispatchError) as mismatch:
            _plan(
                "dev",
                "POST",
                ["README.md"],
                scope="AGENTS.md",
                context_manifest=manifest,
            )
        self.assertEqual(
            "REVIEW.OWNER_MANIFEST_SCOPE_MISMATCH", mismatch.exception.code
        )


    def test_plan_identity_binds_owner_manifest_and_terminal(self) -> None:
        manifest = _context_manifest(
            {"path": "README.md", "anchor": None, "kind": "spec"}
        )
        plan = _plan("dev", "POST", ["README.md"], context_manifest=manifest)
        identity = plan["owner_identity"]
        self.assertEqual(manifest["target"], identity["target"])
        self.assertEqual(
            manifest["evidence_fingerprint"]["digest"],
            identity["fingerprint_digest"],
        )
        terminal_mutation = json.loads(json.dumps(plan))
        terminal_mutation["terminal"] = {
            "status": "GATE_BLOCK",
            "codes": ["REVIEW.CANCELLED"],
            "failed_evidence": [],
        }
        with self.assertRaises(_cli.ReviewDispatchError) as blocked:
            _cli.validate_current_review_plan(
                terminal_mutation, _registry, phase="evidence"
            )
        self.assertEqual("REVIEW.TERMINAL_CONTRACT_INVALID", blocked.exception.code)

    # spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-002.t4
    def test_owner_manifest_ref_replacement_is_stale(self) -> None:
        manifest = _context_manifest()
        plan = _plan("dev", "POST", ["README.md"], context_manifest=manifest)
        ref = _REPO_ROOT / plan["owner_identity"]["ref"]
        original = ref.read_text(encoding="utf-8")
        try:
            ref.write_text(original + " ", encoding="utf-8")
            with self.assertRaises(_cli.ReviewDispatchError) as stale:
                _cli.validate_current_review_plan(plan, _registry)
            self.assertEqual("IDENTITY.MIGRATION_REQUIRED", stale.exception.code)
        finally:
            ref.write_text(original, encoding="utf-8")

    def test_plan_and_revalidation_share_owner_manifest_reader(self) -> None:
        manifest = _context_manifest()
        ref = _MANIFEST_REFS[id(manifest)]
        raw = (_REPO_ROOT / ref).read_bytes()
        identity = {
            "ref": ref,
            "canonical_bytes_sha256": "sha256:"
            + hashlib.sha256(raw).hexdigest(),
            "target": manifest["target"],
            "scope": manifest["target"],
            "resolved_owner": manifest["resolved_owner"],
            "fingerprint_ref": manifest["evidence_fingerprint"]["ref"],
            "fingerprint_digest": manifest["evidence_fingerprint"]["digest"],
        }
        with (
            mock.patch.object(
                _cli,
                "_read_owner_manifest_exact_bytes",
                wraps=_cli._read_owner_manifest_exact_bytes,
            ) as reader,
            mock.patch.object(_cli, "validate_feature_context_manifest"),
            mock.patch.object(
                _cli, "validate_current_feature_context_fingerprint"
            ),
        ):
            candidate = build_candidate_evidence(ref, [str(manifest["target"])], repo_root=_REPO_ROOT)
            candidate_raw = canonical_json_bytes(candidate)
            candidate_path = _REPO_ROOT / ".qwq_output/env/repo/runs/feature-tree/by-fingerprint/candidates/by-fingerprint" / (hashlib.sha256(candidate_raw).hexdigest() + ".json")
            candidate_path.parent.mkdir(parents=True, exist_ok=True)
            candidate_path.write_bytes(candidate_raw)
            _cli._normalize_contexts(
                manifest,
                manifest_ref=ref,
                candidate_evidence_ref=candidate_path.relative_to(_REPO_ROOT).as_posix(),
                changed_paths=[str(manifest["target"])],
                expected_scope=str(manifest["target"]),
                required=True,
            )
            self.assertEqual(1, reader.call_count)

            from lib.feature_tree import commands as feature_tree_commands
            from lib.feature_tree import ownership as feature_tree_ownership

            _relative, candidate_bytes, candidate_payload, candidate_fp = _cli._review_owner_manifest.validate_candidate_ref(
                candidate_path.relative_to(_REPO_ROOT).as_posix(), repo_root=_REPO_ROOT
            )
            candidate_identity = _cli._review_owner_manifest.candidate_identity(
                candidate_path.relative_to(_REPO_ROOT).as_posix(), candidate_bytes, candidate_payload, candidate_fp
            )
            _cli._validate_current_owner_manifest({
                "owner_identity": identity, "candidate_evidence_identity": candidate_identity,
                "scope": manifest["target"], "changed_paths": [manifest["target"]],
            })
            self.assertEqual(2, reader.call_count)

    def test_control_workflow_cannot_wrap_delivery_deliverable(self) -> None:
        with self.assertRaises(_cli.ReviewDispatchError) as forbidden:
            _plan("review", "POST", ["README.md"], deliverable="implementation")
        self.assertEqual(
            "REVIEW.CONTROL_WORKFLOW_DELIVERABLE_FORBIDDEN",
            forbidden.exception.code,
        )

    def test_emitted_terminal_codes_equal_contract_closed_set(self) -> None:
        self.assertEqual(
            set(_governance_contract["terminal_codes"]),
            set(_cli.EMITTED_REVIEW_CODES),
        )
        recoveries = [
            item["recovery"]
            for item in _governance_contract["terminal_codes"].values()
        ]
        self.assertEqual(len(recoveries), len(set(recoveries)))

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

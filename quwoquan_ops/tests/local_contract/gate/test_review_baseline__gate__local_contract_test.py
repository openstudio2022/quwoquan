# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md
import copy
import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

import yaml

from quwoquan_ops.cli.lib.candidate_evidence import build_candidate_evidence
from quwoquan_ops.cli.lib.evidence_fingerprint import canonical_json_bytes
from quwoquan_ops.cli.lib.feature_tree.content_addressed_writer import (
    _write_content_addressed_bytes,
)
from quwoquan_ops.tests.local_contract.gate.test_named_evidence_runner__local_contract_test import (
    REGISTRY_PATH,
    ROOT,
    NamedEvidenceRunnerTest,
    review,
    runner,
)



class ReviewBaselineGateContractTest(NamedEvidenceRunnerTest):
    def test_review_baseline_receives_only_runner_exact_plan_identity(self) -> None:
        registry = copy.deepcopy(
            yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {}
        )
        command = str(registry["evidence"]["review-baseline"]["command"])
        self.assertIn("verify_review_baseline.py", command)
        self.assertNotIn("pytest", command)
        self.assertNotIn("make verify-review-dispatch", command)
        paths = [
            "specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md"
        ]
        manifest = self._manifest(paths[0])
        candidate = build_candidate_evidence(self.manifest_ref, paths, repo_root=ROOT)
        candidate_path = _write_content_addressed_bytes(
            canonical_json_bytes(candidate), subdirectory="candidates/by-fingerprint"
        )
        plan = review.build_plan(
            registry, "dev", "POST", None, paths,
            context_manifest=manifest, context_manifest_ref=self.manifest_ref,
            candidate_evidence_ref=candidate_path.relative_to(ROOT).as_posix(),
        )
        captured: dict[str, object] = {}
        real_run = runner.run_command

        def inspect(args, *positional, **kwargs):
            env = kwargs["env"]
            exact_path = Path(env[runner.BASELINE_PLAN_ENV])
            raw = exact_path.read_bytes()
            captured.update({
                "path": exact_path,
                "raw": raw,
                "sha": env[runner.BASELINE_PLAN_SHA_ENV],
                "ref": env[runner.BASELINE_PLAN_REF_ENV],
            })
            result = real_run(args, *positional, **kwargs)
            captured["stderr"] = result.stderr.decode("utf-8", errors="replace")
            return result

        hostile = {
            runner.BASELINE_PLAN_ENV: "/tmp/forged-plan.json",
            runner.BASELINE_PLAN_SHA_ENV: "sha256:" + "0" * 64,
            runner.BASELINE_PLAN_REF_ENV: "forged",
        }
        source_plan = self.case_root / "exact-plan.json"
        source_plan.write_bytes(canonical_json_bytes(plan))
        source_ref = source_plan.relative_to(ROOT).as_posix()
        with mock.patch.dict(os.environ, hostile), mock.patch.object(
            runner, "run_command", side_effect=inspect
        ):
            receipt = self._run(
                plan, registry,
                plan_bytes=source_plan.read_bytes(),
                plan_ref=source_ref,
            )
        self.assertEqual(
            "PASS", receipt["terminal"]["status"],
            captured.get("stderr") or (receipt["evidence"][0] if receipt["evidence"] else receipt),
        )
        self.assertEqual(canonical_json_bytes(plan), captured["raw"])
        self.assertEqual(
            "sha256:" + hashlib.sha256(captured["raw"]).hexdigest(), captured["sha"]
        )
        self.assertEqual(source_ref, captured["ref"])
        self.assertFalse(captured["path"].exists())

    def test_review_baseline_rejects_plan_bytes_ref_candidate_paths_and_registry_drift(self) -> None:
        registry = copy.deepcopy(
            yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {}
        )
        command = str(registry["evidence"]["review-baseline"]["command"])
        paths = [
            "specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md"
        ]
        manifest = self._manifest(paths[0])
        candidate = build_candidate_evidence(self.manifest_ref, paths, repo_root=ROOT)
        candidate_path = _write_content_addressed_bytes(
            canonical_json_bytes(candidate), subdirectory="candidates/by-fingerprint"
        )
        plan = review.build_plan(
            registry, "dev", "POST", None, paths,
            context_manifest=manifest, context_manifest_ref=self.manifest_ref,
            candidate_evidence_ref=candidate_path.relative_to(ROOT).as_posix(),
        )
        wrong_bytes = canonical_json_bytes({**plan, "scope": "forged"})
        with self.assertRaisesRegex(runner.EvidenceRunnerError, "exact plan bytes"):
            self._run(plan, registry, plan_bytes=wrong_bytes)

        cases = [
            ("candidate", lambda value: value["candidate_evidence_identity"].__setitem__("ref", value["owner_identity"]["ref"])),
            ("changed_paths", lambda value: value.__setitem__("changed_paths", ["README.md"])),
            ("evidence_registry", lambda value: value["evidence"][0].__setitem__("command", "printf forged")),
        ]
        for label, mutate in cases:
            with self.subTest(label=label):
                changed = copy.deepcopy(plan)
                mutate(changed)
                with self.assertRaisesRegex(
                    runner.EvidenceRunnerError,
                    "CANDIDATE|IDENTITY|FINGERPRINT_CHANGED|command 与 registry|identity",
                ):
                    self._run(changed, registry, plan_bytes=canonical_json_bytes(changed))

        source_plan = self.case_root / "source-plan.json"
        source_plan.write_bytes(canonical_json_bytes(plan))
        with tempfile.TemporaryDirectory(prefix="qwq-review-evidence-plan-") as directory:
            injected = Path(directory) / "exact-plan.json"
            injected.write_bytes(canonical_json_bytes(plan))
            source_plan.write_bytes(canonical_json_bytes({**plan, "generated_at": "drift"}))
            completed = subprocess.run(
                [sys.executable, "-B", str(ROOT / "quwoquan_ops/gate/verify_review_baseline.py")],
                cwd=ROOT,
                env={
                    **os.environ,
                    runner.BASELINE_PLAN_ENV: str(injected),
                    runner.BASELINE_PLAN_SHA_ENV: "sha256:" + hashlib.sha256(injected.read_bytes()).hexdigest(),
                    runner.BASELINE_PLAN_REF_ENV: source_plan.relative_to(ROOT).as_posix(),
                },
                capture_output=True, text=True, check=False,
            )
        self.assertEqual(2, completed.returncode)
        self.assertIn("ref bytes", completed.stderr)

        outside = self.case_root / "outside-plan.json"
        outside.write_bytes(canonical_json_bytes(plan))
        completed = subprocess.run(
            [sys.executable, "-B", str(ROOT / "quwoquan_ops/gate/verify_review_baseline.py")],
            cwd=ROOT,
            env={
                **os.environ,
                runner.BASELINE_PLAN_ENV: str(outside),
                runner.BASELINE_PLAN_SHA_ENV: "sha256:" + hashlib.sha256(outside.read_bytes()).hexdigest(),
                runner.BASELINE_PLAN_REF_ENV: "forged",
            },
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(2, completed.returncode)

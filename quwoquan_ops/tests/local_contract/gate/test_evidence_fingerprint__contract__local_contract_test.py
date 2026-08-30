"""EvidenceFingerprint canonical serialization and repository snapshot contracts.

# spec_ref: specs/feature-tree/runtime/development-workflow-governance/agent-skill-review-context-organization/spec.md#gwt-004.t1
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_REPO_ROOT / "quwoquan_ops/cli"))

from lib.evidence_fingerprint import (  # noqa: E402
    EvidenceFingerprintError,
    MISSING,
    build_digest_payload,
    build_evidence_fingerprint,
    canonical_digest,
    canonical_json_bytes,
    normalize_repo_relative_path,
    snapshot_path,
    snapshot_paths,
    validate_evidence_fingerprint,
    workspace_digests,
)

_OUTPUT_ROOT = _REPO_ROOT / ".qwq_output/env/repo/local/evidence-fingerprint-tests"


def _groups(**overrides: object) -> dict[str, dict[str, object]]:
    groups: dict[str, dict[str, object]] = {
        "git": {"head_sha": "a" * 40, "merge_base_sha": "b" * 40},
        "workspace": {
            "tracked_digest": canonical_digest([]),
            "untracked_digest": canonical_digest([]),
            "deleted_digest": canonical_digest([]),
            "renamed_digest": canonical_digest([]),
            "symlink_digest": canonical_digest([]),
        },
        "assets": {
            "canonical_assets_digest": canonical_digest({"kind": "café"}),
            "review_assets_digest": canonical_digest([]),
        },
        "execution": {
            "commands_digest": canonical_digest([]),
            "toolchain_digest": canonical_digest({"python": 3}),
            "provider_digest": canonical_digest([]),
            "generator_digest": canonical_digest("generator"),
        },
    }
    for key, value in overrides.items():
        group, field = key.split("__", 1)
        groups[group][field] = value
    return groups


class EvidenceFingerprintCanonicalContractTest(unittest.TestCase):
    def test_receipt_metadata_never_changes_digest(self) -> None:
        first = build_evidence_fingerprint(
            _groups(),
            captured_at="2026-08-29T00:00:00Z",
            captured_by="one",
            captured_metadata={"run": 1},
        )
        second = build_evidence_fingerprint(
            _groups(),
            captured_at="2026-08-30T00:00:00Z",
            captured_by="two",
            captured_metadata={"run": 2},
        )
        self.assertEqual(first["digest"], second["digest"])
        self.assertEqual(first["ref"], second["ref"])
        self.assertNotEqual(first["captured_at"], second["captured_at"])

    def test_map_and_path_order_are_bytewise_invariant(self) -> None:
        self.assertEqual(
            canonical_digest({"é": 1, "z": 2}),
            canonical_digest({"z": 2, "e\u0301": 1}),
        )
        first = workspace_digests(
            ["README.md", "AGENTS.md"], repo_root=_REPO_ROOT
        )
        second = workspace_digests(
            ["AGENTS.md", "README.md", "README.md"], repo_root=_REPO_ROOT
        )
        self.assertEqual(first, second)

    def test_any_payload_byte_change_changes_digest(self) -> None:
        first = build_evidence_fingerprint(_groups(), captured_by="test")
        second = build_evidence_fingerprint(
            _groups(execution__generator_digest=canonical_digest("changed")),
            captured_by="test",
        )
        self.assertNotEqual(first["digest"], second["digest"])

    def test_unicode_nfc_missing_null_and_empty_are_distinct(self) -> None:
        self.assertEqual(canonical_digest("é"), canonical_digest("e\u0301"))
        values = {
            canonical_digest(MISSING),
            canonical_digest(None),
            canonical_digest(""),
            canonical_digest([]),
            canonical_digest({}),
        }
        self.assertEqual(5, len(values))
        self.assertEqual(b"true", canonical_json_bytes(True))
        self.assertEqual(b"false", canonical_json_bytes(False))
        self.assertEqual(b"null", canonical_json_bytes(None))
        with self.assertRaises(EvidenceFingerprintError):
            canonical_json_bytes(1.0)

    def test_unknown_fields_and_groups_fail_closed(self) -> None:
        groups = _groups()
        groups["git"]["unknown"] = "no"
        with self.assertRaisesRegex(EvidenceFingerprintError, "未知字段"):
            build_evidence_fingerprint(groups, captured_by="test")
        groups = _groups()
        groups["legacy"] = {}
        with self.assertRaisesRegex(EvidenceFingerprintError, "未知 field group"):
            build_evidence_fingerprint(groups, captured_by="test")

    def test_self_built_partial_fields_validate_roundtrip(self) -> None:
        receipt = build_evidence_fingerprint(
            {"git": {"head_sha": "a" * 40}},
            captured_at="2026-08-30T00:00:00Z",
            captured_by="test",
        )
        wire_receipt = json.loads(canonical_json_bytes(receipt))
        validated = validate_evidence_fingerprint(wire_receipt)
        self.assertEqual(receipt["digest"], validated["digest"])
        self.assertEqual(
            canonical_json_bytes(receipt), canonical_json_bytes(validated)
        )

    def test_caller_reserved_missing_marker_is_rejected(self) -> None:
        marker = {"$evidenceFingerprintMissing": True}
        with self.assertRaisesRegex(EvidenceFingerprintError, "保留 member"):
            build_digest_payload({"git": {"head_sha": marker}})
        with self.assertRaisesRegex(EvidenceFingerprintError, "未知字段"):
            build_digest_payload({"git": {"$evidenceFingerprintMissing": True}})
        with self.assertRaisesRegex(EvidenceFingerprintError, "保留 member"):
            build_digest_payload(
                {"git": {"head_sha": {"nested": marker}}}
            )
        with self.assertRaisesRegex(EvidenceFingerprintError, "保留 member"):
            build_digest_payload(
                {"git": {"head_sha": {"$evidenceFingerprintMissingExtra": True}}}
            )

    def test_metadata_reserved_missing_marker_is_rejected(self) -> None:
        with self.assertRaisesRegex(EvidenceFingerprintError, "保留 member"):
            build_evidence_fingerprint(
                _groups(),
                captured_by="test",
                captured_metadata={"$evidenceFingerprintMissing": True},
            )
        receipt = build_evidence_fingerprint(_groups(), captured_by="test")
        receipt["captured_metadata"] = {"$evidenceFingerprintMissing": True}
        with self.assertRaisesRegex(EvidenceFingerprintError, "保留 member"):
            validate_evidence_fingerprint(receipt)

    def test_windows_separator_and_dot_segments_normalize_lexically(self) -> None:
        self.assertEqual(
            "quwoquan_ops/cli/review_dispatch.py",
            normalize_repo_relative_path(
                r"quwoquan_ops\cli\.\review_dispatch.py", _REPO_ROOT
            ),
        )
        with self.assertRaises(EvidenceFingerprintError):
            normalize_repo_relative_path(r"..\outside.txt", _REPO_ROOT)

    def test_symlink_target_outside_repository_is_rejected(self) -> None:
        _OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=_OUTPUT_ROOT) as directory:
            link = Path(directory) / "outside.txt"
            link.symlink_to("/tmp/outside-evidence-fingerprint.txt")
            with self.assertRaisesRegex(EvidenceFingerprintError, "路径不在仓库内"):
                snapshot_path(link.relative_to(_REPO_ROOT), repo_root=_REPO_ROOT)

    def test_symlink_target_content_and_broken_target_are_bound(self) -> None:
        _OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=_OUTPUT_ROOT) as directory:
            root = Path(directory)
            target = root / "target.txt"
            link = root / "link.txt"
            target.write_text("first\n", encoding="utf-8")
            link.symlink_to("target.txt")
            first = snapshot_path(link.relative_to(_REPO_ROOT), repo_root=_REPO_ROOT)
            self.assertEqual("symlink", first["state"])
            self.assertFalse(first["broken"])
            self.assertEqual("target.txt", Path(first["symlink_target"]).name)
            target.write_text("second\n", encoding="utf-8")
            second = snapshot_path(link.relative_to(_REPO_ROOT), repo_root=_REPO_ROOT)
            self.assertNotEqual(
                first["symlink_target_content_digest"],
                second["symlink_target_content_digest"],
            )
            target.unlink()
            broken = snapshot_path(link.relative_to(_REPO_ROOT), repo_root=_REPO_ROOT)
            self.assertTrue(broken["broken"])
            self.assertIsNone(broken["symlink_target_content_digest"])
            self.assertNotEqual(second["content_digest"], broken["content_digest"])

    def test_directory_snapshot_includes_symlink_identity_without_following_it(self) -> None:
        _OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=_OUTPUT_ROOT) as directory:
            root = Path(directory)
            (root / "target.txt").write_text("payload\n", encoding="utf-8")
            (root / "alias.txt").symlink_to("target.txt")
            first = snapshot_path(root.relative_to(_REPO_ROOT), repo_root=_REPO_ROOT)
            os.unlink(root / "alias.txt")
            second = snapshot_path(root.relative_to(_REPO_ROOT), repo_root=_REPO_ROOT)
            self.assertNotEqual(first["content_digest"], second["content_digest"])

    def _renamed_repo(self, directory: str) -> Path:
        repo = Path(directory)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        for name, payload in (
            ("before.txt", "first\n"),
            ("before-two.txt", "other\n"),
            ("keep.txt", "keep\n"),
        ):
            (repo / name).write_text(payload, encoding="utf-8")
        subprocess.run(
            ["git", "add", "before.txt", "before-two.txt", "keep.txt"],
            cwd=repo,
            check=True,
        )
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
        subprocess.run(["git", "mv", "before.txt", "after.txt"], cwd=repo, check=True)
        subprocess.run(
            ["git", "mv", "before-two.txt", "after-two.txt"], cwd=repo, check=True
        )
        return repo

    def test_renamed_snapshot_preserves_source_identity_and_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = self._renamed_repo(directory)
            renamed = snapshot_path("after.txt", repo_root=repo)
            self.assertTrue(renamed["tracked"])
            self.assertEqual("renamed", renamed["state"])
            self.assertEqual("before.txt", renamed["renamed_from"])
            first_digest = workspace_digests(
                ["after.txt"], repo_root=repo
            )["renamed_digest"]
            self.assertEqual(canonical_digest([renamed]), first_digest)
            (repo / "after.txt").write_text("second\n", encoding="utf-8")
            second_digest = workspace_digests(
                ["after.txt"], repo_root=repo
            )["renamed_digest"]
            self.assertNotEqual(first_digest, second_digest)

    def test_batch_renamed_snapshot_uses_at_most_one_global_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = self._renamed_repo(directory)
            import lib.evidence_fingerprint as evidence_fingerprint

            real_git = evidence_fingerprint._git
            calls: list[tuple[str, ...]] = []

            def recording_git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
                calls.append(args)
                return real_git(root, *args)

            with mock.patch.object(evidence_fingerprint, "_git", side_effect=recording_git):
                snapshots = snapshot_paths(
                    ["after.txt", "after-two.txt", "keep.txt", "absent.txt"],
                    repo_root=repo,
                )
            by_path = {item["path"]: item for item in snapshots}
            self.assertEqual("renamed", by_path["after.txt"]["state"])
            self.assertEqual("before.txt", by_path["after.txt"]["renamed_from"])
            self.assertEqual("renamed", by_path["after-two.txt"]["state"])
            self.assertEqual(
                "before-two.txt", by_path["after-two.txt"]["renamed_from"]
            )
            self.assertEqual("file", by_path["keep.txt"]["state"])
            self.assertEqual("missing", by_path["absent.txt"]["state"])
            status_calls = [args for args in calls if args and args[0] == "status"]
            global_status_calls = [args for args in status_calls if "--" not in args]
            self.assertEqual(2, len(status_calls))
            self.assertEqual(1, len(global_status_calls))

    def test_tracked_untracked_and_deleted_snapshots_are_distinct(self) -> None:
        tracked = snapshot_path("README.md", repo_root=_REPO_ROOT)
        self.assertTrue(tracked["tracked"])
        _OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=_OUTPUT_ROOT) as directory:
            untracked_path = Path(directory) / "untracked.txt"
            untracked_path.write_text("value\n", encoding="utf-8")
            untracked = snapshot_path(
                untracked_path.relative_to(_REPO_ROOT), repo_root=_REPO_ROOT
            )
            self.assertFalse(untracked["tracked"])
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
            deleted = snapshot_path("deleted.txt", repo_root=repo)
            self.assertEqual("deleted", deleted["state"])
            self.assertTrue(deleted["tracked"])
            self.assertTrue(deleted["content_digest"].startswith("sha256:"))


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False).result.wasSuccessful() else 1)

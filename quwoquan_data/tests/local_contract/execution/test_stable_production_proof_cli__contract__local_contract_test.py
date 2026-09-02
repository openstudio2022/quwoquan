"""Read-only CLI contract for GWT-034 proof and retirement precheck."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

DATA_ROOT = Path(__file__).resolve().parents[3]
ROOT = DATA_ROOT.parent
CLI = DATA_ROOT / "scripts/cli.py"
SCRIPTS = DATA_ROOT / "scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from content.execution import stable_production_proof as proof_subject  # noqa: E402
from content.execution.operational_fingerprint import operational_fingerprint  # noqa: E402
from governance import stable_production_proof as subject  # noqa: E402
from quwoquan_data.tests.support import stable_production_proof_fixture as fixture  # noqa: E402


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PYTHONPYCACHEPREFIX"] = str(ROOT / ".qwq_output/env/repo/local/pycache")
    return subprocess.run([sys.executable, "-B", str(CLI), *args], cwd=ROOT, capture_output=True, text=True, check=False, env=environment)


def _write_request(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    return path


def test_stable_production_proof_cli_rejects_test_only_fixture(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    fixture.FINGERPRINT = operational_fingerprint()
    request = fixture.build_proof_fixture(root)
    request.pop("artifactRoot")
    request_path = _write_request(root / "request.json", request)
    before = sorted((item.relative_to(root).as_posix(), item.read_bytes()) for item in root.rglob("*") if item.is_file())
    result = _run("governance", "stable-production-proof", "--request", str(request_path), "--artifact-root", str(root))
    after = sorted((item.relative_to(root).as_posix(), item.read_bytes()) for item in root.rglob("*") if item.is_file())
    assert result.returncode != 0
    assert "test_only evidence is not accepted" in result.stderr
    assert before == after


def test_stable_production_proof_has_no_output_write_option(tmp_path: Path) -> None:
    request = _write_request(tmp_path / "request.json", {"schema": subject.REQUEST_SCHEMA, "fingerprint": "sha256:" + "f" * 64, "verifyAllReceipt": {"ref": "verify.json", "exactByteDigest": "sha256:" + "1" * 64}, "publicCliLiveImportZeroReceipt": {"ref": "imports.json", "exactByteDigest": "sha256:" + "2" * 64}, "proofUnits": []})
    output = tmp_path / "must-not-exist.json"
    result = _run("governance", "stable-production-proof", "--request", str(request), "--artifact-root", str(tmp_path), "--output", str(output))
    assert result.returncode != 0
    assert "unrecognized arguments: --output" in result.stderr
    assert not output.exists()


def test_stable_production_proof_error_names_one_proof_unit(tmp_path: Path) -> None:
    request = _write_request(tmp_path / "request.json", {"schema": subject.REQUEST_SCHEMA, "fingerprint": "sha256:" + "f" * 64, "verifyAllReceipt": {"ref": "verify.json", "exactByteDigest": "sha256:" + "1" * 64}, "publicCliLiveImportZeroReceipt": {"ref": "imports.json", "exactByteDigest": "sha256:" + "2" * 64}, "proofUnits": []})
    result = _run("governance", "stable-production-proof", "--request", str(request), "--artifact-root", str(tmp_path))
    assert result.returncode != 0
    assert "GATE_BLOCK DATA.STABLE_PRODUCTION_PROOF.CURRENT_EVIDENCE_REQUIRED" in result.stderr
    assert "exactly one proof unit" in result.stderr


def test_stable_production_proof_rejects_stale_current_fingerprint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    request = {"schema": subject.REQUEST_SCHEMA, "fingerprint": "sha256:" + "e" * 64, "verifyAllReceipt": {"ref": "verify.json", "exactByteDigest": "sha256:" + "1" * 64}, "publicCliLiveImportZeroReceipt": {"ref": "imports.json", "exactByteDigest": "sha256:" + "2" * 64}, "proofUnits": []}
    monkeypatch.setattr(subject, "assert_valid", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(proof_subject, "evaluate_stable_production_proof", lambda **kwargs: (_ for _ in ()).throw(subject.StableProductionProofError("must not reach evaluator")))
    with pytest.raises(subject.StableProductionProofError, match="fingerprint drifted"):
        subject.evaluate_stable_production_proof_request(request=request, artifact_root=tmp_path)


def test_legacy_retirement_precheck_missing_evidence_is_read_only(tmp_path: Path) -> None:
    inventory = tmp_path / "legacy_orchestration_retirement.json"
    inventory.write_text(json.dumps({"schema": subject.RETIREMENT_INVENTORY_SCHEMA, "state": "operationally_retired", "deleteFamilies": ["agent", "queue", "controller", "recovery", "campaign"], "preserveProtocolKernels": ["closure", "runtime_evidence", "scale"], "forbiddenCompatibility": ["alias", "dual_read", "dual_write", "shim"]}) + "\n", encoding="utf-8")
    before = inventory.read_bytes()
    result = _run("governance", "legacy-retirement-precheck", "--retirement-inventory", str(inventory))
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["eligibility"] == "not_eligible"
    assert payload["stateChanged"] is False and payload["deletedRefs"] == []
    assert inventory.read_bytes() == before


def test_legacy_retirement_precheck_accepts_operationally_retired_without_delete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    proof = {"schema": proof_subject.SCHEMA, "expectedFingerprint": "sha256:" + "f" * 64, "releaseIds": ["release-1"], "proofUnitCount": 1, "executionCount": 4, "verdict": "pass"}
    inventory = {"state": "operationally_retired"}
    proof_ref = {"ref": "proof.json", "exactByteDigest": "sha256:" + "a" * 64}
    inventory_ref = {"ref": "inventory.json", "exactByteDigest": "sha256:" + "b" * 64}
    monkeypatch.setattr(proof_subject, "_safe_root", lambda root: Path(root))
    monkeypatch.setattr(proof_subject, "_load_exact_json", lambda *_args, **_kwargs: (proof, proof_ref))
    monkeypatch.setattr(subject, "load_retirement_inventory", lambda _path: (inventory, inventory_ref))
    monkeypatch.setattr(subject, "assert_valid", lambda *_args, **_kwargs: None)
    result = subject.evaluate_legacy_retirement_precheck(artifact_root=tmp_path, expected_fingerprint="sha256:" + "f" * 64, stable_production_proof_ref=proof_ref, retirement_inventory=tmp_path / "inventory.json")
    assert result["eligibility"] == "eligible"
    assert result["stableProductionProof"]["releaseIds"] == proof["releaseIds"]
    assert result["retirementInventory"] == {"state": "operationally_retired", "exactRef": inventory_ref}
    assert result["stateChanged"] is False and result["deletedRefs"] == []

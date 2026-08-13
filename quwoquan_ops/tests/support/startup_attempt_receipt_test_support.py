"""startup attempt receipt 契约套件的共享构造 helper。

由 1000 行硬顶拆分自
quwoquan_ops/tests/local_contract/test_startup_attempt_receipt__local_contract_test.py，
供 environment concern 下 attempt_lifecycle / candidate_oci_and_fanout 两个
拆分套件共用；函数体逐字保留原实现。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from quwoquan_ops.cli.lib import startup_attempt_receipt as subject


def _digest_json(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _oci_manifest(
    *,
    environment: str = "alpha",
    target: str = "alpha-local",
) -> dict[str, object]:
    images = {
        "api-edge": {
            "ref": "quwoquan/api-edge:build",
            "imageDigest": "sha256:" + "1" * 64,
        },
        "provider-protocol-substitute": {
            "buildInputDigest": "sha256:" + "2" * 64,
            "ref": "quwoquan/provider-protocol-substitute:build",
            "imageDigest": "sha256:" + "3" * 64,
        },
        "sms-provider-substitute": {
            "buildInputDigest": "sha256:" + "4" * 64,
            "ref": "quwoquan/sms-provider-substitute:build",
            "imageDigest": "sha256:" + "5" * 64,
        },
    }
    return {
        "schema": "stackctl-package-oci-images",
        "environment": environment,
        "target": target,
        "configurationDigest": "sha256:" + "c" * 64,
        "buildInputDigest": "sha256:" + "6" * 64,
        "imageDigest": _digest_json(images),
        "images": images,
    }


def _composition(
    *,
    environment: str = "alpha",
    target: str = "alpha-local",
) -> dict[str, object]:
    return subject.image_composition_from_candidate_oci(
        _oci_manifest(environment=environment, target=target),
        expected_environment=environment,
        expected_target=target,
    )


def _active_candidate_files(
    tmp_path: Path,
    *,
    manifest: dict[str, object] | None = None,
    baseline_id: str = "sha256:" + "b" * 64,
) -> tuple[Path, Path, Path, dict[str, object]]:
    candidate_root = tmp_path / "candidate"
    oci_path = candidate_root / "packages/runtime-shared/oci-images.json"
    oci_path.parent.mkdir(parents=True)
    oci = manifest or _oci_manifest()
    oci_path.write_text(json.dumps(oci), encoding="utf-8")
    active_path = tmp_path / "active-runtime-candidate.json"
    active_path.write_text(
        json.dumps(
            {
                "schema": subject.ACTIVE_CANDIDATE_SCHEMA,
                "candidateType": "runtime-full",
                "target": str(oci["target"]),
                "baselineId": baseline_id,
                "candidateDir": str(candidate_root),
            }
        ),
        encoding="utf-8",
    )
    candidate = {
        "baselineId": baseline_id,
        "configurationDigest": oci["configurationDigest"],
        "runtimeConfigDigest": "sha256:" + "d" * 64,
        "buildInputDigest": oci["buildInputDigest"],
        "imageDigest": oci["imageDigest"],
    }
    return active_path, candidate_root, oci_path, candidate

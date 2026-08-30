"""候选内 Provider binding overlay 的最小合法构造。

首方镜像把单环境 Provider binding 编进二进制，因此候选目录里必须存在这份
overlay：`up` 会用它的 manifest digest 反推 build tag，读不到就是候选不可运行。
用真实候选做端到端测试成本过高，这里只落一份结构完整、摘要自洽的最小 overlay，
让消费侧读到与生产同形的输入。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from quwoquan_ops.cli.lib.deployment_candidate_manifest import provider_binding_overlay

_ARTIFACT_RELATIVE = "packages/runtime-shared/compiled-provider-bindings"
_OUTPUT_PATH = (
    "quwoquan_service/services/user-service/generated/account/user_account/"
    "external_provider_bindings.g.go"
)


def write_provider_binding_overlay_fixture(
    candidate_root: Path,
    *,
    environment: str,
    target: str,
) -> str:
    """在候选内落一份最小合法 overlay，返回它的 bindingManifestDigest。"""

    artifact_root = Path(candidate_root) / _ARTIFACT_RELATIVE
    artifact_root.mkdir(parents=True, exist_ok=True)

    source_path = artifact_root / "user.g.go"
    source_path.write_text("package generated\n", encoding="utf-8")
    source_digest = "sha256:" + hashlib.sha256(source_path.read_bytes()).hexdigest()

    overlay_path = artifact_root / "go.overlay.json"
    overlay_path.write_text(
        json.dumps(
            {
                "Replace": {
                    _OUTPUT_PATH.removeprefix("quwoquan_service/"): (
                        "/run/qwq-provider-bindings/user.g.go"
                    )
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )

    binding_manifest = {
        "schema": "compiled-external-provider-binding-manifest.single-environment",
        "environment": environment,
        "target": target,
        "bindingDigest": "sha256:" + "1" * 64,
        "readinessDigest": "sha256:" + "2" * 64,
        "descriptorDigest": "sha256:" + "3" * 64,
        "goSourceDigest": "sha256:" + "4" * 64,
        "descriptorCount": 1,
    }
    binding_manifest["manifestDigest"] = provider_binding_overlay._sha256_json(
        binding_manifest
    )

    manifest = {
        "schema": provider_binding_overlay.PROVIDER_BINDING_OVERLAY_SCHEMA,
        "environment": environment,
        "target": target,
        "bindingManifestDigest": binding_manifest["manifestDigest"],
        "bindingManifest": binding_manifest,
        "overlayRef": f"{_ARTIFACT_RELATIVE}/go.overlay.json",
        "overlayDigest": "sha256:"
        + hashlib.sha256(overlay_path.read_bytes()).hexdigest(),
        "sources": [
            {
                "rootId": "user.account.user_account",
                "owner": "user-service",
                "outputPath": _OUTPUT_PATH,
                "sourceRef": f"{_ARTIFACT_RELATIVE}/user.g.go",
                "sourceDigest": source_digest,
            }
        ],
    }
    (artifact_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return str(binding_manifest["manifestDigest"])


def packaged_service_build_ref(
    service: str,
    source_ref: str,
    binding_manifest_digest: str,
) -> str:
    """复刻 build tag 派生：换绑定即换镜像身份，候选里存的是这个 ref。"""

    repository, _, base_tag = source_ref.rpartition(":")
    build_tag = hashlib.sha256(
        (service + "\x00" + base_tag + "\x00" + binding_manifest_digest).encode("utf-8")
    ).hexdigest()
    return repository + ":" + build_tag

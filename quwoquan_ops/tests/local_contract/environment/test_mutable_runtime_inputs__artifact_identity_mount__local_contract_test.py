"""部署期身份挂载材料必须由 immutable 与 mutable 两条装配路径同时产出。

Compose 把 artifact identity 与 platform-ops facts 声明为必需插值变量，任一
装配路径漏绑都会让该 target 的 Compose render 直接失败。immutable 候选路径与
mutable `test_live` 路径共用同一份 Compose 片段，因此这条对称性是启动可用性的
前置条件，而不是实现细节。
"""

# spec_ref: specs/feature-tree/platform-ops-governance/spec.md#req-002
# spec_ref: specs/feature-tree/platform-ops-governance/spec.md#dom-001

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.commands import dev_session_runtime, runtime_image_composition

_REQUIRED_INTERPOLATION = re.compile(r"\$\{(QWQ_COMPOSE_[A-Z0-9_]+):\?")
_IDENTITY_MOUNT_KEYS = frozenset(
    {
        "QWQ_COMPOSE_ARTIFACT_IDENTITY_FILE",
        "QWQ_COMPOSE_PLATFORM_OPS_FACTS_ROOT",
    }
)


def _compose_required_identity_keys() -> set[str]:
    """收集 Compose 对部署期身份挂载声明的必需变量。"""
    service_root = stackctl.ROOT / "quwoquan_service"
    found: set[str] = set()
    for compose_path in service_root.rglob("deploy/compose.yaml"):
        text = compose_path.read_text(encoding="utf-8")
        found.update(
            key
            for key in _REQUIRED_INTERPOLATION.findall(text)
            if key in _IDENTITY_MOUNT_KEYS
        )
    return found


def test_compose_declares_identity_mount_as_required() -> None:
    assert _compose_required_identity_keys() == _IDENTITY_MOUNT_KEYS


def test_identity_mount_material_emits_every_required_compose_key(
    tmp_path: Path,
) -> None:
    environment: dict[str, str] = {
        "QWQ_LOCAL_RELEASE_ENV": "alpha",
        "LOCAL_GAMMA_CONFIG_VERSION": "sha256:" + "a" * 64,
        "QWQ_RUN_ROOT": str(tmp_path / "run"),
    }

    stackctl._bind_artifact_identity_mount_material(environment)

    for key in sorted(_IDENTITY_MOUNT_KEYS):
        assert environment.get(key), key
    identity = json.loads(
        Path(environment["QWQ_COMPOSE_ARTIFACT_IDENTITY_FILE"]).read_text(
            encoding="utf-8"
        )
    )
    assert identity == {
        "schema": "qwq.environment-artifact-identity",
        "environment": "alpha",
        "configDigest": "sha256:" + "a" * 64,
    }
    assert Path(environment["QWQ_COMPOSE_PLATFORM_OPS_FACTS_ROOT"]).is_dir()


@pytest.mark.parametrize(
    "module",
    [
        pytest.param(runtime_image_composition, id="immutable-candidate"),
        pytest.param(dev_session_runtime, id="mutable-test-live"),
    ],
)
def test_both_runtime_assemblies_bind_identity_mount_material(module) -> None:
    """两条装配路径都必须绑定同一份挂载材料，不允许只有其中一条覆盖。"""
    assert "_bind_artifact_identity_mount_material" in inspect.getsource(module)

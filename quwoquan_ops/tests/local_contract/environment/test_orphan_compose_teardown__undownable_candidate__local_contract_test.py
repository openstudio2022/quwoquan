"""candidate 客观不可用时的合法拆除：判据与 receipt 退休。

# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/local-gamma-mirror/spec.md#gwt-005.t10
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/local-gamma-mirror/spec.md#gwt-005.t11
# spec_ref: specs/feature-tree/runtime/deliver-deploy-prod-pipeline/local-gamma-mirror/spec.md#gwt-005.t12

normal down 强绑 candidate 重放拓扑，candidate 不可寻址时那条路永不收敛。
本文件锁定「什么才算客观不可能」以及拆除后回执必须退休这两件事，把它与
精确资源采样、repair 执行收敛分开承载。
"""

from __future__ import annotations

import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from quwoquan_ops.cli import stackctl
from quwoquan_ops.cli.lib import orphan_compose_teardown as contract
from quwoquan_ops.tests.support.orphan_compose_teardown_test_support import (
    install_stackctl_fakes,
    multi_sample,
    post_sample,
    repair_args,
)


def _sealed_workload_projection(
    tmp_path: Path,
    services: dict[str, dict[str, object]],
) -> Path:
    path = tmp_path / "projected.compose.yaml"
    path.write_text(
        json.dumps({"services": services}, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize(
    ("services", "expect_named"),
    [
        ({"rtc-service": {"networks": ["edge"]}}, True),
        (
            {"rtc-service": {"networks": ["edge"], "profiles": ["edge-media"]}},
            False,
        ),
        ({"rtc-service": {"image": "sha256:" + "f" * 64}}, False),
    ],
)
def test_normal_down_impossibility_is_named_only_for_ungated_imageless_services(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    services: dict[str, dict[str, object]],
    expect_named: bool,
) -> None:
    """只有「无 image、无 build、又无 profile 门控」才让 normal down 不可能。

    带 profile 的条目会被 Compose 在该 profile 未激活时整体排除,自带 image 的
    条目本就有效;这两种都必须继续走 candidate-bound normal down,不能借这条
    出口绕过它。
    """

    projection = _sealed_workload_projection(tmp_path, services)
    monkeypatch.setattr(
        stackctl,
        "deployment_candidate_dir",
        lambda _target, _digest: tmp_path,
    )
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.runtime_topology_package.load_runtime_topology_package",
        lambda *repair_args, **_kwargs: {"composeFiles": [projection]},
    )

    reason = stackctl._normal_down_structurally_impossible(
        "alpha-local",
        {
            "status": "partial",
            "workload": "content-release",
            "candidateDigest": "sha256:" + "a" * 64,
        },
    )

    assert bool(reason) is expect_named
    if expect_named:
        assert "rtc-service" in reason


def test_missing_candidate_is_a_named_reason_not_an_empty_string(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """candidate 被回收后 normal down 已不可能，判定不得把这个失败塌陷成空值。

    回收 candidate store 之后回执引用的目录就不在了。此时报 "" 等于宣告
    「继续走 normal down」，而那条路永远不会收敛，环境被冻结的证据锁死。
    """

    absent = tmp_path / "candidates" / "runtime-full" / ("sha256-" + "a" * 64)
    monkeypatch.setattr(
        stackctl,
        "deployment_candidate_dir",
        lambda _target, _digest: absent,
    )
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.runtime_topology_package.load_runtime_topology_package",
        lambda *repair_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("an absent candidate must not be loaded as a topology")
        ),
    )

    reason = stackctl._normal_down_structurally_impossible(
        "gamma-local",
        {
            "status": "running",
            "workload": "full",
            "candidateDigest": "sha256:" + "a" * 64,
        },
    )

    assert "no longer present" in reason
    assert str(absent) in reason


def test_unreadable_candidate_topology_is_named_rather_than_swallowed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """candidate 在场但拓扑读不出来，同样让 normal down 不可能，必须说出原因。"""

    from quwoquan_ops.cli.lib.runtime_topology_package import (
        RuntimeTopologyPackageError,
    )

    present = tmp_path / "candidate"
    present.mkdir()
    monkeypatch.setattr(
        stackctl,
        "deployment_candidate_dir",
        lambda _target, _digest: present,
    )
    monkeypatch.setattr(
        "quwoquan_ops.cli.lib.runtime_topology_package.load_runtime_topology_package",
        lambda *repair_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeTopologyPackageError("workload projection is missing")
        ),
    )

    reason = stackctl._normal_down_structurally_impossible(
        "gamma-local",
        {
            "status": "running",
            "workload": "full",
            "candidateDigest": "sha256:" + "b" * 64,
        },
    )

    assert "cannot project workload=full" in reason
    assert "workload projection is missing" in reason


def test_running_receipt_is_admitted_only_when_its_candidate_is_unusable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """运行中回执的准入判据是 candidate 的客观状态，不是操作者的声明。"""

    running = {"target": "gamma-local", "status": "running"}
    monkeypatch.setattr(stackctl, "active_consumer_leases", lambda _target: [])
    monkeypatch.setattr(stackctl, "load_startup_attempt", lambda _target: running)

    monkeypatch.setattr(
        stackctl,
        "_normal_down_structurally_impossible",
        lambda _target, _startup: "candidate sha256:x is no longer present",
    )
    assert stackctl._orphan_compose_runtime_gate("gamma-local") == running

    monkeypatch.setattr(
        stackctl,
        "_normal_down_structurally_impossible",
        lambda _target, _startup: "",
    )
    with pytest.raises(contract.OrphanComposeTeardownError) as blocked:
        stackctl._orphan_compose_runtime_gate("gamma-local")
    assert "candidate-bound normal down" in str(blocked.value)


def test_teardown_of_an_unusable_candidate_retires_the_running_receipt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """拆掉残留后回执必须转 stopped，否则下一次 up 仍被失效凭据挡住。"""

    report_dir = install_stackctl_fakes(monkeypatch, tmp_path)
    running = {
        "env": "alpha",
        "target": "alpha-local",
        "status": "running",
        "attemptId": "attempt-frozen",
        "candidateDigest": "sha256:" + "a" * 64,
    }
    monkeypatch.setattr(stackctl, "load_startup_attempt", lambda _target: running)
    monkeypatch.setattr(
        stackctl,
        "_normal_down_structurally_impossible",
        lambda _target, _startup: "candidate is no longer present",
    )
    transitions: list[dict[str, object]] = []
    monkeypatch.setattr(
        stackctl,
        "transition_startup_attempt",
        lambda **kwargs: transitions.append(kwargs),
    )
    snapshot = multi_sample()
    post_snapshot = post_sample(snapshot)
    samples = iter((snapshot, snapshot, post_snapshot))
    monkeypatch.setattr(contract, "sample_snapshot", lambda **_kwargs: next(samples))
    monkeypatch.setattr(
        stackctl,
        "run",
        lambda argv: CompletedProcess(argv, 0, "removed", ""),
    )
    path = tmp_path / "orphaned-compose-teardown-attestation.json"

    planned = stackctl._repair_orphaned_compose(
        repair_args(path, confirm=False),
        environment="alpha",
        report_dir=report_dir,
    )
    assert planned["exitCode"] == 0
    assert transitions == []

    consumed = stackctl._repair_orphaned_compose(
        repair_args(path, confirm=True),
        environment="alpha",
        report_dir=report_dir,
    )

    assert consumed["exitCode"] == 0
    assert transitions == [
        {
            "env": "alpha",
            "target": "alpha-local",
            "attempt_id": "attempt-frozen",
            "status": "stopped",
            "failure": (
                "reclaimed by governed orphan Compose teardown; candidate-bound "
                "down was structurally impossible for this receipt"
            ),
        }
    ]
    payload = json.loads(
        path.with_name("orphaned-compose-teardown-consumption.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["preservedVolumeNames"] == ["quwoquan_alpha_release_mongo-data"]


def test_reclaimed_receipt_is_retired_so_later_up_is_not_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transitions: list[dict[str, object]] = []
    monkeypatch.setattr(
        stackctl,
        "transition_startup_attempt",
        lambda **kwargs: transitions.append(kwargs),
    )

    detail = stackctl._close_orphan_reclaimed_startup_receipt(
        "alpha-local",
        {
            "env": "alpha",
            "status": "partial",
            "attemptId": "attempt-1",
        },
    )

    assert "attempt-1" in detail
    assert transitions == [
        {
            "env": "alpha",
            "target": "alpha-local",
            "attempt_id": "attempt-1",
            "status": "stopped",
            "failure": (
                "reclaimed by governed orphan Compose teardown; candidate-bound "
                "down was structurally impossible for this receipt"
            ),
        }
    ]

    transitions.clear()
    assert (
        stackctl._close_orphan_reclaimed_startup_receipt(
            "alpha-local",
            {"env": "alpha", "status": "stopped", "attemptId": "attempt-1"},
        )
        == ""
    )
    assert transitions == []

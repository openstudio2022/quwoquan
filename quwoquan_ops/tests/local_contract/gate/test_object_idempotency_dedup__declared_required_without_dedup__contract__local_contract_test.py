"""幂等去重门禁的判定契约。

锁三件事：只减不增的三个方向、语言可见性不得静默通过、以及「透传幂等键不算去重」——
最后这条是上一轮把 6 个对象误判为未实现的直接原因，必须由测试钉住。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MODULE_PATH = ROOT / "quwoquan_ops/gate/verify_object_idempotency_dedup.py"

SPEC = importlib.util.spec_from_file_location("object_idempotency_dedup", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
verifier = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = verifier
SPEC.loader.exec_module(verifier)


def _scan(
    service: str,
    relative: str,
    signals: dict[str, str] | None = None,
    suffixes: frozenset[str] = frozenset({".go"}),
) -> verifier.ObjectScan:
    return verifier.ObjectScan(
        service=service,
        relative=relative,
        signals=signals or {},
        suffixes=suffixes,
    )


def test_declared_required_without_dedup_outside_baseline_is_blocked() -> None:
    issues = verifier.validate([_scan("chat-service", "chat/message")], frozenset())

    assert any("没有任何去重实现" in issue for issue in issues)


def test_baseline_entry_must_be_removed_once_deduplicated() -> None:
    scan = _scan(
        "user-service",
        "account/invitation",
        {"receipt": "quwoquan_service/services/user-service/internal/account/invitation/x.go"},
    )

    issues = verifier.validate([scan], frozenset({("user-service", "account/invitation")}))

    assert any("MISSING_BASELINE" in issue for issue in issues)


def test_baseline_entry_stays_silent_while_still_missing() -> None:
    scan = _scan("user-service", "account/invitation")

    issues = verifier.validate([scan], frozenset({("user-service", "account/invitation")}))

    assert issues == []


def test_stale_baseline_entry_is_blocked() -> None:
    issues = verifier.validate(
        [_scan("chat-service", "chat/message", {"receipt": "x.go"})],
        frozenset({("user-service", "account/invitation")}),
    )

    assert any("基线与声明不同源" in issue for issue in issues)


def test_unscanned_language_is_blocked_instead_of_silently_passing() -> None:
    scan = _scan("edge-service", "edge/session", suffixes=frozenset({".go", ".rs"}))

    issues = verifier.validate([scan], frozenset())

    assert any("未被扫描的语言" in issue for issue in issues)
    assert not any("没有任何去重实现" in issue for issue in issues)


def test_python_implementation_is_visible() -> None:
    scan = _scan(
        "recommendation-service",
        "recommendation/recommendation_model_release",
        {"receipt": "x.py"},
        suffixes=frozenset({".py"}),
    )

    assert verifier.validate([scan], frozenset()) == []


def test_idempotency_key_plumbing_alone_is_not_dedup() -> None:
    plumbing = "\n".join(
        [
            "idempotencyKey := commandIdempotencyKey(r)",
            "req.IdempotencyKey = idempotencyKey",
            "return s.store.Create(ctx, req)",
        ]
    )

    matched = [
        name for name, pattern in verifier.DEDUP_SIGNALS.items() if pattern.search(plumbing)
    ]

    assert matched == []


def test_renamed_receipt_key_still_counts_as_dedup() -> None:
    renamed = "\n".join(
        [
            "SELECT operation, payload FROM greeting_receipts",
            " WHERE actor_persona_id = $1 AND n_key = $2",
            "if errors.Is(err, pgx.ErrNoRows) { return nil, false, nil }",
        ]
    )

    matched = [
        name for name, pattern in verifier.DEDUP_SIGNALS.items() if pattern.search(renamed)
    ]

    assert "receipt" in matched


def test_repository_missing_baseline_cannot_expand_again() -> None:
    assert verifier.MISSING_BASELINE == frozenset()


def test_repository_declared_objects_are_all_resolved() -> None:
    declared = verifier.objects_requiring_idempotency()

    assert declared, "必须至少有一个对象声明 idempotency: required"
    scans = [verifier.scan_object(service, relative) for service, relative in declared]
    assert verifier.validate(scans, verifier.MISSING_BASELINE) == []

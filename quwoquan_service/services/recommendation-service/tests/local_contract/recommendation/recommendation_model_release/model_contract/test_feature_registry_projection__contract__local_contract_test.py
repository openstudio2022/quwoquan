"""Feature registry viewer-edge to immutable snapshot projection contract."""

from __future__ import annotations

import importlib.util
import sys

from support.path_setup import model_runtime_root


def _load_verifier():
    path = model_runtime_root() / "scripts" / "verify_feature_consistency.py"
    spec = importlib.util.spec_from_file_location("verify_feature_consistency", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    # 源码树禁止 __pycache__；加载被测模块时不得写字节码。
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def test_intersection_edge_projection_has_one_source_and_exact_snapshot_shape() -> None:
    verifier = _load_verifier()
    registry = verifier.load_feature_registry()
    assert registry is not None
    registry_users = set(registry["user"])
    assert verifier.INTERSECTION_EDGE_REGISTRY_FIELD in registry_users

    projected = verifier.expected_snapshot_user_fields(registry_users)
    assert verifier.INTERSECTION_EDGE_REGISTRY_FIELD not in projected
    assert (
        projected - (registry_users - {verifier.INTERSECTION_EDGE_REGISTRY_FIELD})
        == verifier.INTERSECTION_EDGE_SNAPSHOT_FIELDS
    )
    assert verifier.check_item_and_label_registry() == []


def test_consistency_gate_fails_when_a_matched_edge_scalar_is_not_consumed(
    tmp_path,
    monkeypatch,
) -> None:
    verifier = _load_verifier()
    source = verifier.INTERSECTION_ENCODER.read_text(encoding="utf-8")
    consumed_expressions = {
        "intersectionEdgeWeight": (
            'features.append(float(matched_edge.get("intersectionEdgeWeight", 0) or 0))'
        ),
        "intersectionEdgeFreshness": (
            'features.append(float(matched_edge.get("intersectionEdgeFreshness", 0) or 0))'
        ),
        "intersectionEdgeKind": (
            'features.append(encode_intersection_kind(matched_edge.get("intersectionEdgeKind")))'
        ),
    }
    for field, expression in consumed_expressions.items():
        broken = source.replace(expression, "features.append(0.0)")
        assert broken != source
        broken_encoder = tmp_path / f"{field}.py"
        broken_encoder.write_text(broken, encoding="utf-8")
        monkeypatch.setattr(verifier, "INTERSECTION_ENCODER", broken_encoder)

        issues = verifier.check_intersection_features()
        assert any(
            f"does not consume '{field}'" in issue
            for issue in issues
        ), issues

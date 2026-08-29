#!/usr/bin/env python3
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-003.t1
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-003.t2
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/explicit-semantics-no-implicit-inference/spec.md#gwt-003.t1
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/explicit-semantics-no-implicit-inference/spec.md#gwt-003.t2
# spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/explicit-semantics-no-implicit-inference/spec.md#gwt-003.t3
"""锁定运行配置渲染的四层取值：跨服务默认是显式声明层，不是隐式推断。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from quwoquan_ops.cli.render_runtime_config import (  # noqa: E402
    MISSING,
    load_cross_service_defaults,
    pattern_matches,
    render_workload,
    resolve_layer_default,
)


WORKLOAD = "entity-service"
SCENE_MODE_KEY = "sys.entity-service.redis.general.mode"


def build_tree(
    tmp_path: Path,
    *,
    schema_default: str | None,
    global_defaults: dict[str, object] | None = None,
    environment_defaults: dict[str, object] | None = None,
    service_overrides: dict[str, object] | None = None,
) -> Path:
    service_dir = tmp_path / "quwoquan_service/services" / WORKLOAD
    (service_dir / "config").mkdir(parents=True)
    (service_dir / "environments/alpha").mkdir(parents=True)

    definition: dict[str, object] = {
        "key": SCENE_MODE_KEY,
        "type": "string",
        "scope": "workload",
        "reload": "restart",
        "rollout": "progressive",
        "sensitive": False,
    }
    if schema_default is not None:
        definition["default"] = schema_default
    (service_dir / "config/schema.yaml").write_text(
        yaml.safe_dump({"configs": [definition]}), encoding="utf-8"
    )
    (service_dir / "environments/alpha/config.yaml").write_text(
        yaml.safe_dump({"overrides": service_overrides or {}}), encoding="utf-8"
    )

    defaults_root = tmp_path / "quwoquan_ops/environments/alpha"
    defaults_root.mkdir(parents=True)
    if global_defaults is not None:
        (defaults_root.parent / "config-defaults.yaml").write_text(
            yaml.safe_dump({"defaults": global_defaults}), encoding="utf-8"
        )
    if environment_defaults is not None:
        (defaults_root / "config-defaults.yaml").write_text(
            yaml.safe_dump({"defaults": environment_defaults}), encoding="utf-8"
        )
    return tmp_path


def render_mode(tree: Path, output: Path) -> object:
    render_workload(tree, "alpha", WORKLOAD, output)
    rendered = yaml.safe_load(output.read_text(encoding="utf-8"))
    return rendered["redis"]["general"]["mode"]


def test_service_environment_override_wins_over_every_default_layer(tmp_path: Path) -> None:
    tree = build_tree(
        tmp_path,
        schema_default="schema",
        global_defaults={"redis.*.mode": "global"},
        environment_defaults={"redis.*.mode": "environment"},
        service_overrides={SCENE_MODE_KEY: "service"},
    )
    assert render_mode(tree, tmp_path / "out.yaml") == "service"


def test_environment_defaults_win_over_global_defaults(tmp_path: Path) -> None:
    tree = build_tree(
        tmp_path,
        schema_default="schema",
        global_defaults={"redis.*.mode": "global"},
        environment_defaults={"redis.*.mode": "environment"},
    )
    assert render_mode(tree, tmp_path / "out.yaml") == "environment"


def test_global_defaults_win_over_schema_default(tmp_path: Path) -> None:
    tree = build_tree(
        tmp_path,
        schema_default="schema",
        global_defaults={"redis.*.mode": "global"},
    )
    assert render_mode(tree, tmp_path / "out.yaml") == "global"


def test_schema_default_applies_when_no_cross_service_layer_matches(tmp_path: Path) -> None:
    tree = build_tree(
        tmp_path,
        schema_default="schema",
        global_defaults={"mongo.*.uri": "unrelated"},
    )
    assert render_mode(tree, tmp_path / "out.yaml") == "schema"


# 跨服务默认只给 schema 已声明的键供值。模式匹配不到任何声明键时不写入快照，
# 键的真相源仍是各服务 config/schema.yaml。
def test_cross_service_defaults_never_introduce_keys_absent_from_schema(tmp_path: Path) -> None:
    tree = build_tree(
        tmp_path,
        schema_default=None,
        global_defaults={"redis.*.mode": "global", "redis.*.addr": "redis:6379"},
    )
    output = tmp_path / "out.yaml"
    render_workload(tree, "alpha", WORKLOAD, output)
    rendered = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert rendered["redis"]["general"]["mode"] == "global"
    assert "addr" not in rendered["redis"]["general"]


def test_cross_service_defaults_cannot_supply_sensitive_keys(tmp_path: Path) -> None:
    service_dir = tmp_path / "quwoquan_service/services" / WORKLOAD
    (service_dir / "config").mkdir(parents=True)
    (service_dir / "environments/alpha").mkdir(parents=True)
    (service_dir / "config/schema.yaml").write_text(
        yaml.safe_dump(
            {
                "configs": [
                    {
                        "key": "sys.entity-service.redis.general.password",
                        "type": "string",
                        "sensitive": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (service_dir / "environments/alpha/config.yaml").write_text(
        yaml.safe_dump({"overrides": {}}), encoding="utf-8"
    )
    defaults_root = tmp_path / "quwoquan_ops/environments"
    defaults_root.mkdir(parents=True)
    (defaults_root / "config-defaults.yaml").write_text(
        yaml.safe_dump({"defaults": {"redis.*.password": "leaked"}}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="must use secretRef"):
        render_workload(tmp_path, "alpha", WORKLOAD, tmp_path / "out.yaml")


def test_type_violation_in_cross_service_defaults_names_the_defaults_file(tmp_path: Path) -> None:
    tree = build_tree(
        tmp_path,
        schema_default="schema",
        global_defaults={"redis.*.mode": 7},
    )
    with pytest.raises(ValueError, match="config-defaults.yaml"):
        render_workload(tree, "alpha", WORKLOAD, tmp_path / "out.yaml")


def test_more_specific_pattern_wins_within_one_layer(tmp_path: Path) -> None:
    tree = build_tree(
        tmp_path,
        schema_default="schema",
        global_defaults={"redis.*.mode": "wildcard", "redis.general.mode": "exact"},
    )
    assert render_mode(tree, tmp_path / "out.yaml") == "exact"


# 同层内两个同等具体的模式命中同一个键时判否：挑哪一个都是代码替声明者做决定。
def test_equally_specific_patterns_in_one_layer_fail_closed(tmp_path: Path) -> None:
    tree = build_tree(
        tmp_path,
        schema_default="schema",
        global_defaults={"redis.*.mode": "first", "*.general.mode": "second"},
    )
    with pytest.raises(ValueError, match="ambiguous defaults"):
        render_workload(tree, "alpha", WORKLOAD, tmp_path / "out.yaml")


@pytest.mark.parametrize(
    ("pattern", "key", "expected"),
    [
        ("redis.*.mode", "redis.general.mode", True),
        ("redis.*.mode", "redis.general.addr", False),
        ("redis.*.mode", "redis.mode", False),
        ("redis.*.mode", "redis.general.rec.mode", False),
        ("redis.general.mode", "redis.general.mode", True),
        ("*", "mode", True),
    ],
)
def test_pattern_matching_is_segment_exact(pattern: str, key: str, expected: bool) -> None:
    assert pattern_matches(pattern, key) is expected


def test_absent_defaults_file_contributes_no_layer(tmp_path: Path) -> None:
    assert load_cross_service_defaults(tmp_path / "nope.yaml") == {}


def test_render_requires_the_global_cross_service_defaults_file(tmp_path: Path) -> None:
    tree = build_tree(
        tmp_path,
        schema_default="schema",
        global_defaults=None,
    )
    with pytest.raises(ValueError, match="missing required global cross-service defaults"):
        render_workload(tree, "alpha", WORKLOAD, tmp_path / "out.yaml")


def test_unmatched_key_reports_missing_sentinel_not_none(tmp_path: Path) -> None:
    resolved = resolve_layer_default(
        tmp_path / "config-defaults.yaml", {"redis.*.mode": None}, "redis.general.addr"
    )
    assert resolved is MISSING
    # None 是合法 YAML 值，命中时必须与「未命中」区分开。
    assert (
        resolve_layer_default(
            tmp_path / "config-defaults.yaml", {"redis.*.mode": None}, "redis.general.mode"
        )
        is None
    )

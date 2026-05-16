#!/usr/bin/env python3
"""校验群头像商用端到端矩阵（E1–E4）证据 JSON 是否满足 commercial-e2e-matrix-runbook 零折扣口径。

用法:
  python3 agent_ops/avatar/verify_chat_avatar_commercial_matrix_evidence.py --manifest PATH

Manifest 为 YAML（推荐）或 JSON：见 artifacts/commercial-matrix/chat-avatar/manifest.sample.yaml

退出码: 0 通过；2 GATE_BLOCK。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

MATRIX_VERSION = 1
PROBE_SCENARIO_PREFIX = "chat.group_avatar.sync_display_e2e"
MATRIX_SCENARIO = "chat.group_avatar.sync_display_e2e.matrix"

SLOT_SPECS: dict[str, dict[str, str]] = {
    "e1_beta": {"probe_env": "beta", "matrix_env": "beta", "label": "E1 beta"},
    "e2_local_gamma": {
        "probe_env": "local-gamma",
        "matrix_env": "local-gamma",
        "label": "E2 local-gamma",
    },
    "e3_cloud_gamma_pre": {
        "probe_env": "gamma",
        "matrix_env": "gamma",
        "label": "E3 cloud-gamma-pre",
    },
    "e4_cloud_gamma_prod_smoke": {
        "probe_env": "gamma",
        "matrix_env": "gamma",
        "label": "E4 cloud-gamma-prod-smoke",
    },
}

DRY_RUN_PATTERNS = (
    re.compile(r'"dryRun"\s*:\s*true', re.IGNORECASE),
    re.compile(r"dry-run-device", re.IGNORECASE),
    re.compile(r'"dry_run"\s*:\s*true', re.IGNORECASE),
)


def load_manifest(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError as exc:
            raise SystemExit(
                "读取 YAML manifest 需要 PyYAML：pip install pyyaml "
                f"（rec-model-service requirements 已含）: {exc}"
            ) from exc
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            raise SystemExit("manifest 根节点必须是 mapping")
        return data
    if suffix == ".json":
        raw = json.loads(text)
        if not isinstance(raw, dict):
            raise SystemExit("manifest 根节点必须是 object")
        return raw
    raise SystemExit(f"不支持的 manifest 后缀: {suffix}（请用 .yaml / .yml / .json）")


def resolve_under(root: Path, raw: str | Path) -> Path:
    p = Path(raw)
    return p if p.is_absolute() else root / p


def raw_text_no_cheat(path: Path, *, label: str, errors: list[str]) -> None:
    body = path.read_text(encoding="utf-8", errors="replace")
    for rx in DRY_RUN_PATTERNS:
        if rx.search(body):
            errors.append(f"{label}: 禁止 dry-run / synthetic 证据（匹配 {rx.pattern!r} ）: {path}")


def load_json(path: Path, *, label: str, errors: list[str]) -> dict[str, Any] | None:
    if not path.exists():
        errors.append(f"{label}: 文件不存在 {path}")
        return None
    if path.stat().st_size == 0:
        errors.append(f"{label}: 文件为空 {path}")
        return None
    raw_text_no_cheat(path, label=label, errors=errors)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{label}: JSON 解析失败 {path}: {exc}")
        return None
    if not isinstance(data, dict):
        errors.append(f"{label}: 根节点须为 object: {path}")
        return None
    return data


def scenario_ok_probe(scenario: str) -> bool:
    return scenario == "chat.group_avatar.sync_display_e2e" or scenario.startswith(
        PROBE_SCENARIO_PREFIX + "."
    )


def check_probe_report(
    data: dict[str, Any],
    *,
    expect_env: str,
    label: str,
    errors: list[str],
) -> None:
    if data.get("schemaVersion") != 1:
        errors.append(f"{label}: schemaVersion 须为 1")
    scen = str(data.get("scenario") or "")
    if not scenario_ok_probe(scen):
        errors.append(f"{label}: scenario 须为 chat.group_avatar.sync_display_e2e*，实为 {scen!r}")
    if data.get("status") != "passed":
        errors.append(f"{label}: status 须为 passed，实为 {data.get('status')!r}")
    env = (data.get("environment") or {}) if isinstance(data.get("environment"), dict) else {}
    env_name = str(env.get("env") or "")
    if env_name != expect_env:
        errors.append(
            f"{label}: environment.env 须为 {expect_env!r}，实为 {env_name!r}",
        )


def check_matrix_report(
    data: dict[str, Any],
    *,
    expect_matrix_env: str,
    label: str,
    errors: list[str],
) -> None:
    if data.get("schemaVersion") != 1:
        errors.append(f"{label}: schemaVersion 须为 1")
    scen = str(data.get("scenario") or "")
    if scen != MATRIX_SCENARIO:
        errors.append(f"{label}: scenario 须为 {MATRIX_SCENARIO!r}，实为 {scen!r}")
    if data.get("status") != "passed":
        errors.append(f"{label}: status 须为 passed，实为 {data.get('status')!r}")

    envs = data.get("requestedEnvironments")
    if not isinstance(envs, list) or not envs:
        errors.append(f"{label}: requestedEnvironments 非空数组")
    elif expect_matrix_env not in [str(x) for x in envs]:
        errors.append(
            f"{label}: requestedEnvironments 须含 {expect_matrix_env!r}，实为 {envs!r}",
        )


def check_slot(slot_key: str, entry: Any, root: Path, errors: list[str]) -> None:
    if slot_key not in SLOT_SPECS:
        errors.append(f"未知 manifest 槽位 {slot_key!r}，允许: {sorted(SLOT_SPECS)}")
        return
    spec = SLOT_SPECS[slot_key]
    label = spec["label"]
    if not isinstance(entry, dict):
        errors.append(f"{label}: 槽位值须为 mapping")
        return

    def rp(raw: str | Path) -> Path:
        return resolve_under(root, raw)

    agg_raw = entry.get("aggregate")
    if agg_raw:
        agg_path = rp(str(agg_raw))
        agg = load_json(agg_path, label=f"{label} aggregate", errors=errors)
        if agg is None:
            return
        if agg.get("schemaVersion") != 1:
            errors.append(f"{label}: aggregate schemaVersion 须为 1")
        scen = str(agg.get("scenario") or "")
        if not scen.startswith("chat.group_avatar.sync_display_e2e.local_gamma"):
            errors.append(
                f"{label}: aggregate scenario 须以 chat.group_avatar.sync_display_e2e.local_gamma 为前缀，"
                f"实为 {scen!r}",
            )
        if agg.get("status") != "passed":
            errors.append(f"{label}: aggregate status 须为 passed，实为 {agg.get('status')!r}")
        probe_wrap = agg.get("probe") or {}
        pr = probe_wrap.get("report") if isinstance(probe_wrap, dict) else None
        if not isinstance(pr, dict):
            errors.append(f"{label}: aggregate.probe.report 缺失")
        else:
            check_probe_report(pr, expect_env=spec["probe_env"], label=f"{label}.probe", errors=errors)
        dm_wrap = agg.get("deviceMatrix") or {}
        dm = dm_wrap.get("report") if isinstance(dm_wrap, dict) else None
        if not isinstance(dm, dict):
            errors.append(f"{label}: aggregate.deviceMatrix.report 缺失")
        else:
            check_matrix_report(
                dm,
                expect_matrix_env=spec["matrix_env"],
                label=f"{label}.deviceMatrix",
                errors=errors,
            )
        return

    probe_raw = entry.get("probe")
    if not probe_raw:
        errors.append(f"{label}: 缺少 probe 路径或 aggregate")
        return
    probe = load_json(rp(str(probe_raw)), label=f"{label} probe", errors=errors)
    if probe:
        check_probe_report(
            probe,
            expect_env=spec["probe_env"],
            label=f"{label} probe",
            errors=errors,
        )

    for plat in ("android", "ios"):
        key = entry.get(plat)
        if not key:
            errors.append(f"{label}: 缺少 {plat} 设备矩阵报告路径")
            continue
        mr = load_json(rp(str(key)), label=f"{label} {plat}", errors=errors)
        if mr:
            check_matrix_report(
                mr,
                expect_matrix_env=spec["matrix_env"],
                label=f"{label} {plat} matrix",
                errors=errors,
            )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", required=True, help="YAML 或 JSON manifest 路径")
    ap.add_argument(
        "--repo-root",
        default=str(REPO_ROOT),
        help="仓库根（相对路径解析基准）",
    )
    args = ap.parse_args()
    root = Path(args.repo_root).resolve()

    mpath = resolve_under(root, args.manifest)
    manifest = load_manifest(mpath)
    ver = manifest.get("matrix_version")
    if ver != MATRIX_VERSION:
        print(f"[commercial-matrix] FAIL: matrix_version 须为 {MATRIX_VERSION}，实为 {ver!r}")
        return 2

    errors: list[str] = []
    for slot_key in SLOT_SPECS:
        if slot_key not in manifest:
            errors.append(f"缺少槽位 {slot_key}")
            continue
        check_slot(slot_key, manifest[slot_key], root, errors)

    if errors:
        print("[commercial-matrix] GATE_BLOCK")
        for line in errors:
            print(f"  - {line}")
        return 2

    try:
        shown = mpath.relative_to(root)
    except ValueError:
        shown = mpath
    print(f"[commercial-matrix] OK manifest={shown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""实体主页 build 真实链路：prepare 下发产出契约 + validate 采纳门。

与现行「三层目录实体」模型一致（entities/{领域}/{类型}/{名称}/）：
- prepare：读 effective task spec 的 scope.coverageTargets，为每个实体写
  inputs/entity_page/<ref>.json（含 SOP 模板路径、字数下限、region/season 菜单、
  effective conditionAxes、产出目录），并写 assistant_tasks 清单，下发给 Agent。
- Agent：按 SOP（sop/主页/<领域>/<类型>/{guide,template,example}.md，全局单一真相源、
  不拷进任务）在产出目录物化 page.md(≥800字)+_entity.json(含 conditionProfile)+manifest.json。
- validate：逐 coverage 实体校验三件套/字数/必填字段/conditionProfile 结构与取值是否
  落在 region_catalog/season_catalog 内，作为 promote 发布门之前的采纳门。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from _common.io import read_json, write_assistant_task, write_json
from _common.entity_page_quality import entity_page_quality_issues
from _common.paths import (
    batch_assistant_task,
    batch_command_root,
    batch_inputs_dir,
    task_data,
)
from _common.entity_extract import entity_ref, resolve_domain_etype

MIN_PAGE_CHARS = 800
_REQUIRED_ENTITY_FIELDS = ("label", "domain", "type", "sourceTaskId")
_ASSET_REF_RE = re.compile(r"asset://([A-Za-z0-9_./\u4e00-\u9fff-]+)")
# catalog 是 committed 真相源，按脚本相对路径定位（与 QWQ_DATA_ROOT 覆盖无关）
_CATALOG_DIR = Path(__file__).resolve().parents[2] / "templates" / "_registry" / "catalogs"


def _safe_ref(domain: str, etype: str, name: str) -> str:
    return f"{domain}__{etype}__{name}".replace("/", "_")


def _coverage_targets(spec: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for target in (spec.get("scope") or {}).get("coverageTargets") or []:
        name = str(target.get("name") or "").strip()
        if not name:
            continue
        domain, etype = resolve_domain_etype(target.get("entityType"))
        out.append({"name": name, "domain": domain, "etype": etype})
    return out


def _catalog_keys(filename: str, top_key: str) -> list[str]:
    path = _CATALOG_DIR / filename
    if not path.is_file():
        return []
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return list((doc.get(top_key) or {}).keys())


def region_keys() -> list[str]:
    return _catalog_keys("region_catalog.yaml", "regions")


def season_keys() -> list[str]:
    return _catalog_keys("season_catalog.yaml", "seasons")


def prepare_entity_pages(task_id: str, batch_id: str, spec: dict[str, Any]) -> tuple[Path, list[str]]:
    """为 coverage 实体下发实体主页产出契约（inputs + assistant_tasks）。"""
    inputs_dir = batch_inputs_dir(task_id, batch_id, "build", "entity_page")
    inputs_dir.mkdir(parents=True, exist_ok=True)
    axes = spec.get("conditionAxes") or {}
    data = task_data(task_id)
    refs: list[str] = []
    for target in _coverage_targets(spec):
        domain, etype, name = target["domain"], target["etype"], target["name"]
        ref = _safe_ref(domain, etype, name)
        sop_dir = data.sop_dir(domain, etype)
        write_json(inputs_dir / f"{ref}.json", {
            "schemaVersion": "quwoquan_data.stage_envelope",
            "taskId": task_id,
            "batchId": batch_id,
            "step": "entity_page",
            "ref": ref,
            "payload": {
                "name": name,
                "domain": domain,
                "etype": etype,
                "entityRef": entity_ref(domain, etype, name),
                "sopDir": str(sop_dir),
                "sopTemplate": str(sop_dir / "template.md"),
                "sopGuide": str(sop_dir / "guide.md"),
                "sopExample": str(sop_dir / "example.md"),
                "minChars": MIN_PAGE_CHARS,
                "conditionAxes": axes,
                "regionMenu": region_keys(),
                "seasonMenu": season_keys(),
                "outputDir": str(data.entity_dir(domain, etype, name)),
                "sourceTaskId": task_id,
            },
        })
        refs.append(ref)
    manifest_path = batch_assistant_task(task_id, batch_id, "build", "entity_page")
    results_dir = batch_command_root(task_id, batch_id, "build") / "results" / "entity_page"
    write_assistant_task(manifest_path, step="entity_page", input_dir=inputs_dir, result_dir=results_dir, refs=refs)
    return inputs_dir, refs


def _page_char_count(page: Path) -> int:
    text = page.read_text(encoding="utf-8")
    return len("".join(text.split()))


def _page_asset_refs(page: Path) -> set[str]:
    if not page.is_file():
        return set()
    refs: set[str] = set()
    for ref in _ASSET_REF_RE.findall(page.read_text(encoding="utf-8")):
        refs.add(ref.split("/")[-1])
    return refs


def _asset_closure_issues(entity_dir: Path, manifest_payload: dict[str, Any], label: str) -> list[str]:
    """实体主页 asset:// 引用闭环：page.md → manifest.assets → assets/<fileName>。"""
    refs = _page_asset_refs(entity_dir / "page.md")
    assets = manifest_payload.get("assets") or []
    if not refs and not assets:
        return []
    if not isinstance(assets, list):
        return [f"{label}: manifest.assets 须为数组"]
    id_to_file: dict[str, str] = {}
    file_names: set[str] = set()
    for raw in assets:
        if not isinstance(raw, dict):
            continue
        asset_id = str(raw.get("assetId") or raw.get("id") or "").strip()
        file_name = str(raw.get("fileName") or "").strip()
        if asset_id:
            id_to_file[asset_id] = file_name
        if file_name:
            file_names.add(file_name)
    issues: list[str] = []
    known_ids = set(id_to_file)
    for ref in sorted(refs):
        if ref not in known_ids and ref not in file_names:
            issues.append(f"{label}: page.md asset ref not in manifest: {ref}")
    assets_dir = entity_dir / "assets"
    for asset_id, file_name in sorted(id_to_file.items()):
        if not file_name:
            issues.append(f"{label}: asset {asset_id} missing fileName in manifest")
            continue
        if not (assets_dir / file_name).is_file():
            issues.append(f"{label}: asset file missing on disk: assets/{file_name} (assetId={asset_id})")
    return issues


def validate_entity_page(
    task_id: str,
    domain: str,
    etype: str,
    name: str,
    *,
    region_set: set[str],
    season_set: set[str],
) -> list[str]:
    """校验单个实体主页三件套/字数/字段/conditionProfile，返回阻断问题列表。"""
    data = task_data(task_id)
    page = data.entity_page(domain, etype, name)
    ejson = data.entity_json(domain, etype, name)
    manifest = data.entity_manifest(domain, etype, name)
    label = f"{domain}/{etype}/{name}"
    issues: list[str] = []

    if not page.is_file():
        issues.append(f"{label}: page.md 缺失")
    else:
        chars = _page_char_count(page)
        if chars < MIN_PAGE_CHARS:
            issues.append(f"{label}: page.md 去空白 {chars} 字 < {MIN_PAGE_CHARS}")
        issues.extend(entity_page_quality_issues(page, label=label))
    if not manifest.is_file():
        issues.append(f"{label}: manifest.json 缺失")
        manifest_payload: dict[str, Any] = {}
    else:
        try:
            manifest_payload = read_json(manifest)
        except Exception as exc:
            issues.append(f"{label}: manifest.json 不可解析: {exc}")
            manifest_payload = {}
    if not ejson.is_file():
        issues.append(f"{label}: _entity.json 缺失")
        return issues

    try:
        payload = read_json(ejson)
    except Exception as exc:
        issues.append(f"{label}: _entity.json 不可解析: {exc}")
        return issues

    for field in _REQUIRED_ENTITY_FIELDS:
        if not payload.get(field):
            issues.append(f"{label}: _entity.json 缺字段 {field}")
    if payload.get("domain") and payload["domain"] != domain:
        issues.append(f"{label}: _entity.json domain={payload['domain']} 与目录不一致")
    if payload.get("type") and payload["type"] != etype:
        issues.append(f"{label}: _entity.json type={payload['type']} 与目录不一致")

    cprofile = payload.get("conditionProfile")
    if cprofile is not None:
        if not isinstance(cprofile, dict):
            issues.append(f"{label}: conditionProfile 须为对象")
        else:
            regions = [str(r) for r in (cprofile.get("regions") or [])]
            seasons = [str(s) for s in (cprofile.get("seasons") or [])]
            if not regions and not seasons:
                issues.append(f"{label}: conditionProfile 须含 regions 或 seasons")
            bad_regions = [r for r in regions if r not in region_set]
            bad_seasons = [s for s in seasons if s not in season_set]
            if bad_regions:
                issues.append(f"{label}: conditionProfile.regions 越界 {bad_regions}（须 ∈ region_catalog）")
            if bad_seasons:
                issues.append(f"{label}: conditionProfile.seasons 越界 {bad_seasons}（须 ∈ season_catalog）")
    issues.extend(_asset_closure_issues(data.entity_dir(domain, etype, name), manifest_payload, label))
    return issues


def validate_entity_pages(task_id: str, spec: dict[str, Any]) -> list[str]:
    """校验全部 coverage 实体主页，返回阻断问题列表（空=采纳通过）。"""
    region_set = set(region_keys())
    season_set = set(season_keys())
    targets = _coverage_targets(spec)
    if not targets:
        return ["build validate: scope.coverageTargets 为空，无可校验实体"]
    issues: list[str] = []
    for target in targets:
        issues.extend(
            validate_entity_page(
                task_id,
                target["domain"],
                target["etype"],
                target["name"],
                region_set=region_set,
                season_set=season_set,
            )
        )
    return issues

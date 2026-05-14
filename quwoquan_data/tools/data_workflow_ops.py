from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import batch
import workflow_ops
from common import REPO_ROOT, RUNTIME_ROOT, crawl_spec_path_from_arg, ensure_runtime_layout, now_iso, read_json, read_ndjson, read_yaml, write_json, write_ndjson
from crawl_runtime_contract import load_entities_catalog, load_instruction_profile, selected_entities_path
from normalization.build_normalization_inputs import (
    build_authority_backcheck_input,
    build_escalation_input,
    build_extract_input,
    import_hydrated_topic_page_and_build_extract_input,
    build_review_input,
)
from normalization.compile_entity_resolution import compile_batch, materialize_entity_catalog
from normalization.fetch_source_bundle import fetch_source_bundle
from normalization.io_contracts import (
    NORMALIZATION_MANIFEST_SCHEMA_VERSION,
    assistant_batch_status_path,
    assistant_stage_task_manifest_path,
    ensure_normalization_layout,
    entity_resolution_path,
    image_resolution_path,
    input_schema_path,
    manifest_path,
    output_schema_path,
    pending_resolution_path,
    stage_input_path,
    source_resolution_path,
    stage_result_path,
    trace_report_path,
)
from normalization.source_ref import build_source_ref
from normalization.trace_source_resolution import build_trace_report
from semantic_entity_resolution import semantic_cluster_candidates_path, semantic_cluster_pending_path
from normalization.validators import (
    NormalizationValidationError,
    validate_input_file,
    validate_input_payload,
    validate_output_file,
    validate_output_payload,
)


def _ns(**kwargs: Any) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


def _csv(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _spec_path(spec_arg: str) -> Path:
    path = crawl_spec_path_from_arg(str(spec_arg or "").strip())
    if not path.exists():
        raise FileNotFoundError(f"spec 不存在 {path}")
    return path


def _load_spec(spec_arg: str) -> tuple[dict[str, Any], Path]:
    path = _spec_path(spec_arg)
    spec = read_yaml(path)
    if not isinstance(spec, dict):
        raise ValueError(f"spec 非法（非 YAML object）: {path}")
    return spec, path


def _catalog_from_args(spec_arg: str, catalog_arg: str) -> str:
    catalog = str(catalog_arg or "").strip()
    if catalog:
        return catalog
    if not str(spec_arg or "").strip():
        return ""
    spec, spec_path = _load_spec(spec_arg)
    ref = str(spec.get("article_topic_catalog_ref") or "").strip()
    if not ref:
        return ""
    return str((spec_path.parent.parent / ref).resolve())


def _geo_slice_report_path(*, catalog_config: str, report_out: str) -> Path | None:
    """解析 build_geo_poi_catalog 写入的 slice report 路径。"""
    explicit = str(report_out or "").strip()
    if explicit:
        path = Path(explicit)
        if not path.is_absolute():
            path = (REPO_ROOT / path).resolve()
        return path if path.is_file() else None
    cfg_raw = str(catalog_config or "").strip()
    if not cfg_raw:
        return None
    cfg_path = Path(cfg_raw)
    if not cfg_path.is_absolute():
        cfg_path = (REPO_ROOT / cfg_path).resolve()
    try:
        cfg = read_yaml(cfg_path)
    except (OSError, ValueError):
        return None
    if not isinstance(cfg, dict):
        return None
    defaults = dict(cfg.get("output_defaults") or {})
    ref = str(defaults.get("slice_report_ref") or "").strip()
    if not ref:
        return None
    path = (RUNTIME_ROOT / ref).resolve()
    return path if path.is_file() else None


def _mirror_geo_slice_report_beside_catalog(*, catalog_output: str, catalog_config: str, report_out: str) -> None:
    """将 slice 报告复制到 catalog 同名 `.slice_report.json`，以满足 verify_geo_catalog_quality 门禁。"""
    out_raw = str(catalog_output or "").strip()
    if not out_raw:
        return
    out_path = Path(out_raw)
    if not out_path.is_absolute():
        out_path = (REPO_ROOT / out_path).resolve()
    dest = out_path.with_suffix(".slice_report.json")
    src = _geo_slice_report_path(catalog_config=catalog_config, report_out=report_out)
    if src and src.resolve() != dest.resolve():
        shutil.copy2(src, dest)


def _stage_payload(stage: str, **payload: Any) -> int:
    print(
        json.dumps(
            {
                "ok": True,
                "stage": stage,
                "generatedAt": now_iso(),
                **payload,
            },
            ensure_ascii=False,
        )
    )
    return 0


def _waiting_payload(stage: str, *, exit_code: int = 2, **payload: Any) -> int:
    print(
        json.dumps(
            {
                "ok": False,
                "stage": stage,
                "generatedAt": now_iso(),
                **payload,
            },
            ensure_ascii=False,
        )
    )
    return exit_code


def _call_quiet(handler, args: argparse.Namespace) -> int:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        result = int(handler(args))
    if result != 0 and buffer.getvalue().strip():
        print(buffer.getvalue(), file=sys.stderr, end="" if buffer.getvalue().endswith("\n") else "\n")
    return result


def _run_verify_script(script_name: str) -> int:
    script_path = REPO_ROOT / "quwoquan_data" / "scripts" / "verify" / script_name
    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=REPO_ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        if result.stdout.strip():
            print(result.stdout, file=sys.stderr, end="" if result.stdout.endswith("\n") else "\n")
        if result.stderr.strip():
            print(result.stderr, file=sys.stderr, end="" if result.stderr.endswith("\n") else "\n")
    return result.returncode


def _run_geo_script(script_name: str, *args: str) -> int:
    script_path = REPO_ROOT / "quwoquan_data" / "tools" / "geo" / script_name
    result = subprocess.run(
        [sys.executable, str(script_path), *args],
        cwd=REPO_ROOT,
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        if result.stdout.strip():
            print(result.stdout, file=sys.stderr, end="" if result.stdout.endswith("\n") else "\n")
        if result.stderr.strip():
            print(result.stderr, file=sys.stderr, end="" if result.stderr.endswith("\n") else "\n")
    return result.returncode


def _read_catalog_rows(catalog_arg: str) -> list[dict[str, Any]]:
    raw = str(catalog_arg or "").strip()
    if not raw:
        return []
    path = Path(raw)
    if not path.is_absolute():
        path = (REPO_ROOT / raw).resolve()
    else:
        path = path.resolve()
    if not path.exists():
        raise FileNotFoundError(f"catalog 不存在 {path}")
    if path.suffix.lower() == ".ndjson":
        return read_ndjson(path)
    payload = read_yaml(path)
    if isinstance(payload, dict):
        rows = payload.get("attractions") or []
        return [row for row in rows if isinstance(row, dict)]
    return []


def _topic_catalog_rows_for_spec(spec: dict[str, Any], spec_path: Path) -> list[dict[str, Any]]:
    ref = str(spec.get("article_topic_catalog_ref") or "").strip()
    if not ref:
        return []
    path = (spec_path.parent.parent / ref).resolve()
    return read_ndjson(path)


def _selected_entities_for_spec(spec: dict[str, Any]) -> list[dict[str, Any]]:
    spec_id = str(spec.get("spec_id", "")).strip()
    if spec_id and selected_entities_path(spec_id).exists():
        return read_ndjson(selected_entities_path(spec_id))
    return load_entities_catalog()


def _upsert_normalization_manifest(batch_label: str, **updates: Any) -> dict[str, Any]:
    ensure_normalization_layout(batch_label)
    path = manifest_path(batch_label)
    payload: dict[str, Any]
    if path.exists():
        payload = read_json(path)
        if not isinstance(payload, dict):
            payload = {}
    else:
        payload = {}
    payload.setdefault("schemaVersion", NORMALIZATION_MANIFEST_SCHEMA_VERSION)
    payload.setdefault("batchLabel", batch_label)
    payload.setdefault("status", "running")
    payload.setdefault("artifacts", {})
    payload.setdefault("warnings", [])
    for key, value in updates.items():
        if key == "artifacts" and isinstance(value, dict):
            payload["artifacts"].update(value)
        elif key == "warnings" and isinstance(value, list):
            existing = payload.setdefault("warnings", [])
            if isinstance(existing, list):
                existing.extend(str(item).strip() for item in value if str(item).strip())
        else:
            payload[key] = value
    write_json(path, payload)
    return payload


def _resolve_source_ref_for_batch(*, batch_label: str, source_ref: str = "", source_md: str = "", source_url: str = "") -> str:
    if str(source_ref or "").strip():
        return str(source_ref).strip()
    if str(source_md or "").strip():
        md_path = Path(str(source_md).strip())
        if not md_path.is_absolute():
            md_path = md_path.resolve()
        bundle_path = md_path.parent / "page.json"
        if bundle_path.exists():
            bundle = read_json(bundle_path)
            if isinstance(bundle, dict):
                ref = str(bundle.get("sourceRef", "")).strip()
                if ref:
                    return ref
    if str(source_url or "").strip():
        extract_dir = stage_result_path(batch_label, "extract", "placeholder").parent
        for path in sorted(extract_dir.glob("*.json")):
            payload = read_json(path)
            if not isinstance(payload, dict):
                continue
            if str(payload.get("sourceUrl", "")).strip() == str(source_url).strip():
                ref = str(payload.get("sourceRef", "")).strip()
                if ref:
                    return ref
        return build_source_ref(source_url=str(source_url).strip())
    raise ValueError("需要 source_ref/source_md/source_url 之一")


def handle_data_explore(args) -> int:
    spec_arg = str(getattr(args, "spec", "") or "").strip()
    payload: dict[str, Any] = {
        "query": str(getattr(args, "query", "") or "").strip(),
        "regions": _csv(getattr(args, "regions", "")),
        "entityTypes": _csv(getattr(args, "entity_types", "")),
        "notes": str(getattr(args, "notes", "") or "").strip(),
    }
    if spec_arg:
        spec, spec_path = _load_spec(spec_arg)
        payload["spec"] = str(spec_path)
        payload["specId"] = str(spec.get("spec_id", "")).strip()
    return _stage_payload("data-explore", **payload)


def handle_data_baseline(args) -> int:
    checks = {
        "specDoc": str(getattr(args, "spec_doc", "") or "").strip(),
        "designDoc": str(getattr(args, "design_doc", "") or "").strip(),
        "acceptanceDoc": str(getattr(args, "acceptance_doc", "") or "").strip(),
        "workflowDoc": str(getattr(args, "workflow_doc", "") or "").strip(),
        "commandMatrixDoc": str(getattr(args, "command_matrix_doc", "") or "").strip(),
        "catalogConfig": str(getattr(args, "catalog_config", "") or "").strip(),
        "namingRules": str(getattr(args, "naming_rules", "") or "").strip(),
        "geoBandRules": str(getattr(args, "geo_band_rules", "") or "").strip(),
    }
    missing: list[str] = []
    resolved: dict[str, str] = {}
    for key, raw in checks.items():
        if not raw:
            continue
        path = Path(raw)
        if not path.is_absolute():
            path = (REPO_ROOT / raw).resolve()
        else:
            path = path.resolve()
        resolved[key] = str(path)
        if not path.exists():
            missing.append(str(path))
    schema_files = [str(item).strip() for item in (getattr(args, "schema_files", []) or []) if str(item).strip()]
    resolved_schema_files: list[str] = []
    for raw in schema_files:
        path = Path(raw)
        if not path.is_absolute():
            path = (REPO_ROOT / raw).resolve()
        else:
            path = path.resolve()
        resolved_schema_files.append(str(path))
        if not path.exists():
            missing.append(str(path))
    if missing:
        for item in missing:
            print(f"[data baseline] FAIL: 缺少基线文件 {item}", file=sys.stderr)
        return 1

    catalog_cfg = resolved.get("catalogConfig", "").strip()
    geo_band_arg = resolved.get("geoBandRules", "").strip()
    if catalog_cfg and geo_band_arg:
        cfg_path = Path(catalog_cfg)
        try:
            cfg = read_yaml(cfg_path)
        except (OSError, ValueError) as exc:
            print(f"[data baseline] FAIL: 无法读取 catalog-config {cfg_path}: {exc}", file=sys.stderr)
            return 1
        if not isinstance(cfg, dict):
            print(f"[data baseline] FAIL: catalog-config 非法（非 object）{cfg_path}", file=sys.stderr)
            return 1
        ref = str(cfg.get("geo_band_rules_path") or "").strip()
        if not ref:
            print(
                "[data baseline] FAIL: 同时传入 --catalog-config 与 --geo-band-rules 时，"
                "catalog 内必须含 geo_band_rules_path",
                file=sys.stderr,
                )
            return 1
        expected = (cfg_path.parent / ref).resolve()
        actual = Path(geo_band_arg).resolve()
        if expected != actual:
            print(
                "[data baseline] FAIL: --geo-band-rules 与 catalog-config 内 geo_band_rules_path 解析路径不一致\n"
                f"  期望 {expected}\n  实际 {actual}",
                file=sys.stderr,
            )
            return 1

    return _stage_payload("data-baseline", files=resolved, schemaFiles=resolved_schema_files)


def _build_entities_tags_catalog_and_entity(args) -> int:
    """Phase all / catalog / entity-tag: geo catalog + entity_catalog + tag_catalog."""
    catalog_config = str(getattr(args, "catalog_config", "") or "").strip()
    catalog_output = str(getattr(args, "catalog_output", "") or "").strip()
    report_out = str(getattr(args, "report_out", "") or "").strip()
    catalog_inputs = [str(item).strip() for item in (getattr(args, "catalog_inputs", []) or []) if str(item).strip()]
    phase = str(getattr(args, "phase", "all") or "all").strip()

    if catalog_config and phase in ("all", "catalog"):
        geo_args: list[str] = ["--config", catalog_config]
        if catalog_output:
            geo_args.extend(["--output", catalog_output])
        else:
            print("[data build-entities-tags] FAIL: 使用 --catalog-config 时必须同时提供 --catalog-output", file=sys.stderr)
            return 1
        if report_out:
            geo_args.extend(["--report-out", report_out])
        if catalog_inputs:
            geo_args.extend(["--inputs", *catalog_inputs])
        if bool(getattr(args, "catalog_no_fetch", False)):
            geo_args.append("--no-fetch")
        if bool(getattr(args, "catalog_no_name_dedupe", False)):
            geo_args.append("--no-name-dedupe")
        if bool(getattr(args, "catalog_province_wide_query", False)):
            geo_args.append("--province-wide-query")
        if _run_geo_script("build_geo_poi_catalog.py", *geo_args) != 0:
            return 1
        _mirror_geo_slice_report_beside_catalog(
            catalog_output=catalog_output,
            catalog_config=catalog_config,
            report_out=report_out,
        )

    if phase == "catalog":
        return _stage_payload("data-build-entities-tags", phase=phase, catalogOutput=catalog_output)

    catalog = _catalog_from_args(str(getattr(args, "spec", "") or ""), str(getattr(args, "catalog", "") or ""))
    if catalog_output:
        catalog = str(Path(catalog_output).resolve())
    if not bool(getattr(args, "skip_tag_catalog", False)):
        if _call_quiet(workflow_ops.handle_tag_catalog_build, _ns()) != 0:
            return 1
    if not bool(getattr(args, "skip_entity_catalog", False)):
        if _call_quiet(workflow_ops.handle_entity_catalog_build, _ns(catalog=catalog)) != 0:
            return 1
    semantic_candidates = semantic_cluster_candidates_path()
    semantic_pending = semantic_cluster_pending_path()
    return _stage_payload(
        "data-build-entities-tags",
        phase=phase,
        catalog=catalog,
        catalogConfig=catalog_config,
        reportOut=report_out,
        semanticCandidates=str(semantic_candidates) if semantic_candidates.exists() else "",
        semanticPending=str(semantic_pending) if semantic_pending.exists() else "",
        skipTagCatalog=bool(getattr(args, "skip_tag_catalog", False)),
        skipEntityCatalog=bool(getattr(args, "skip_entity_catalog", False)),
    )


def _build_entities_tags_normalize_prepare(args) -> int:
    """Phase normalize-prepare: prepare extract inputs + write assistant task manifest."""
    spec_arg = str(getattr(args, "spec", "") or "").strip()
    if not spec_arg:
        print("[data build-entities-tags --phase normalize-prepare] FAIL: 需要 --spec", file=sys.stderr)
        return 1
    spec, spec_path = _load_spec(spec_arg)
    spec_id = str(spec.get("spec_id", "")).strip()
    batch_label = str(getattr(args, "batch_label", "") or "").strip() or spec_id
    topics_filter = {item.strip() for item in str(getattr(args, "topics", "") or "").split(",") if item.strip()}
    try:
        prepare = _prepare_topic_inputs(
            spec=spec,
            spec_path=spec_path,
            batch_label=batch_label,
            topics_filter=topics_filter,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"[data build-entities-tags --phase normalize-prepare] FAIL: {exc}", file=sys.stderr)
        return 1
    extract_paths = [Path(p) for p in prepare["extractInputPaths"]]
    if not extract_paths:
        print("[data build-entities-tags --phase normalize-prepare] FAIL: 没有生成 extract input", file=sys.stderr)
        return 1
    tasks: list[dict[str, Any]] = []
    for path in extract_paths:
        input_payload = validate_input_file("extract", path)
        tasks.append(_assistant_task_item("extract", input_payload, path))
    manifest = _write_assistant_task_manifest(
        batch_label=batch_label,
        stage="extract",
        spec_path=str(spec_path),
        topics=sorted(topics_filter),
        tasks=tasks,
    )
    return _stage_payload(
        "data-build-entities-tags",
        phase="normalize-prepare",
        batchLabel=batch_label,
        extractInputCount=len(extract_paths),
        assistantTaskManifestPath=str(manifest),
    )


def _build_entities_tags_normalize_validate(args) -> int:
    """Phase normalize-validate: check programming assistant results exist and pass schema."""
    batch_label = str(getattr(args, "batch_label", "") or "").strip()
    if not batch_label:
        print("[data build-entities-tags --phase normalize-validate] FAIL: 需要 --batch-label", file=sys.stderr)
        return 1
    stage = str(getattr(args, "stage", "") or "").strip()
    spec_arg = str(getattr(args, "spec", "") or "").strip()
    spec_path = spec_arg
    topics_filter = {item.strip() for item in str(getattr(args, "topics", "") or "").split(",") if item.strip()}
    stages_to_validate = [stage] if stage else ["extract", "review", "authority", "escalate"]
    for st in stages_to_validate:
        paths = _resolve_stage_paths(batch_label=batch_label, stage=st, kind="input")
        if not paths:
            continue
        try:
            _validate_stage_results_or_raise(
                batch_label=batch_label,
                stage=st,
                paths=paths,
                spec_path=spec_path,
                topics=sorted(topics_filter),
            )
        except AssistantTaskPendingError as exc:
            return _waiting_payload("data-build-entities-tags", phase="normalize-validate", **exc.payload)
        except (NormalizationValidationError, FileNotFoundError, ValueError) as exc:
            print(f"[data build-entities-tags --phase normalize-validate] FAIL ({st}): {exc}", file=sys.stderr)
            return 1
        _build_followup_stage_inputs(batch_label, st)
    return _stage_payload("data-build-entities-tags", phase="normalize-validate", batchLabel=batch_label, stages=stages_to_validate)


def _build_entities_tags_compile(args) -> int:
    """Phase compile: compile normalization results into entity resolution."""
    batch_label = str(getattr(args, "batch_label", "") or "").strip()
    if not batch_label:
        print("[data build-entities-tags --phase compile] FAIL: 需要 --batch-label", file=sys.stderr)
        return 1
    try:
        summary = compile_batch(batch_label)
    except (FileNotFoundError, ValueError) as exc:
        print(f"[data build-entities-tags --phase compile] FAIL: {exc}", file=sys.stderr)
        return 1
    return _stage_payload("data-build-entities-tags", phase="compile", batchLabel=batch_label, compileSummary=summary)


def _build_entities_tags_materialize(args) -> int:
    """Phase materialize: write normalized entities into entity_catalog/entities.ndjson."""
    batch_label = str(getattr(args, "batch_label", "") or "").strip()
    if not batch_label:
        print("[data build-entities-tags --phase materialize] FAIL: 需要 --batch-label", file=sys.stderr)
        return 1
    catalog_arg = str(getattr(args, "catalog", "") or "").strip() or _catalog_from_args(str(getattr(args, "spec", "") or ""), "")
    output_name = str(getattr(args, "output_name", "") or "").strip() or f"{batch_label}_normalized_entities.ndjson"
    try:
        result = materialize_entity_catalog(
            batch_label=batch_label,
            catalog_rows=_read_catalog_rows(catalog_arg),
            output_name=output_name,
        )
        _upsert_normalization_manifest(batch_label, status="ready")
    except (FileNotFoundError, ValueError) as exc:
        print(f"[data build-entities-tags --phase materialize] FAIL: {exc}", file=sys.stderr)
        return 1
    return _stage_payload("data-build-entities-tags", phase="materialize", batchLabel=batch_label)


_PHASE_DISPATCH = {
    "all": _build_entities_tags_catalog_and_entity,
    "catalog": _build_entities_tags_catalog_and_entity,
    "entity-tag": _build_entities_tags_catalog_and_entity,
    "normalize-prepare": _build_entities_tags_normalize_prepare,
    "normalize-validate": _build_entities_tags_normalize_validate,
    "compile": _build_entities_tags_compile,
    "materialize": _build_entities_tags_materialize,
}


def handle_data_build_entities_tags(args) -> int:
    ensure_runtime_layout()
    phase = str(getattr(args, "phase", "all") or "all").strip()
    handler = _PHASE_DISPATCH.get(phase)
    if not handler:
        print(f"[data build-entities-tags] FAIL: 未知 phase={phase}", file=sys.stderr)
        return 1
    return handler(args)


def handle_data_download(args) -> int:
    ensure_runtime_layout()
    spec_arg = str(getattr(args, "spec", "") or "").strip()
    spec, spec_path = _load_spec(spec_arg)
    spec_id = str(spec.get("spec_id", "") or "").strip()
    if spec_id and not load_instruction_profile(spec_id):
        if _call_quiet(workflow_ops.handle_instruction_build, _ns(spec=str(spec_path))) != 0:
            return 1

    topics_csv = str(getattr(args, "topics", "") or "").strip()
    sel_path = selected_entities_path(spec_id) if spec_id else None
    _img_suffix = "__img"
    if sel_path and not topics_csv and bool(spec.get("include_all_catalog_entities")):
        if sel_path.exists():
            sel_path.unlink()
    if topics_csv and spec_id and sel_path:
        tid_set = {t.strip() for t in topics_csv.split(",") if t.strip()}
        base_topic_ids: set[str] = set()
        for tid in tid_set:
            if tid.endswith(_img_suffix):
                base_topic_ids.add(tid[: -len(_img_suffix)])
            else:
                base_topic_ids.add(tid)
        entities = load_entities_catalog()
        selected = [e for e in entities if str(e.get("topicId", "")).strip() in base_topic_ids]
        write_ndjson(sel_path, selected)

    if not bool(getattr(args, "skip_authority_sync", False)):
        if _call_quiet(workflow_ops.handle_authority_sync, _ns(spec=str(spec_path), spec_id="")) != 0:
            return 1
        if _call_quiet(workflow_ops.handle_authority_review, _ns(spec=str(spec_path), spec_id="")) != 0:
            return 1

    if not bool(getattr(args, "skip_pool_bootstrap", False)):
        if _call_quiet(
            batch.handle_pool_bootstrap,
            _ns(
                spec=str(spec_path),
                catalog=str(getattr(args, "catalog", "") or ""),
                merge=bool(getattr(args, "merge", False)),
                topics=str(getattr(args, "topics", "") or ""),
                travel_seed=str(getattr(args, "travel_seed", "") or ""),
                max_sources=int(getattr(args, "max_sources", 22) or 22),
                wiki_expand=str(getattr(args, "wiki_expand", "filtered") or "filtered"),
                wiki_link_budget=int(getattr(args, "wiki_link_budget", 40) or 40),
                baike_link_budget=int(getattr(args, "baike_link_budget", 24) or 24),
                wikivoyage_limit=int(getattr(args, "wikivoyage_limit", 12) or 12),
                sleep=float(getattr(args, "sleep", 0.35) or 0.35),
                skip_baike_scrape=bool(getattr(args, "skip_baike_scrape", False)),
            )
        ) != 0:
            return 1

    if not bool(getattr(args, "skip_spec_discovery", False)):
        if _call_quiet(
            batch.handle_spec_discovery,
            _ns(
                spec=str(spec_path),
                skip_hydrate=bool(getattr(args, "skip_hydrate", False)),
                topics=str(getattr(args, "topics", "") or ""),
            ),
        ) != 0:
            return 1

    fetch_seed_arg = str(getattr(args, "fetch_seed", "") or "").strip()
    if fetch_seed_arg:
        fetch_seed_path = Path(fetch_seed_arg)
        if not fetch_seed_path.is_absolute():
            fetch_seed_path = (REPO_ROOT / fetch_seed_arg).resolve()
        else:
            fetch_seed_path = fetch_seed_path.resolve()
        rows = read_ndjson(fetch_seed_path)
        for row in rows:
            if not isinstance(row, dict):
                continue
            topic_id = str(row.get("topicId") or row.get("topic_id") or "").strip()
            task_type = str(row.get("taskType") or row.get("task_type") or "").strip() or "article"
            source_url = str(row.get("sourceUrl") or row.get("url") or "").strip()
            source_id = str(row.get("sourceId") or row.get("source_id") or "").strip() or f"{topic_id}_{task_type}_manual"
            if not topic_id or not source_url:
                continue
            if _call_quiet(
                batch.handle_fetch_source,
                _ns(
                    spec=str(spec_path),
                    topic=topic_id,
                    task_type=task_type,
                    source_id=source_id,
                    url=source_url,
                    title=str(row.get("title", "")).strip(),
                    query=str(row.get("query", "")).strip(),
                    snippet=str(row.get("snippet", "")).strip(),
                    source_role=str(row.get("sourceRole") or row.get("source_role") or "publish_candidate").strip() or "publish_candidate",
                    rights_status=str(row.get("rightsStatus") or row.get("rights_status") or "clear").strip() or "clear",
                    watermark_status=str(row.get("watermarkStatus") or row.get("watermark_status") or "clean").strip() or "clean",
                ),
            ) != 0:
                return 1

    if not bool(getattr(args, "skip_content_discover", False)):
        if _call_quiet(
            workflow_ops.handle_content_discover,
            _ns(
                spec=str(spec_path),
                spec_id="",
                seed=str(getattr(args, "seed", "") or ""),
            )
        ) != 0:
            return 1

    if not bool(getattr(args, "skip_hydrate", False)):
        topics_arg = str(getattr(args, "topics", "") or "")
        if _call_quiet(
            workflow_ops.handle_content_hydrate,
            _ns(spec=str(spec_path), spec_id="", topics=topics_arg),
        ) != 0:
            return 1

    return _stage_payload(
        "data-download",
        specId=str(spec.get("spec_id", "")).strip(),
        spec=str(spec_path),
        topics=_csv(getattr(args, "topics", "")),
        fetchSeed=fetch_seed_arg,
        skipHydrate=bool(getattr(args, "skip_hydrate", False)),
    )


def _process_content_assistant_phase(args, phase: str) -> int:
    """Generate an assistant task manifest for content processing phases."""
    spec_arg = str(getattr(args, "spec", "") or "").strip()
    spec, spec_path = _load_spec(spec_arg)
    spec_id = str(spec.get("spec_id", "")).strip()
    batch_label = str(getattr(args, "batch_label", "") or "").strip() or spec_id
    topics_csv = str(getattr(args, "topics", "") or "").strip()
    topics_list = [t.strip() for t in topics_csv.split(",") if t.strip()]
    stage_map = {
        "quality-analysis": "content_quality",
        "generate": "content_generate",
        "backfill": "content_backfill",
    }
    stage = stage_map[phase]
    instructions_map = {
        "content_quality": "分析下载内容的质量（准确性、完整性、时效性、可读性），标记需要润色或重写的段落。",
        "content_generate": "基于质量分析结果，润色/改写/生成高质量的文章或图文描述。",
        "content_backfill": "补全内容中缺失的实体引用和标签关联。",
    }
    tasks: list[dict[str, Any]] = []
    for i, topic in enumerate(topics_list):
        tasks.append({
            "sourceRef": topic,
            "sourceUrl": "",
            "sourceTitle": topic,
            "inputPath": str(spec_path),
            "expectedResultPath": str(RUNTIME_ROOT / "runs" / batch_label / "content" / phase / f"{topic}.json"),
            "assistantCommand": f"/data-process-content --phase {phase}",
            "assistantCommandDoc": str(REPO_ROOT / ".cursor" / "commands" / "data-process-content.md"),
            "inputSchemaPath": "",
            "outputSchemaPath": "",
            "processingSummary": instructions_map[stage],
            "selfCheckCommands": [],
        })
    if tasks:
        ensure_normalization_layout(batch_label)
        manifest_dir = RUNTIME_ROOT / "runs" / batch_label / "content" / "assistant_tasks"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = manifest_dir / f"{phase}.json"
        write_json(manifest_path, {
            "schemaVersion": "quwoquan_data.normalization.assistant_task_manifest",
            "batchLabel": batch_label,
            "stage": stage,
            "status": "waiting_for_programming_assistant",
            "assistantCommand": f"/data-process-content --phase {phase}",
            "assistantCommandDoc": str(REPO_ROOT / ".cursor" / "commands" / "data-process-content.md"),
            "specPath": str(spec_path),
            "topics": topics_list,
            "taskCount": len(tasks),
            "tasks": tasks,
        })
        return _stage_payload(
            "data-process-content",
            phase=phase,
            batchLabel=batch_label,
            assistantTaskManifestPath=str(manifest_path),
            taskCount=len(tasks),
        )
    return _stage_payload("data-process-content", phase=phase, batchLabel=batch_label, taskCount=0)


def handle_data_process_content(args) -> int:
    ensure_runtime_layout()
    phase = str(getattr(args, "phase", "all") or "all").strip()
    if phase in ("quality-analysis", "generate", "backfill"):
        return _process_content_assistant_phase(args, phase)
    spec_arg = str(getattr(args, "spec", "") or "").strip()
    spec, spec_path = _load_spec(spec_arg)
    topics = str(getattr(args, "topics", "") or "")
    targets = str(getattr(args, "targets", "") or "")

    if phase in ("all", "review"):
        if _call_quiet(workflow_ops.handle_content_review, _ns(spec=str(spec_path), spec_id="")) != 0:
            return 1
    if phase in ("all", "compose"):
        if _call_quiet(
            workflow_ops.handle_compose_post,
            _ns(spec=str(spec_path), topic="", topics=topics, targets=targets),
        ) != 0:
            return 1
        if _call_quiet(workflow_ops.handle_review_generated, _ns(spec=str(spec_path), topic="", topics=topics)) != 0:
            return 1
    return _stage_payload(
        "data-process-content",
        phase=phase,
        specId=str(spec.get("spec_id", "")).strip(),
        spec=str(spec_path),
        topics=_csv(topics),
        targets=_csv(targets or spec.get("target_envs")),
    )


def handle_data_build_content(args) -> int:
    """兼容旧阶段名；统一委托到 `data-process-content`。"""
    return handle_data_process_content(args)


def handle_data_publish(args) -> int:
    ensure_runtime_layout()
    spec_arg = str(getattr(args, "spec", "") or "").strip()
    spec, spec_path = _load_spec(spec_arg)
    topics = str(getattr(args, "topics", "") or "")

    if _call_quiet(workflow_ops.handle_publish_approved, _ns(spec=str(spec_path), topic="", topics=topics)) != 0:
        return 1

    if not bool(getattr(args, "skip_feedback", False)):
        if _call_quiet(workflow_ops.handle_feedback_extract, _ns(spec=str(spec_path), topic="", topics=topics)) != 0:
            return 1
        if _call_quiet(workflow_ops.handle_feedback_verify, _ns(spec=str(spec_path))) != 0:
            return 1

    if not bool(getattr(args, "skip_verify", False)):
        if _run_verify_script("verify_quwoquan_data_source_authenticity.py") != 0:
            return 1
        if _run_verify_script("verify_quwoquan_data_post_packages.py") != 0:
            return 1

    return _stage_payload(
        "data-publish",
        specId=str(spec.get("spec_id", "")).strip(),
        spec=str(spec_path),
        topics=_csv(topics),
        skipFeedback=bool(getattr(args, "skip_feedback", False)),
        skipVerify=bool(getattr(args, "skip_verify", False)),
    )


def handle_data_source_fetch(args) -> int:
    ensure_runtime_layout()
    batch_label = str(getattr(args, "batch_label", "") or "").strip()
    if not batch_label:
        print("[data source-fetch] FAIL: 需要 --batch-label", file=sys.stderr)
        return 1
    input_payload = {
        "schemaVersion": "quwoquan_data.normalization.source_fetch_input",
        "batchLabel": batch_label,
        "catalogTopicId": str(getattr(args, "catalog_topic", "") or "").strip(),
        "catalogName": str(getattr(args, "catalog_name", "") or "").strip(),
        "sourceType": str(getattr(args, "source_type", "") or "article").strip() or "article",
        "sourceUrl": str(getattr(args, "source_url", "") or "").strip(),
        "pageTitle": str(getattr(args, "page_title", "") or "").strip(),
        "maxAssets": int(getattr(args, "max_assets", 8) or 8),
    }
    try:
        validate_input_payload("fetch", input_payload)
        bundle = fetch_source_bundle(
            batch_label=batch_label,
            source_url=input_payload["sourceUrl"],
            page_title=input_payload["pageTitle"],
            catalog_topic_id=input_payload["catalogTopicId"],
            catalog_name=input_payload["catalogName"],
            source_type=input_payload["sourceType"],
            max_assets=input_payload["maxAssets"],
        )
        validate_output_payload("fetch", bundle)
    except (NormalizationValidationError, FileNotFoundError, ValueError) as exc:
        print(f"[data source-fetch] FAIL: {exc}", file=sys.stderr)
        return 1
    input_with_ref = dict(input_payload)
    input_with_ref["sourceRef"] = str(bundle.get("sourceRef", "")).strip()
    write_json(stage_input_path(batch_label, "fetch", input_with_ref["sourceRef"]), input_with_ref)
    write_json(stage_result_path(batch_label, "fetch", input_with_ref["sourceRef"]), bundle)
    _upsert_normalization_manifest(
        batch_label,
        artifacts={
            f"source.bundle.{bundle['sourceRef']}": str(bundle.get("markdownPath") or ""),
        },
    )
    return _stage_payload(
        "data-source-fetch",
        status="ready",
        trace={
            "sourceUrl": bundle["sourceUrl"],
            "pageTitle": bundle["pageTitle"],
            "sourceMarkdownPath": bundle["markdownPath"],
            "catalogTopicId": bundle.get("catalogTopicId", ""),
            "catalogName": bundle.get("catalogName", ""),
        },
        inputs=input_payload,
        outputs={
            "bundlePath": str(bundle.get("markdownPath") or ""),
            "assetManifestPath": str(bundle.get("assetManifestPath") or ""),
            "sourceRef": bundle["sourceRef"],
        },
        metrics={"assetCount": int(bundle.get("assetCount") or 0), "paragraphCount": int(bundle.get("paragraphCount") or 0)},
        warnings=bundle.get("warnings") or [],
        nextActions=["data normalize-build-extract-input"],
    )


def _prepare_topic_inputs(
    *,
    spec: dict[str, Any],
    spec_path: Path,
    batch_label: str,
    topics_filter: set[str],
) -> dict[str, Any]:
    spec_id = str(spec.get("spec_id", "")).strip()
    topic_rows = _topic_catalog_rows_for_spec(spec, spec_path)
    topic_rows = [row for row in topic_rows if isinstance(row, dict)]
    if topics_filter:
        topic_rows = [row for row in topic_rows if str(row.get("topic_id", "")).strip() in topics_filter]
    prepared_inputs: list[str] = []
    source_refs: list[str] = []
    warnings: list[str] = []
    hydrated_source_count = 0
    for topic_row in topic_rows:
        topic_id = str(topic_row.get("topic_id", "")).strip()
        topic_dir = batch.run_topic_dir(spec_id, topic_id)
        pool_rows = read_ndjson(topic_dir / "source_pool.ndjson")
        for row in pool_rows:
            if not isinstance(row, dict):
                continue
            source_id = str(row.get("sourceId") or row.get("candidateId") or "").strip()
            if not source_id:
                continue
            page_dir = topic_dir / "pages" / source_id
            if not (page_dir / "source.md").exists():
                continue
            hydrated_source_count += 1
            try:
                payload = import_hydrated_topic_page_and_build_extract_input(
                    batch_label=batch_label,
                    spec_id=spec_id,
                    catalog_topic_id=topic_id,
                    catalog_name=str(topic_row.get("name") or "").strip(),
                    source_row=row,
                    page_dir=page_dir,
                )
                prepared_inputs.append(str(stage_input_path(payload["batchLabel"], "extract", payload["sourceRef"])))
                source_refs.append(str(payload["sourceRef"]))
            except (FileNotFoundError, ValueError) as exc:
                warnings.append(f"topic={topic_id} source={source_id}: {exc}")
    return {
        "specId": spec_id,
        "topicRows": topic_rows,
        "extractInputPaths": prepared_inputs,
        "sourceRefs": source_refs,
        "hydratedSourceCount": hydrated_source_count,
        "warnings": warnings,
    }


def handle_data_normalize_prepare_topic_inputs(args) -> int:
    spec_arg = str(getattr(args, "spec", "") or "").strip()
    spec, spec_path = _load_spec(spec_arg)
    spec_id = str(spec.get("spec_id", "")).strip()
    batch_label = str(getattr(args, "batch_label", "") or "").strip() or spec_id
    topics_filter = {item.strip() for item in str(getattr(args, "topics", "") or "").split(",") if item.strip()}
    prepared = _prepare_topic_inputs(
        spec=spec,
        spec_path=spec_path,
        batch_label=batch_label,
        topics_filter=topics_filter,
    )
    return _stage_payload(
        "data-normalize-prepare-topic-inputs",
        status="ready",
        trace={"specId": spec_id, "batchLabel": batch_label},
        inputs={"spec": str(spec_path), "topics": sorted(topics_filter)},
        outputs={
            "extractInputPaths": prepared["extractInputPaths"],
            "sourceRefs": prepared["sourceRefs"],
        },
        metrics={
            "topicCount": len(prepared["topicRows"]),
            "hydratedSourceCount": prepared["hydratedSourceCount"],
            "extractInputCount": len(prepared["extractInputPaths"]),
        },
        warnings=prepared["warnings"],
        nextActions=["cursor command /data-normalize-extract-source"],
    )


def _stage_io_dir(batch_label: str, stage: str, kind: str) -> Path:
    if kind == "input":
        return stage_input_path(batch_label, stage, "placeholder").parent
    return stage_result_path(batch_label, stage, "placeholder").parent


def _resolve_stage_paths(*, batch_label: str, stage: str, kind: str, input_arg: str = "", source_ref: str = "") -> list[Path]:
    raw = str(input_arg or "").strip()
    if raw:
        path = Path(raw)
        if not path.is_absolute():
            path = (REPO_ROOT / raw).resolve()
        else:
            path = path.resolve()
        return [path]
    if source_ref:
        if kind == "input":
            return [stage_input_path(batch_label, stage, source_ref)]
        return [stage_result_path(batch_label, stage, source_ref)]
    directory = _stage_io_dir(batch_label, stage, kind)
    if not directory.exists():
        return []
    return sorted(directory.glob("*.json"))


ASSISTANT_STAGE_COMMANDS = {
    "extract": "/data-normalize-extract-source",
    "review": "/data-normalize-review-source",
    "authority": "/data-normalize-authority-source",
    "escalate": "/data-normalize-escalate-source",
}

ASSISTANT_STAGE_DOC_FILENAMES = {
    "extract": "data-normalize-extract-source.md",
    "review": "data-normalize-review-source.md",
    "authority": "data-normalize-authority-source.md",
    "escalate": "data-normalize-escalate-source.md",
}

ASSISTANT_STAGE_SUMMARIES = {
    "extract": "读取 extract input，提取主实体/成员/别名/图片判定，并把结果写入 extract result。",
    "review": "读取 review input，对 extract 结果做二次复核，并把结果写入 review result。",
    "authority": "读取 authority input，对主实体候选做权威反查，并把结果写入 authority result。",
    "escalate": "读取 escalate input，对疑难来源补充裁决，并把结果写入 escalate result。",
}


class AssistantTaskPendingError(RuntimeError):
    def __init__(self, *, payload: dict[str, Any]):
        super().__init__(str(payload.get("message") or "waiting for programming assistant"))
        self.payload = payload


def _assistant_doc_path(stage: str) -> str:
    return str(REPO_ROOT / ".cursor" / "commands" / ASSISTANT_STAGE_DOC_FILENAMES[stage])


def _assistant_self_check_commands(stage: str, result_path: Path) -> list[str]:
    commands = [
        f'python3 quwoquan_data/tools/cli.py data normalize-validate-output --stage {stage} --result "{result_path}"'
    ]
    if stage == "extract":
        commands.append(
            f'python3 quwoquan_data/tools/cli.py data normalize-build-review-input --extract-result "{result_path}"'
        )
    elif stage == "review":
        commands.append(
            f'python3 quwoquan_data/tools/cli.py data normalize-build-authority-input --review-result "{result_path}"'
        )
    elif stage == "authority":
        commands.append(
            f'python3 quwoquan_data/tools/cli.py data normalize-build-escalation-input --authority-result "{result_path}"'
        )
    return commands


def _assistant_task_item(stage: str, input_payload: dict[str, Any], input_path: Path) -> dict[str, Any]:
    source_ref = str(input_payload.get("sourceRef", "")).strip()
    batch_label = str(input_payload.get("batchLabel", "")).strip()
    result_path = stage_result_path(batch_label, stage, source_ref)
    return {
        "sourceRef": source_ref,
        "sourceUrl": str(input_payload.get("sourceUrl", "")).strip(),
        "sourceTitle": str(input_payload.get("sourceTitle", "")).strip(),
        "inputPath": str(input_path),
        "expectedResultPath": str(result_path),
        "assistantCommand": ASSISTANT_STAGE_COMMANDS[stage],
        "assistantCommandDoc": _assistant_doc_path(stage),
        "inputSchemaPath": str(input_schema_path(stage)),
        "outputSchemaPath": str(output_schema_path(stage)),
        "processingSummary": ASSISTANT_STAGE_SUMMARIES[stage],
        "selfCheckCommands": _assistant_self_check_commands(stage, result_path),
    }


def _write_assistant_task_manifest(
    *,
    batch_label: str,
    stage: str,
    spec_path: str,
    topics: list[str],
    tasks: list[dict[str, Any]],
) -> Path:
    ensure_normalization_layout(batch_label)
    manifest = assistant_stage_task_manifest_path(batch_label, stage)
    write_json(
        manifest,
        {
            "schemaVersion": "quwoquan_data.normalization.assistant_task_manifest",
            "batchLabel": batch_label,
            "stage": stage,
            "status": "waiting_for_programming_assistant",
            "assistantCommand": ASSISTANT_STAGE_COMMANDS[stage],
            "assistantCommandDoc": _assistant_doc_path(stage),
            "specPath": spec_path,
            "topics": topics,
            "taskCount": len(tasks),
            "tasks": tasks,
        },
    )
    write_json(
        assistant_batch_status_path(batch_label),
        {
            "schemaVersion": "quwoquan_data.normalization.assistant_batch_status",
            "batchLabel": batch_label,
            "stage": stage,
            "status": "waiting_for_programming_assistant",
            "assistantCommand": ASSISTANT_STAGE_COMMANDS[stage],
            "assistantCommandDoc": _assistant_doc_path(stage),
            "taskManifestPath": str(manifest),
            "taskCount": len(tasks),
            "topics": topics,
        },
    )
    _upsert_normalization_manifest(
        batch_label,
        status="waiting_for_programming_assistant",
        artifacts={
            f"assistantTasks.{stage}": str(manifest),
            "assistantTasks.batchStatus": str(assistant_batch_status_path(batch_label)),
        },
    )
    return manifest


def _validate_stage_results_or_raise(
    *,
    batch_label: str,
    stage: str,
    paths: list[Path],
    spec_path: str,
    topics: list[str],
) -> list[dict[str, Any]]:
    validated: list[dict[str, Any]] = []
    missing_tasks: list[dict[str, Any]] = []
    for path in paths:
        input_payload = validate_input_file(stage, path)
        source_ref = str(input_payload.get("sourceRef", "")).strip()
        result_path = stage_result_path(batch_label, stage, source_ref)
        if not result_path.exists():
            missing_tasks.append(_assistant_task_item(stage, input_payload, path))
            continue
        output_payload = validate_output_file(stage, result_path)
        validated.append(
            {
                "sourceRef": source_ref,
                "sourceUrl": str(output_payload.get("sourceUrl", "")).strip(),
                "sourceTitle": str(output_payload.get("sourceTitle", "")).strip(),
                "inputPath": str(path),
                "resultPath": str(result_path),
            }
        )
    if missing_tasks:
        manifest = _write_assistant_task_manifest(
            batch_label=batch_label,
            stage=stage,
            spec_path=spec_path,
            topics=topics,
            tasks=missing_tasks,
        )
        raise AssistantTaskPendingError(
            payload={
                "status": "waiting_for_programming_assistant",
                "trace": {"batchLabel": batch_label, "stage": stage},
                "inputs": {"spec": spec_path, "topics": topics, "inputPaths": [str(path) for path in paths]},
                "outputs": {
                    "assistantTaskManifestPath": str(manifest),
                    "expectedResultPaths": [task["expectedResultPath"] for task in missing_tasks],
                },
                "metrics": {
                    "inputCount": len(paths),
                    "validatedResultCount": len(validated),
                    "missingResultCount": len(missing_tasks),
                },
                "warnings": [],
                "nextActions": [ASSISTANT_STAGE_COMMANDS[stage]],
                "message": f"stage={stage} 缺少 {len(missing_tasks)} 个结果文件，等待编程助手执行",
            }
        )
    return validated


def _build_followup_stage_inputs(batch_label: str, stage: str) -> dict[str, int]:
    created = 0
    if stage == "extract":
        for result_path in _resolve_stage_paths(batch_label=batch_label, stage="extract", kind="result"):
            build_review_input(extract_result_path=str(result_path))
            created += 1
    elif stage == "review":
        for result_path in _resolve_stage_paths(batch_label=batch_label, stage="review", kind="result"):
            build_authority_backcheck_input(review_result_path=str(result_path))
            created += 1
    elif stage == "authority":
        for result_path in _resolve_stage_paths(batch_label=batch_label, stage="authority", kind="result"):
            payload = read_json(result_path)
            if not isinstance(payload, dict):
                continue
            if str(payload.get("authorityBackcheckStatus", "")).strip() == "verified":
                continue
            build_escalation_input(authority_result_path=str(result_path))
            created += 1
    return {"created": created}


def _stage_handler(stage: str, *, input_arg: str, batch_label: str, source_ref: str) -> int:
    paths = _resolve_stage_paths(batch_label=batch_label, stage=stage, kind="input", input_arg=input_arg, source_ref=source_ref)
    if not paths:
        print(f"[data normalize-run-{stage}] FAIL: 没有可执行的 {stage} input", file=sys.stderr)
        return 1
    try:
        outputs = _validate_stage_results_or_raise(
            batch_label=batch_label,
            stage=stage,
            paths=paths,
            spec_path="",
            topics=[],
        )
        followup = _build_followup_stage_inputs(batch_label, stage)
    except AssistantTaskPendingError as exc:
        return _waiting_payload(f"data-normalize-run-{stage}", **exc.payload)
    except (NormalizationValidationError, FileNotFoundError, ValueError) as exc:
        print(f"[data normalize-run-{stage}] FAIL: {exc}", file=sys.stderr)
        return 1
    return _stage_payload(
        f"data-normalize-run-{stage}",
        status="ready",
        trace={"batchLabel": batch_label, "stage": stage},
        inputs={"inputPaths": [str(path) for path in paths]},
        outputs={"resultPaths": [str(item["resultPath"]) for item in outputs]},
        metrics={"inputCount": len(paths), "resultCount": len(outputs), **followup},
        warnings=[],
        nextActions=[],
    )


def handle_data_normalize_run_extract(args) -> int:
    batch_label = str(getattr(args, "batch_label", "") or "").strip()
    return _stage_handler(
        "extract",
        input_arg=str(getattr(args, "input", "") or "").strip(),
        batch_label=batch_label,
        source_ref=str(getattr(args, "source_ref", "") or "").strip(),
    )


def handle_data_normalize_run_review(args) -> int:
    batch_label = str(getattr(args, "batch_label", "") or "").strip()
    return _stage_handler(
        "review",
        input_arg=str(getattr(args, "input", "") or "").strip(),
        batch_label=batch_label,
        source_ref=str(getattr(args, "source_ref", "") or "").strip(),
    )


def handle_data_normalize_run_authority(args) -> int:
    batch_label = str(getattr(args, "batch_label", "") or "").strip()
    return _stage_handler(
        "authority",
        input_arg=str(getattr(args, "input", "") or "").strip(),
        batch_label=batch_label,
        source_ref=str(getattr(args, "source_ref", "") or "").strip(),
    )


def handle_data_normalize_run_escalate(args) -> int:
    batch_label = str(getattr(args, "batch_label", "") or "").strip()
    return _stage_handler(
        "escalate",
        input_arg=str(getattr(args, "input", "") or "").strip(),
        batch_label=batch_label,
        source_ref=str(getattr(args, "source_ref", "") or "").strip(),
    )


def handle_data_normalize_run_batch(args) -> int:
    spec_arg = str(getattr(args, "spec", "") or "").strip()
    spec, spec_path = _load_spec(spec_arg)
    spec_id = str(spec.get("spec_id", "")).strip()
    batch_label = str(getattr(args, "batch_label", "") or "").strip() or spec_id
    topics_filter = {item.strip() for item in str(getattr(args, "topics", "") or "").split(",") if item.strip()}
    output_name = str(getattr(args, "output_name", "") or f"{spec_id}_normalized_entities.ndjson").strip()
    catalog_arg = str(getattr(args, "catalog", "") or "").strip() or _catalog_from_args(spec_arg, "")
    if not catalog_arg:
        print("[data normalize-run-batch] FAIL: 需要 --catalog 或 spec.article_topic_catalog_ref", file=sys.stderr)
        return 1
    try:
        prepare = _prepare_topic_inputs(
            spec=spec,
            spec_path=spec_path,
            batch_label=batch_label,
            topics_filter=topics_filter,
        )
        extract_paths = [Path(path) for path in prepare["extractInputPaths"]]
        if not extract_paths:
            raise ValueError("没有生成 extract input")
        extract_outputs = _validate_stage_results_or_raise(
            batch_label=batch_label,
            stage="extract",
            paths=extract_paths,
            spec_path=str(spec_path),
            topics=sorted(topics_filter),
        )
        review_inputs = _build_followup_stage_inputs(batch_label, "extract")
        review_paths = _resolve_stage_paths(batch_label=batch_label, stage="review", kind="input")
        review_outputs = _validate_stage_results_or_raise(
            batch_label=batch_label,
            stage="review",
            paths=review_paths,
            spec_path=str(spec_path),
            topics=sorted(topics_filter),
        )
        authority_inputs = _build_followup_stage_inputs(batch_label, "review")
        authority_paths = _resolve_stage_paths(batch_label=batch_label, stage="authority", kind="input")
        authority_outputs = _validate_stage_results_or_raise(
            batch_label=batch_label,
            stage="authority",
            paths=authority_paths,
            spec_path=str(spec_path),
            topics=sorted(topics_filter),
        )
        escalation_inputs = _build_followup_stage_inputs(batch_label, "authority")
        escalate_paths = _resolve_stage_paths(batch_label=batch_label, stage="escalate", kind="input")
        escalate_outputs: list[dict[str, Any]] = []
        if escalate_paths:
            escalate_outputs = _validate_stage_results_or_raise(
                batch_label=batch_label,
                stage="escalate",
                paths=escalate_paths,
                spec_path=str(spec_path),
                topics=sorted(topics_filter),
            )
        compile_summary = compile_batch(batch_label)
        materialize_result = materialize_entity_catalog(
            batch_label=batch_label,
            catalog_rows=_read_catalog_rows(catalog_arg),
            output_name=output_name,
        )
        _upsert_normalization_manifest(batch_label, status="ready")
    except AssistantTaskPendingError as exc:
        return _waiting_payload("data-normalize-run-batch", **exc.payload)
    except (NormalizationValidationError, FileNotFoundError, ValueError) as exc:
        print(f"[data normalize-run-batch] FAIL: {exc}", file=sys.stderr)
        return 1
    return _stage_payload(
        "data-normalize-run-batch",
        status="ready",
        trace={"specId": spec_id, "batchLabel": batch_label},
        inputs={"spec": str(spec_path), "topics": sorted(topics_filter), "catalog": catalog_arg},
        outputs={
            "extractResultPaths": [str(item["resultPath"]) for item in extract_outputs],
            "reviewResultPaths": [str(item["resultPath"]) for item in review_outputs],
            "authorityResultPaths": [str(item["resultPath"]) for item in authority_outputs],
            "escalateResultPaths": [str(item["resultPath"]) for item in escalate_outputs],
            "entityResolutionPath": str(entity_resolution_path(batch_label)),
            "materializedEntityCatalogPath": materialize_result["path"],
        },
        metrics={
            "topicCount": len(prepare["topicRows"]),
            "hydratedSourceCount": prepare["hydratedSourceCount"],
            "extractInputCount": len(extract_paths),
            "reviewInputCount": len(review_paths),
            "authorityInputCount": len(authority_paths),
            "escalateInputCount": len(escalate_paths),
            "extractResultCount": len(extract_outputs),
            "reviewResultCount": len(review_outputs),
            "authorityResultCount": len(authority_outputs),
            "escalateResultCount": len(escalate_outputs),
            "reviewInputCreated": review_inputs["created"],
            "authorityInputCreated": authority_inputs["created"],
            "escalationInputCreated": escalation_inputs["created"],
            **compile_summary,
            "materializedEntityCount": materialize_result["count"],
        },
        warnings=prepare["warnings"],
        nextActions=[],
    )


def handle_data_normalize_build_extract_input(args) -> int:
    batch_label = str(getattr(args, "batch_label", "") or "").strip()
    try:
        payload = build_extract_input(
            batch_label=batch_label,
            source_markdown_path=str(getattr(args, "source_md", "") or "").strip(),
            catalog_topic_id=str(getattr(args, "catalog_topic", "") or "").strip(),
            catalog_name=str(getattr(args, "catalog_name", "") or "").strip(),
        )
        validate_input_payload("extract", payload)
    except (NormalizationValidationError, FileNotFoundError, ValueError) as exc:
        print(f"[data normalize-build-extract-input] FAIL: {exc}", file=sys.stderr)
        return 1
    return _stage_payload(
        "data-normalize-build-extract-input",
        status="ready",
        trace={
            "sourceUrl": payload["sourceUrl"],
            "pageTitle": payload["sourceTitle"],
            "sourceMarkdownPath": payload["sourceMarkdownPath"],
            "catalogTopicId": payload.get("catalogTopicId", ""),
        },
        inputs={
            "sourceMarkdownPath": payload["sourceMarkdownPath"],
            "catalogTopicId": payload.get("catalogTopicId", ""),
        },
        outputs={"inputPath": str(stage_input_path(payload["batchLabel"], "extract", payload["sourceRef"]))},
        metrics={"assetCount": len(payload.get("imageAssetRefs") or [])},
        warnings=[],
        nextActions=["cursor command /data-normalize-extract-source", "data normalize-validate-output --stage extract --result <file>"],
    )


def handle_data_normalize_build_review_input(args) -> int:
    try:
        payload = build_review_input(extract_result_path=str(getattr(args, "extract_result", "") or "").strip())
        validate_input_payload("review", payload)
    except (NormalizationValidationError, FileNotFoundError, ValueError) as exc:
        print(f"[data normalize-build-review-input] FAIL: {exc}", file=sys.stderr)
        return 1
    return _stage_payload(
        "data-normalize-build-review-input",
        status="ready",
        trace={"sourceUrl": payload["sourceUrl"], "pageTitle": payload["sourceTitle"], "sourceMarkdownPath": payload["sourceMarkdownPath"]},
        inputs={"extractResultPath": payload["extractResultPath"]},
        outputs={"inputPath": str(stage_input_path(payload["batchLabel"], "review", payload["sourceRef"]))},
        metrics={},
        warnings=[],
        nextActions=["cursor command /data-normalize-review-source", "data normalize-validate-output --stage review --result <file>"],
    )


def handle_data_normalize_build_authority_input(args) -> int:
    try:
        payload = build_authority_backcheck_input(review_result_path=str(getattr(args, "review_result", "") or "").strip())
        validate_input_payload("authority", payload)
    except (NormalizationValidationError, FileNotFoundError, ValueError) as exc:
        print(f"[data normalize-build-authority-input] FAIL: {exc}", file=sys.stderr)
        return 1
    return _stage_payload(
        "data-normalize-build-authority-input",
        status="ready",
        trace={"sourceUrl": payload["sourceUrl"], "pageTitle": payload["sourceTitle"]},
        inputs={"reviewResultPath": payload["reviewResultPath"]},
        outputs={"inputPath": str(stage_input_path(payload["batchLabel"], "authority", payload["sourceRef"]))},
        metrics={},
        warnings=[],
        nextActions=["cursor command /data-normalize-authority-source", "data normalize-validate-output --stage authority --result <file>"],
    )


def handle_data_normalize_build_escalation_input(args) -> int:
    try:
        payload = build_escalation_input(authority_result_path=str(getattr(args, "authority_result", "") or "").strip())
        validate_input_payload("escalate", payload)
    except (NormalizationValidationError, FileNotFoundError, ValueError) as exc:
        print(f"[data normalize-build-escalation-input] FAIL: {exc}", file=sys.stderr)
        return 1
    return _stage_payload(
        "data-normalize-build-escalation-input",
        status="ready",
        trace={"sourceUrl": payload["sourceUrl"], "pageTitle": payload["sourceTitle"]},
        inputs={"authorityResultPath": payload["authorityResultPath"]},
        outputs={"inputPath": str(stage_input_path(payload["batchLabel"], "escalate", payload["sourceRef"]))},
        metrics={},
        warnings=[],
        nextActions=["cursor command /data-normalize-escalate-source", "data normalize-validate-output --stage escalate --result <file>"],
    )


def handle_data_normalize_validate_input(args) -> int:
    stage = str(getattr(args, "stage", "") or "").strip()
    path = Path(str(getattr(args, "input", "") or "").strip())
    if not path.is_absolute():
        path = (REPO_ROOT / path).resolve()
    try:
        payload = validate_input_file(stage, path)
    except (NormalizationValidationError, FileNotFoundError, KeyError, ValueError) as exc:
        print(f"[data normalize-validate-input] FAIL: {exc}", file=sys.stderr)
        return 1
    return _stage_payload(
        "data-normalize-validate-input",
        status="ready",
        trace={"inputPath": str(path)},
        inputs={"stage": stage},
        outputs={"validatedInputPath": str(path)},
        metrics={"fieldCount": len(payload)},
        warnings=[],
        nextActions=[],
    )


def handle_data_normalize_validate_output(args) -> int:
    stage = str(getattr(args, "stage", "") or "").strip()
    path = Path(str(getattr(args, "result", "") or "").strip())
    if not path.is_absolute():
        path = (REPO_ROOT / path).resolve()
    try:
        payload = validate_output_file(stage, path)
    except (NormalizationValidationError, FileNotFoundError, KeyError, ValueError) as exc:
        print(f"[data normalize-validate-output] FAIL: {exc}", file=sys.stderr)
        return 1
    return _stage_payload(
        "data-normalize-validate-output",
        status="ready",
        trace={
            "resultPath": str(path),
            "sourceUrl": str(payload.get("sourceUrl", "")).strip(),
            "pageTitle": str(payload.get("sourceTitle", "")).strip(),
        },
        inputs={"stage": stage},
        outputs={"validatedResultPath": str(path)},
        metrics={"fieldCount": len(payload)},
        warnings=[],
        nextActions=[],
    )


def handle_data_normalize_compile_entities(args) -> int:
    batch_label = str(getattr(args, "batch_label", "") or "").strip()
    if not batch_label:
        print("[data normalize-compile-entities] FAIL: 需要 --batch-label", file=sys.stderr)
        return 1
    try:
        summary = compile_batch(batch_label)
    except (FileNotFoundError, ValueError) as exc:
        print(f"[data normalize-compile-entities] FAIL: {exc}", file=sys.stderr)
        return 1
    _upsert_normalization_manifest(
        batch_label,
        status="ready",
        artifacts={
            "compiled.sourceResolution": str(source_resolution_path(batch_label)),
            "compiled.entityResolution": str(entity_resolution_path(batch_label)),
            "compiled.pendingResolution": str(pending_resolution_path(batch_label)),
            "compiled.imageResolution": str(image_resolution_path(batch_label)),
        },
    )
    return _stage_payload(
        "data-normalize-compile-entities",
        status="ready",
        trace={"batchLabel": batch_label},
        inputs={"batchLabel": batch_label},
        outputs={
            "entityResolutionPath": str(entity_resolution_path(batch_label)),
            "imageResolutionPath": str(image_resolution_path(batch_label)),
            "pendingResolutionPath": str(pending_resolution_path(batch_label)),
        },
        metrics=summary,
        warnings=[],
        nextActions=["data entity-catalog-materialize --batch-label <batch> --catalog <catalog.ndjson>"],
    )


def handle_data_entity_catalog_materialize(args) -> int:
    batch_label = str(getattr(args, "batch_label", "") or "").strip()
    catalog_arg = str(getattr(args, "catalog", "") or "").strip()
    if not batch_label or not catalog_arg:
        print("[data entity-catalog-materialize] FAIL: 需要 --batch-label 与 --catalog", file=sys.stderr)
        return 1
    output_name = str(getattr(args, "output_name", "") or "entities.ndjson").strip() or "entities.ndjson"
    try:
        result = materialize_entity_catalog(
            batch_label=batch_label,
            catalog_rows=_read_catalog_rows(catalog_arg),
            output_name=output_name,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"[data entity-catalog-materialize] FAIL: {exc}", file=sys.stderr)
        return 1
    return _stage_payload(
        "data-entity-catalog-materialize",
        status="ready",
        trace={"batchLabel": batch_label, "catalogPath": catalog_arg},
        inputs={"batchLabel": batch_label, "catalog": catalog_arg, "outputName": output_name},
        outputs={"entityCatalogPath": result["path"]},
        metrics={"entityCount": result["count"]},
        warnings=[],
        nextActions=[],
    )


def handle_data_trace_source(args) -> int:
    batch_label = str(getattr(args, "batch_label", "") or "").strip()
    if not batch_label:
        print("[data trace-source] FAIL: 需要 --batch-label", file=sys.stderr)
        return 1
    try:
        source_ref = _resolve_source_ref_for_batch(
            batch_label=batch_label,
            source_ref=str(getattr(args, "source_ref", "") or "").strip(),
            source_md=str(getattr(args, "source_md", "") or "").strip(),
            source_url=str(getattr(args, "source_url", "") or "").strip(),
        )
        payload = build_trace_report(batch_label=batch_label, source_ref=source_ref)
    except (FileNotFoundError, ValueError) as exc:
        print(f"[data trace-source] FAIL: {exc}", file=sys.stderr)
        return 1
    return _stage_payload(
        "data-trace-source",
        status="ready",
        trace={"sourceUrl": payload.get("sourceUrl", ""), "pageTitle": payload.get("sourceTitle", "")},
        inputs={"batchLabel": batch_label, "sourceRef": source_ref},
        outputs={"traceReportPath": str(trace_report_path(batch_label, source_ref))},
        metrics={"compiledEntityCount": len(payload.get("compiledEntityRefs") or [])},
        warnings=[],
        nextActions=[],
    )

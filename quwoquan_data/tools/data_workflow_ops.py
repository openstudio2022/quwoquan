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
    build_review_input,
)
from normalization.compile_entity_resolution import compile_batch, materialize_entity_catalog
from normalization.fetch_source_bundle import fetch_source_bundle
from normalization.io_contracts import (
    NORMALIZATION_MANIFEST_SCHEMA_VERSION,
    ensure_normalization_layout,
    entity_resolution_path,
    image_resolution_path,
    manifest_path,
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


def _call_quiet(handler, args: argparse.Namespace) -> int:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        result = int(handler(args))
    if result != 0 and buffer.getvalue().strip():
        print(buffer.getvalue(), file=sys.stderr, end="" if buffer.getvalue().endswith("\n") else "\n")
    return result


def _run_verify_script(script_name: str) -> int:
    script_path = REPO_ROOT / "scripts" / script_name
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


def handle_data_build_entities_tags(args) -> int:
    ensure_runtime_layout()
    catalog_config = str(getattr(args, "catalog_config", "") or "").strip()
    catalog_output = str(getattr(args, "catalog_output", "") or "").strip()
    report_out = str(getattr(args, "report_out", "") or "").strip()
    catalog_inputs = [str(item).strip() for item in (getattr(args, "catalog_inputs", []) or []) if str(item).strip()]

    if catalog_config:
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
        catalog=catalog,
        catalogConfig=catalog_config,
        reportOut=report_out,
        semanticCandidates=str(semantic_candidates) if semantic_candidates.exists() else "",
        semanticPending=str(semantic_pending) if semantic_pending.exists() else "",
        skipTagCatalog=bool(getattr(args, "skip_tag_catalog", False)),
        skipEntityCatalog=bool(getattr(args, "skip_entity_catalog", False)),
    )


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


def handle_data_process_content(args) -> int:
    ensure_runtime_layout()
    spec_arg = str(getattr(args, "spec", "") or "").strip()
    spec, spec_path = _load_spec(spec_arg)
    topics = str(getattr(args, "topics", "") or "")
    targets = str(getattr(args, "targets", "") or "")

    if _call_quiet(workflow_ops.handle_content_review, _ns(spec=str(spec_path), spec_id="")) != 0:
        return 1
    if _call_quiet(
        workflow_ops.handle_compose_post,
        _ns(spec=str(spec_path), topic="", topics=topics, targets=targets),
    ) != 0:
        return 1
    if _call_quiet(workflow_ops.handle_review_generated, _ns(spec=str(spec_path), topic="", topics=topics)) != 0:
        return 1
    return _stage_payload(
        "data-process-content",
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

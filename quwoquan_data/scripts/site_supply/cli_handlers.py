"""CLI handlers for the site-supply command surface."""
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import functools
import hashlib
import json
import math
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any, Mapping

import yaml

from _common.io import read_json, write_json
from _common.paths import DATA_ROOT, RUNTIME_ROOT, now_iso
from download.fetch import fetch_image_payload, fetch_source_payload

from site_supply.core import *  # noqa: F403
from site_supply.packets import *  # noqa: F403
from site_supply.targets import *  # noqa: F403
from site_supply.content_plan import *  # noqa: F403
from site_supply.reports import *  # noqa: F403
from site_supply.trial import *  # noqa: F403
from site_supply.crawler import *  # noqa: F403
from site_supply import bridge

def handle_plan(args: argparse.Namespace) -> None:
    packet = build_site_frontier_packet(
        vertical=args.vertical,
        site_id=args.site_id,
        batch_id=args.batch,
        daily_target=args.daily_target,
        queue_backend=args.queue_backend,
        lanes=_split_csv(args.lanes) or None,
        time_window_days=args.time_window_days,
        start_date=args.start_date,
        end_date=args.end_date,
        entry_urls=_split_csv(args.entry_urls) or None,
        allowed_paths=_split_csv(args.allowed_paths) or None,
        admission_mode=args.admission_mode,
    )
    if args.write:
        write_site_frontier_packet(packet)
    _print(packet)
    if not packet["gate"]["passed"]:
        raise SystemExit(1)

def handle_candidate(args: argparse.Namespace) -> None:
    packet = build_site_candidate_packet(
        vertical=args.vertical,
        site_id=args.site_id,
        batch_id=args.batch,
        url=args.url,
        lane=args.lane,
        title=args.title,
        text=args.text or "",
        published_at=args.published_at,
        author=args.author or "",
        assets=_parse_assets(args.assets, source_url=args.url),
        entity_mentions=_split_csv(args.entity_mentions),
        tag_mentions=_split_csv(args.tag_mentions),
    )
    if args.write:
        write_site_candidate_packet(packet)
    _print(packet)
    if not packet["gate"]["passed"]:
        raise SystemExit(1)

def handle_score(args: argparse.Namespace) -> None:
    root = site_supply_root(args.vertical, args.site_id, args.batch)
    ref = args.candidate_ref or _stable_ref("candidate", args.url)
    candidate = read_json(_candidate_path(root, ref))
    packet = build_site_score_packet(candidate, duplicate=args.duplicate)
    if args.write:
        write_site_score_packet(packet)
    _print(packet)
    if not packet["gate"]["passed"]:
        raise SystemExit(1)

def handle_map(args: argparse.Namespace) -> None:
    root = site_supply_root(args.vertical, args.site_id, args.batch)
    ref = args.candidate_ref or _stable_ref("candidate", args.url)
    candidate = read_json(_candidate_path(root, ref))
    score = read_json(_score_path(root, ref))
    packet = build_site_map_packet(candidate, score)
    if args.write:
        write_site_map_packet(packet)
    _print(packet)
    if not packet["gate"]["passed"]:
        raise SystemExit(1)

def handle_rollup(args: argparse.Namespace) -> None:
    report = build_site_rollup_report(
        vertical=args.vertical,
        site_id=args.site_id,
        batch_id=args.batch,
        objects_per_hour=args.objects_per_hour,
        first_pass_rate=args.first_pass_rate,
        token_ledger_count=args.token_ledger_count,
        release_verified=args.release_verified,
        import_verified=args.import_verified,
        search_visible=args.search_visible,
        recommendation_feedback_ready=args.recommendation_feedback_ready,
        http_429_count=args.http_429_count,
        http_403_count=args.http_403_count,
        probe_page_count=args.probe_page_count,
        empty_extract_count=args.empty_extract_count,
        duplicate_count=args.duplicate_count,
        dead_letter_count=args.dead_letter_count,
    )
    if args.write:
        write_site_rollup_report(report)
    _print(report)
    if not report["passed"]:
        raise SystemExit(1)

def handle_quality_report(args: argparse.Namespace) -> None:
    report = build_site_quality_distribution_report(
        vertical=args.vertical,
        site_id=args.site_id,
        batch_id=args.batch,
    )
    if args.write:
        write_site_quality_distribution_report(report)
    _print(report)
    if not (report.get("gate") or {}).get("passed"):
        raise SystemExit(1)

def handle_rerollup(args: argparse.Namespace) -> None:
    report = _recomputed_site_rollup_report(
        vertical=args.vertical,
        site_id=args.site_id,
        batch_id=args.batch,
        objects_per_hour=args.objects_per_hour,
    )
    if args.write:
        write_site_rollup_report(report)
    _print(report)
    if not report["passed"]:
        raise SystemExit(1)

def handle_downstream_evidence(args: argparse.Namespace) -> None:
    if args.write:
        repair_content_plan_source_site_provenance(
            vertical=args.vertical,
            site_id=args.site_id,
            batch_id=args.batch,
            task_id=args.task,
            target_batch=args.target_batch,
        )
    report = build_downstream_e2e_report(
        vertical=args.vertical,
        site_id=args.site_id,
        batch_id=args.batch,
        task_id=args.task,
        target_batch=args.target_batch,
        env=args.env,
        allow_dry_run_import=args.allow_dry_run_import,
    )
    if args.write:
        write_downstream_e2e_report(report)
    _print(report)
    if not (report.get("gate") or {}).get("passed"):
        raise SystemExit(1)

def handle_repair_fetch(args: argparse.Namespace) -> None:
    root = site_supply_root(args.vertical, args.site_id, args.batch)
    ref = args.candidate_ref or _stable_ref("candidate", args.url)
    previous = read_json(root / "fetches" / ref / "site_fetch_packet.json")
    frontier = _frontier_packet(args.vertical, args.site_id, args.batch)
    profile = frontier.get("profile") if isinstance(frontier.get("profile"), Mapping) else {}
    url = str(previous.get("canonicalUrl") or args.url or "").strip()
    if not url:
        raise SystemExit("repair-fetch requires --url or an existing fetch packet canonicalUrl")
    payload, error, attempts = _fetch_with_retry(
        url,
        source=profile,
        retry_budget=args.fetch_retry_budget,
        retry_delay_seconds=args.fetch_retry_delay,
    )
    extraction = previous.get("extraction") if isinstance(previous.get("extraction"), Mapping) else {}
    mentions = previous.get("semanticMentions") if isinstance(previous.get("semanticMentions"), Mapping) else {}
    fetch_packet = build_site_fetch_packet(
        vertical=args.vertical,
        site_id=args.site_id,
        batch_id=args.batch,
        url=url,
        lane=str(previous.get("lane") or args.lane),
        title=str(extraction.get("title") or previous.get("title") or ""),
        author=str(extraction.get("author") or ""),
        published_at=str(extraction.get("publishedAt") or "") or args.published_at,
        entity_mentions=[str(x) for x in (mentions.get("entities") or [])],
        tag_mentions=[str(x) for x in (mentions.get("tags") or [])],
        min_text_chars=args.min_text_chars,
        payload=payload,
        error=error,
        attempts=attempts,
    )
    write_site_fetch_packet(
        fetch_packet,
        html_bytes=(payload or {}).get("htmlBytes") if isinstance((payload or {}).get("htmlBytes"), bytes) else None,
    )
    if fetch_packet["gate"]["passed"]:
        candidate = build_site_candidate_from_fetch(fetch_packet)
        write_site_candidate_packet(candidate)
        if candidate["gate"]["passed"]:
            score = build_site_score_packet(candidate)
            write_site_score_packet(score)
            if score["gate"]["passed"]:
                mapped = build_site_map_packet(candidate, score)
                write_site_map_packet(mapped)
    report = _recomputed_site_rollup_report(
        vertical=args.vertical,
        site_id=args.site_id,
        batch_id=args.batch,
        objects_per_hour=args.objects_per_hour,
    )
    write_site_rollup_report(report)
    _print({"fetch": fetch_packet, "rollup": report})
    if not fetch_packet["gate"]["passed"] or not report["passed"]:
        raise SystemExit(1)

def handle_trial(args: argparse.Namespace) -> None:
    packet = build_site_frontier_packet(
        vertical=args.vertical,
        site_id=args.site_id,
        batch_id=args.batch,
        daily_target=args.daily_target,
        queue_backend=args.queue_backend,
        end_date=args.end_date,
        admission_mode=args.admission_mode,
    )
    write_site_frontier_packet(packet)
    if not packet["gate"]["passed"]:
        _print(packet)
        raise SystemExit(1)
    lane_counts = _trial_lane_counts(args)
    profile = packet.get("profile") or {}
    global_idx = 0
    for lane, count in lane_counts.items():
        for lane_idx in range(1, count + 1):
            global_idx += 1
            url = _trial_url(profile, batch_id=args.batch, lane=lane, index=global_idx)
            candidate = build_site_candidate_packet(
                vertical=args.vertical,
                site_id=args.site_id,
                batch_id=args.batch,
                url=url,
                lane=lane,
                title=f"{args.batch} {lane} 受控试跑候选 {lane_idx:06d}",
                text=_trial_text(global_idx) if lane == "article" else "",
                published_at=args.end_date,
                assets=_trial_assets(profile, url=url, lane=lane, index=global_idx),
                entity_mentions=[f"地点/景区/结构试跑景区{global_idx:06d}"],
                tag_mentions=["Topic/旅行/玩法/自然风光", f"Format/内容载体/{lane}"],
            )
            write_site_candidate_packet(candidate)
            if not candidate["gate"]["passed"]:
                _print(candidate)
                raise SystemExit(1)
            score = build_site_score_packet(candidate)
            write_site_score_packet(score)
            if not score["gate"]["passed"]:
                _print(score)
                raise SystemExit(1)
            mapped = build_site_map_packet(candidate, score)
            write_site_map_packet(mapped)
            if not mapped["gate"]["passed"]:
                _print(mapped)
                raise SystemExit(1)
    rollup = build_site_rollup_report(
        vertical=args.vertical,
        site_id=args.site_id,
        batch_id=args.batch,
        objects_per_hour=args.objects_per_hour,
        first_pass_rate=args.first_pass_rate,
        token_ledger_count=args.token_ledger_count if args.token_ledger_count is not None else global_idx,
        release_verified=args.release_verified,
        import_verified=args.import_verified,
        search_visible=args.search_visible,
        recommendation_feedback_ready=args.recommendation_feedback_ready,
    )
    write_site_rollup_report(rollup)
    _print(rollup)
    if not rollup["passed"]:
        raise SystemExit(1)

def handle_crawl(args: argparse.Namespace) -> None:
    started = time.monotonic()
    target_count = int(args.target_count)
    overfetch_ratio = max(1.0, float(getattr(args, "frontier_overfetch_ratio", 1.0)))
    args.discovery_target_count = max(target_count, int(math.ceil(target_count * overfetch_ratio)))
    frontier = build_site_frontier_packet(
        vertical=args.vertical,
        site_id=args.site_id,
        batch_id=args.batch,
        daily_target=args.daily_target,
        queue_backend=args.queue_backend,
        lanes=[args.lane],
        end_date=args.end_date,
        admission_mode=ADMISSION_BATCH_CRAWL,
    )
    write_site_frontier_packet(frontier)
    if not frontier["gate"]["passed"]:
        _print(frontier)
        raise SystemExit(1)

    discovered = bridge.call(
        "_crawl_input_candidates",
        _crawl_input_candidates,
        args,
        frontier,
    )
    if not discovered:
        raise SystemExit("no real crawl input URLs discovered; repair at site_frontier discovery")
    root = site_supply_root(args.vertical, args.site_id, args.batch)
    frontier_candidates_path = _write_frontier_candidates(root, discovered)
    frontier["frontier"] = {
        **dict(frontier.get("frontier") or {}),
        "targetCount": target_count,
        "discoveryTargetCount": int(args.discovery_target_count),
        "frontierOverfetchRatio": overfetch_ratio,
        "discoveredCount": len(discovered),
        "maxDiscoveryRequests": int(args.max_discovery_requests),
        "queryStrategy": str(getattr(args, "query_strategy", QUERY_STRATEGY_MANUAL) or QUERY_STRATEGY_MANUAL),
        "frontierCandidates": str(frontier_candidates_path),
    }
    if len(discovered) < target_count:
        frontier["gate"] = _gate_report(
            "site_frontier",
            [f"frontier discovery produced {len(discovered)} URLs < targetCount {target_count}"],
            [],
        )
        write_site_frontier_packet(frontier)
        _print(frontier)
        raise SystemExit(1)
    write_site_frontier_packet(frontier)
    if bool(getattr(args, "frontier_only", False)):
        _print(frontier)
        return

    profile = frontier.get("profile") if isinstance(frontier.get("profile"), Mapping) else {}
    throttle_seconds = _rate_limit_seconds(profile)
    if args.throttle_seconds is not None:
        throttle_seconds = max(throttle_seconds, float(args.throttle_seconds))

    http_429 = http_403 = probe_pages = empty_extract = dead_letters = 0
    success_count = 0
    attempted = 0
    last_fetch_at = 0.0
    for row in discovered:
        if success_count >= target_count:
            break
        url = str(row.get("url") or "").strip()
        if not url:
            continue
        candidate_ref = _fetch_candidate_ref(url)
        if _existing_crawl_handoff_ready(root, candidate_ref):
            success_count += 1
            continue
        if attempted and throttle_seconds > 0:
            elapsed_since_fetch = time.monotonic() - last_fetch_at
            if elapsed_since_fetch < throttle_seconds:
                time.sleep(throttle_seconds - elapsed_since_fetch)
        attempted += 1
        payload, error, attempts_for_url = _fetch_with_retry(
            url,
            source=profile,
            retry_budget=args.fetch_retry_budget,
            retry_delay_seconds=args.fetch_retry_delay,
        )
        last_fetch_at = time.monotonic()
        fetch_packet = build_site_fetch_packet(
            vertical=args.vertical,
            site_id=args.site_id,
            batch_id=args.batch,
            url=url,
            lane=str(row.get("lane") or args.lane),
            title=str(row.get("title") or ""),
            author=str(row.get("author") or ""),
            published_at=str(row.get("publishedAt") or "") or args.end_date,
            entity_mentions=[str(x) for x in (row.get("entityMentions") or [])],
            tag_mentions=[str(x) for x in (row.get("tagMentions") or [])],
            min_text_chars=args.min_text_chars,
            payload=payload,
            error=error,
            attempts=attempts_for_url,
        )
        write_site_fetch_packet(
            fetch_packet,
            html_bytes=(payload or {}).get("htmlBytes") if isinstance((payload or {}).get("htmlBytes"), bytes) else None,
        )
        c429, c403, cprobe, cempty = _classify_fetch_packet(fetch_packet)
        http_429 += c429
        http_403 += c403
        probe_pages += cprobe
        empty_extract += cempty
        if not fetch_packet["gate"]["passed"]:
            if error:
                dead_letters += 1
            if args.stop_on_first_failure:
                break
            continue

        candidate = build_site_candidate_from_fetch(fetch_packet)
        write_site_candidate_packet(candidate)
        if not candidate["gate"]["passed"]:
            continue
        score = build_site_score_packet(candidate)
        write_site_score_packet(score)
        if not score["gate"]["passed"]:
            continue
        mapped = build_site_map_packet(candidate, score)
        write_site_map_packet(mapped)
        if mapped["gate"]["passed"]:
            success_count += 1

    elapsed_hours = max((time.monotonic() - started) / 3600.0, 0.000001)
    objects_per_hour = success_count / elapsed_hours if args.objects_per_hour is None else args.objects_per_hour
    first_pass_rate = (success_count / attempted) if attempted else 0.0
    rollup = build_site_rollup_report(
        vertical=args.vertical,
        site_id=args.site_id,
        batch_id=args.batch,
        objects_per_hour=objects_per_hour,
        first_pass_rate=first_pass_rate,
        token_ledger_count=args.token_ledger_count if args.token_ledger_count is not None else success_count,
        release_verified=args.release_verified,
        import_verified=args.import_verified,
        search_visible=args.search_visible,
        recommendation_feedback_ready=args.recommendation_feedback_ready,
        http_429_count=http_429,
        http_403_count=http_403,
        probe_page_count=probe_pages,
        empty_extract_count=empty_extract,
        dead_letter_count=dead_letters,
    )
    write_site_rollup_report(rollup)
    _print(rollup)
    if not rollup["passed"]:
        raise SystemExit(1)

def register_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("site-supply", help="网站维度内容供给线 packet/gate/rollup")
    sub = p.add_subparsers(dest="site_supply_command", required=True)

    pp = sub.add_parser("plan", help="生成 site_frontier_packet 并校验站点准入")
    pp.add_argument("--vertical", default="travel")
    pp.add_argument("--site-id", required=True)
    pp.add_argument("--batch", required=True)
    pp.add_argument("--daily-target", type=int, default=DEFAULT_DAILY_TARGET)
    pp.add_argument("--queue-backend", choices=["local_file", "reliabletask"], default="reliabletask")
    pp.add_argument("--lanes", help="逗号分隔 lane 覆盖，默认读 registry")
    pp.add_argument("--entry-urls", help="逗号分隔入口 URL/Pattern，默认读 registry")
    pp.add_argument("--allowed-paths", help="逗号分隔允许 URL pattern/path，默认读 registry")
    pp.add_argument("--admission-mode", choices=ADMISSION_MODES, default=ADMISSION_BATCH_CRAWL)
    pp.add_argument("--time-window-days", type=int, default=DEFAULT_TIME_WINDOW_DAYS)
    pp.add_argument("--start-date")
    pp.add_argument("--end-date")
    pp.add_argument("--write", action="store_true")
    pp.set_defaults(handler=handle_plan)

    pc = sub.add_parser("candidate", help="写入/校验单个 site_candidate_packet")
    pc.add_argument("--vertical", default="travel")
    pc.add_argument("--site-id", required=True)
    pc.add_argument("--batch", required=True)
    pc.add_argument("--url", required=True)
    pc.add_argument("--lane", required=True, choices=["homepage", "article", "image", "video", "knowledgeCard"])
    pc.add_argument("--title", required=True)
    pc.add_argument("--text", default="")
    pc.add_argument("--published-at")
    pc.add_argument("--author", default="")
    pc.add_argument("--assets", help="逗号分隔 assetUrl|license|credit|termsUrl|usageScope|modelReleaseStatus")
    pc.add_argument("--entity-mentions", default="")
    pc.add_argument("--tag-mentions", default="")
    pc.add_argument("--write", action="store_true")
    pc.set_defaults(handler=handle_candidate)

    ps = sub.add_parser("score", help="根据 candidate 写 site_score_packet")
    ps.add_argument("--vertical", default="travel")
    ps.add_argument("--site-id", required=True)
    ps.add_argument("--batch", required=True)
    group = ps.add_mutually_exclusive_group(required=True)
    group.add_argument("--candidate-ref")
    group.add_argument("--url")
    ps.add_argument("--duplicate", action="store_true")
    ps.add_argument("--write", action="store_true")
    ps.set_defaults(handler=handle_score)

    pm = sub.add_parser("map", help="把合格候选映射为 content_plan handoff")
    pm.add_argument("--vertical", default="travel")
    pm.add_argument("--site-id", required=True)
    pm.add_argument("--batch", required=True)
    group_m = pm.add_mutually_exclusive_group(required=True)
    group_m.add_argument("--candidate-ref")
    group_m.add_argument("--url")
    pm.add_argument("--write", action="store_true")
    pm.set_defaults(handler=handle_map)

    pcp = sub.add_parser("content-plan", help="把 site_map 合格候选物化为标准 content_plan batch")
    pcp.add_argument("--vertical", default="travel")
    pcp.add_argument("--site-id", required=True)
    pcp.add_argument("--batch", required=True, help="site_supply batch")
    pcp.add_argument("--task", required=True, help="目标 runtime taskId")
    pcp.add_argument("--target-batch", required=True, help="目标 runtime batchId")
    pcp.add_argument("--limit", type=int, default=10)
    pcp.add_argument("--refs", default="", help="逗号分隔 candidateRef；默认取所有 site_map eligible")
    pcp.add_argument("--entity-type", default="地点/景区")
    pcp.add_argument("--intent", default="行前指南")
    pcp.add_argument("--audience", default="leisureTraveler")
    pcp.add_argument("--max-images-per-candidate", type=int, default=3)
    pcp.add_argument("--allow-partial", action="store_true")
    pcp.set_defaults(handler=handle_content_plan)

    pr = sub.add_parser("rollup", help="聚合站点漏斗与规模化准出证据")
    pr.add_argument("--vertical", default="travel")
    pr.add_argument("--site-id", required=True)
    pr.add_argument("--batch", required=True)
    pr.add_argument("--objects-per-hour", type=float, default=0.0)
    pr.add_argument("--first-pass-rate", type=float)
    pr.add_argument("--token-ledger-count", type=int, default=0)
    pr.add_argument("--release-verified", action="store_true")
    pr.add_argument("--import-verified", action="store_true")
    pr.add_argument("--search-visible", action="store_true")
    pr.add_argument("--recommendation-feedback-ready", action="store_true")
    pr.add_argument("--http-429-count", type=int, default=0)
    pr.add_argument("--http-403-count", type=int, default=0)
    pr.add_argument("--probe-page-count", type=int, default=0)
    pr.add_argument("--empty-extract-count", type=int, default=0)
    pr.add_argument("--duplicate-count", type=int, default=0)
    pr.add_argument("--dead-letter-count", type=int, default=0)
    pr.add_argument("--write", action="store_true")
    pr.set_defaults(handler=handle_rollup)

    pqr = sub.add_parser("quality-report", help="聚合站点候选质量分布与商用准入证据")
    pqr.add_argument("--vertical", default="travel")
    pqr.add_argument("--site-id", required=True)
    pqr.add_argument("--batch", required=True)
    pqr.add_argument("--write", action="store_true")
    pqr.set_defaults(handler=handle_quality_report)

    prr = sub.add_parser("rerollup", help="按现有对象证据重算站点漏斗与准出")
    prr.add_argument("--vertical", default="travel")
    prr.add_argument("--site-id", required=True)
    prr.add_argument("--batch", required=True)
    prr.add_argument("--objects-per-hour", type=float)
    prr.add_argument("--write", action="store_true")
    prr.set_defaults(handler=handle_rerollup)

    pde = sub.add_parser("downstream-evidence", help="汇总 content_plan→ship/import→search/reco 证据并回写站点准出")
    pde.add_argument("--vertical", default="travel")
    pde.add_argument("--site-id", required=True)
    pde.add_argument("--batch", required=True, help="source site_supply batch")
    pde.add_argument("--task", required=True)
    pde.add_argument("--target-batch", required=True)
    pde.add_argument("--env", default="gamma")
    pde.add_argument(
        "--allow-dry-run-import",
        action="store_true",
        help="仅本地受控 rehearsal 允许 dry-run importer 作为导入命令链证据",
    )
    pde.add_argument("--write", action="store_true")
    pde.set_defaults(handler=handle_downstream_evidence)

    prf = sub.add_parser("repair-fetch", help="重新抓取单个失败候选并回灌 extract→score→map")
    prf.add_argument("--vertical", default="travel")
    prf.add_argument("--site-id", required=True)
    prf.add_argument("--batch", required=True)
    group_rf = prf.add_mutually_exclusive_group(required=True)
    group_rf.add_argument("--candidate-ref")
    group_rf.add_argument("--url")
    prf.add_argument("--lane", choices=["article"], default="article")
    prf.add_argument("--published-at")
    prf.add_argument("--min-text-chars", type=int, default=DEFAULT_FETCH_MIN_TEXT_CHARS)
    prf.add_argument("--fetch-retry-budget", type=int, default=2)
    prf.add_argument("--fetch-retry-delay", type=float, default=1.0)
    prf.add_argument("--objects-per-hour", type=float)
    prf.set_defaults(handler=handle_repair_fetch)

    pt = sub.add_parser("trial", help="结构试跑：生成受控候选并执行 frontier→candidate→score→map→rollup")
    pt.add_argument("--vertical", default="travel")
    pt.add_argument("--site-id", required=True)
    pt.add_argument("--batch", required=True)
    pt.add_argument("--target-count", type=int)
    pt.add_argument("--article-count", type=int)
    pt.add_argument("--image-count", type=int)
    pt.add_argument("--video-count", type=int)
    pt.add_argument("--daily-target", type=int, default=10_000)
    pt.add_argument("--queue-backend", choices=["local_file", "reliabletask"], default="reliabletask")
    pt.add_argument("--admission-mode", choices=ADMISSION_MODES, default=ADMISSION_CONTROLLED_TRIAL)
    pt.add_argument("--end-date", default=dt.date.today().isoformat())
    pt.add_argument("--objects-per-hour", type=float, default=500.0)
    pt.add_argument("--first-pass-rate", type=float, default=0.82)
    pt.add_argument("--token-ledger-count", type=int)
    pt.add_argument("--release-verified", action="store_true")
    pt.add_argument("--import-verified", action="store_true")
    pt.add_argument("--search-visible", action="store_true")
    pt.add_argument("--recommendation-feedback-ready", action="store_true")
    pt.set_defaults(handler=handle_trial)

    pcrawl = sub.add_parser("crawl", help="真实抓取：frontier→fetch→candidate→score→map→rollup")
    pcrawl.add_argument("--vertical", default="travel")
    pcrawl.add_argument("--site-id", required=True)
    pcrawl.add_argument("--batch", required=True)
    pcrawl.add_argument("--target-count", type=int, required=True)
    pcrawl.add_argument("--lane", choices=["article"], default="article")
    pcrawl.add_argument("--queries", default="", help="逗号分隔站内发现 query；qunar_guide 复用去哪儿搜索发现")
    pcrawl.add_argument("--query-strategy", choices=QUERY_STRATEGIES, default=QUERY_STRATEGY_MANUAL)
    pcrawl.add_argument("--max-search-pages", type=int, default=3)
    pcrawl.add_argument("--max-discovery-requests", type=int, default=500)
    pcrawl.add_argument("--discovery-request-timeout", type=int, default=20)
    pcrawl.add_argument("--discovery-timeout-seconds", type=float, default=0.0)
    pcrawl.add_argument("--frontier-overfetch-ratio", type=float, default=1.05)
    pcrawl.add_argument("--seed-urls", default="", help="逗号分隔显式 URL，仍需通过 registry/frontier/fetch 门")
    pcrawl.add_argument("--seed-file", help="每行一个显式 URL，仍需通过 registry/frontier/fetch 门")
    pcrawl.add_argument("--entity-mentions", default="")
    pcrawl.add_argument("--tag-mentions", default="")
    pcrawl.add_argument("--daily-target", type=int, default=10_000)
    pcrawl.add_argument("--queue-backend", choices=["local_file", "reliabletask"], default="reliabletask")
    pcrawl.add_argument("--end-date", default=dt.date.today().isoformat())
    pcrawl.add_argument("--min-text-chars", type=int, default=DEFAULT_FETCH_MIN_TEXT_CHARS)
    pcrawl.add_argument("--objects-per-hour", type=float)
    pcrawl.add_argument("--token-ledger-count", type=int)
    pcrawl.add_argument("--fetch-retry-budget", type=int, default=2)
    pcrawl.add_argument("--fetch-retry-delay", type=float, default=1.0)
    pcrawl.add_argument("--throttle-seconds", type=float)
    pcrawl.add_argument("--frontier-only", action="store_true")
    pcrawl.add_argument("--stop-on-first-failure", action="store_true")
    pcrawl.add_argument("--release-verified", action="store_true")
    pcrawl.add_argument("--import-verified", action="store_true")
    pcrawl.add_argument("--search-visible", action="store_true")
    pcrawl.add_argument("--recommendation-feedback-ready", action="store_true")
    pcrawl.set_defaults(handler=handle_crawl)

__all__ = [name for name in globals() if not name.startswith("__")]

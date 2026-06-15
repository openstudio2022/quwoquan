"""Deterministic public-source research plan bootstrap.

This fills the source/research lane with auditable public sources before a
semantic Agent is needed. It is intentionally conservative: it writes only
empty lane plans unless --force is passed, and it leaves explicit gaps when a
source cannot be discovered from registered public endpoints.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import urllib.parse
from pathlib import Path
from typing import Any

from _common.io import read_json, write_json
from _common.paths import STAGE_DOWNLOAD
from _common.source_unit import resolve_entity_object_dir
from download.prepare import prepare_source_plan

_USER_AGENT = "quwoquan-data/1.0 (+https://github.com/quwoquan; contact: data-ops@quwoquan.example)"


def _curl_json(url: str, *, timeout: int = 25) -> dict[str, Any]:
    proc = subprocess.run(
        ["curl", "-sS", "-A", _USER_AGENT, "--max-time", str(timeout), url],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return {}
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _strip_html(value: str) -> str:
    text = re.sub(r"(?is)<[^>]+>", " ", str(value or ""))
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _wiki_api(host: str, params: dict[str, str | int]) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    return _curl_json(f"https://{host}/w/api.php?{query}")


def _wiki_title(host: str, entity_id: str) -> str:
    exact = _wiki_api(host, {"action": "query", "titles": entity_id, "format": "json"})
    pages = (exact.get("query") or {}).get("pages") or {}
    for page in pages.values():
        if isinstance(page, dict) and int(page.get("pageid") or -1) > 0:
            return str(page.get("title") or entity_id)
    search = _wiki_api(
        host,
        {
            "action": "query",
            "list": "search",
            "srsearch": entity_id,
            "srlimit": 1,
            "format": "json",
        },
    )
    rows = ((search.get("query") or {}).get("search") or [])
    if rows and isinstance(rows[0], dict):
        return str(rows[0].get("title") or "")
    return ""


def _wiki_url(host: str, title: str) -> str:
    if not title:
        return ""
    return f"https://{host}/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"


def _wikidata_item_for_zhwiki(title: str) -> str:
    data = _wiki_api("zh.wikipedia.org", {
        "action": "query",
        "titles": title,
        "prop": "pageprops",
        "format": "json",
    })
    pages = (data.get("query") or {}).get("pages") or {}
    for page in pages.values():
        if isinstance(page, dict):
            qid = str((page.get("pageprops") or {}).get("wikibase_item") or "")
            if qid:
                return qid
    return ""


def _official_website(qid: str) -> str:
    if not qid:
        return ""
    data = _curl_json(
        "https://www.wikidata.org/w/api.php?"
        + urllib.parse.urlencode(
            {
                "action": "wbgetentities",
                "ids": qid,
                "props": "claims",
                "format": "json",
            }
        )
    )
    entity = ((data.get("entities") or {}).get(qid) or {})
    for claim in (entity.get("claims") or {}).get("P856") or []:
        try:
            value = claim["mainsnak"]["datavalue"]["value"]
        except (KeyError, TypeError):
            continue
        if str(value).startswith(("http://", "https://")):
            return str(value)
    return ""


def _commons_images(entity_id: str, *, limit: int = 8) -> list[dict[str, Any]]:
    data = _wiki_api(
        "commons.wikimedia.org",
        {
            "action": "query",
            "generator": "search",
            "gsrnamespace": 6,
            "gsrsearch": entity_id,
            "gsrlimit": limit,
            "prop": "imageinfo",
            "iiprop": "url|size|extmetadata",
            "format": "json",
        },
    )
    pages = (data.get("query") or {}).get("pages") or {}
    images: list[dict[str, Any]] = []
    seen: set[str] = set()
    for page in pages.values():
        if not isinstance(page, dict):
            continue
        info = ((page.get("imageinfo") or [{}])[0] or {})
        url = str(info.get("url") or "")
        if not url or url in seen:
            continue
        if not re.search(r"\.(?:jpe?g|png|webp)(?:$|\?)", url, re.I):
            continue
        seen.add(url)
        meta = info.get("extmetadata") or {}
        license_name = _strip_html(((meta.get("LicenseShortName") or {}).get("value") or ""))
        license_url = _strip_html(((meta.get("LicenseUrl") or {}).get("value") or ""))
        if not license_name or not re.search(r"CC|Public domain|PD|自由|公有", license_name, re.I):
            continue
        if "igo" in license_name.lower() or not license_url:
            continue
        width = int(info.get("width") or 0)
        height = int(info.get("height") or 0)
        if width < 640 or height < 426 or max(width, height) < 800:
            continue
        credit = _strip_html(
            ((meta.get("Artist") or {}).get("value") or "")
            or ((meta.get("Credit") or {}).get("value") or "")
            or "Wikimedia Commons contributor"
        )
        description = _strip_html(
            ((meta.get("ImageDescription") or {}).get("value") or "")
            or str(page.get("title") or "")
        )
        source_url = str(info.get("descriptionurl") or info.get("descriptionshorturl") or url)
        images.append(
            {
                "url": url,
                "platform": "Wikimedia Commons",
                "license": license_name,
                "credit": credit,
                "sourceUrl": source_url,
                "termsUrl": license_url,
                "licenseSnapshot": f"{license_name} recorded on Wikimedia Commons file page",
                "authorizationProof": source_url,
                "usageScope": "app_publish",
                "width": width,
                "height": height,
                "caption": description[:120] or f"{entity_id} Wikimedia Commons image",
                "relevance": f"直接呈现或标注为 {entity_id} 相关的 Wikimedia Commons 图片：{description[:120]}",
                "creator": credit,
                "collectionPageUrl": source_url,
            }
        )
    return images


def _image_at(images: list[dict[str, Any]], index: int) -> dict[str, Any] | None:
    if not images:
        return None
    return dict(images[index % len(images)])


def _source(
    *,
    source_id: str,
    platform: str,
    url: str,
    image: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "source_id": source_id,
        "platform": platform,
        "url": url,
        "sourceUseMode": "factual_reference_only",
    }
    if image:
        row["imageUrls"] = [image]
    return row


def _plan_has_payload(plan: dict[str, Any], lane: str) -> bool:
    payload = plan.get("payload") if isinstance(plan.get("payload"), dict) else {}
    if lane == "image":
        return bool(payload.get("collections") or plan.get("collections"))
    return bool(payload.get("sources") or plan.get("sources"))


def _write_lane(path: Path, lane: str, payload_update: dict[str, Any], *, force: bool) -> bool:
    plan = read_json(path) if path.is_file() else {}
    if not force and _plan_has_payload(plan, lane):
        return False
    payload = dict(plan.get("payload") or {})
    payload.update(payload_update)
    plan["payload"] = payload
    write_json(path, plan)
    return True


def write_auto_research_plans(
    task_id: str,
    batch_id: str,
    entity_ids: list[str],
    *,
    entity_type: str,
    force: bool = False,
) -> dict[str, Any]:
    entities = [
        {"entityId": entity_id, "canonicalName": entity_id, "entityType": entity_type}
        for entity_id in entity_ids
    ]
    prepare_source_plan(task_id, batch_id, entities)
    updated: list[dict[str, Any]] = []
    issues: list[str] = []
    for entity_id in entity_ids:
        obj = resolve_entity_object_dir(task_id, batch_id, entity_id, etype_hint=entity_type)
        dl = obj / STAGE_DOWNLOAD
        wiki_title = _wiki_title("zh.wikipedia.org", entity_id)
        voyage_title = _wiki_title("zh.wikivoyage.org", entity_id)
        wiki_url = _wiki_url("zh.wikipedia.org", wiki_title)
        voyage_url = _wiki_url("zh.wikivoyage.org", voyage_title)
        qid = _wikidata_item_for_zhwiki(wiki_title)
        official_url = _official_website(qid)
        commons = _commons_images(entity_id, limit=10)
        if not wiki_url:
            issues.append(f"{entity_id}: no zhwiki source discovered")
        if not commons:
            issues.append(f"{entity_id}: no rights-compatible Commons images discovered")

        homepage_sources: list[dict[str, Any]] = []
        if official_url:
            homepage_sources.append(_source(source_id="home_official", platform="景区官网", url=official_url))
        if wiki_url:
            homepage_sources.append(
                _source(source_id="home_wikipedia", platform="维基百科", url=wiki_url, image=_image_at(commons, 0))
            )
        baidu_url = f"https://baike.baidu.com/item/{urllib.parse.quote(entity_id)}"
        homepage_sources.append(_source(source_id="home_baidu_baike", platform="百度百科", url=baidu_url))
        if _write_lane(
            dl / "homepage_source_plan.json",
            "homepage",
            {
                "primaryEvidenceRef": homepage_sources[0]["source_id"] if homepage_sources else "",
                "sources": homepage_sources[:3],
            },
            force=force,
        ):
            updated.append({"entityId": entity_id, "lane": "homepage", "sources": len(homepage_sources[:3])})

        article_sources: list[dict[str, Any]] = []
        if official_url:
            article_sources.append(
                _source(
                    source_id="article_official",
                    platform="景区官网",
                    url=official_url,
                    image=_image_at(commons, 1),
                )
            )
        if wiki_url:
            article_sources.append(
                _source(
                    source_id="article_wikipedia",
                    platform="维基百科",
                    url=wiki_url,
                    image=_image_at(commons, 2),
                )
            )
        article_sources.append(
            _source(
                source_id="article_baidu_baike",
                platform="百度百科",
                url=baidu_url,
                image=_image_at(commons, 3),
            )
        )
        if voyage_url:
            article_sources.append(
                _source(
                    source_id="article_wikivoyage",
                    platform="维基导游",
                    url=voyage_url,
                    image=_image_at(commons, 4),
                )
            )
        commons_visual = _image_at(commons, 5)
        if len(article_sources) < 4 and commons_visual:
            article_sources.append(
                _source(
                    source_id="article_commons_visual",
                    platform="Wikimedia Commons",
                    url=str(commons_visual.get("sourceUrl") or commons_visual.get("url") or ""),
                    image=commons_visual,
                )
            )
        if len(article_sources) < 4:
            issues.append(f"{entity_id}: article auto plan has {len(article_sources)} source(s), need >=4")
        if _write_lane(
            dl / "article_source_plan.json",
            "article",
            {"sources": article_sources[:4]},
            force=force,
        ):
            updated.append({"entityId": entity_id, "lane": "article", "sources": len(article_sources[:4])})

        collection_images = []
        for index, image in enumerate(commons[:20], start=1):
            item = dict(image)
            item["sourceCollectionId"] = f"commons:{entity_id}"
            item["creator"] = item.get("creator") or item.get("credit") or "Wikimedia Commons contributor"
            item["collectionPageUrl"] = (
                f"https://commons.wikimedia.org/wiki/Special:MediaSearch?type=image&search="
                f"{urllib.parse.quote(entity_id)}"
            )
            collection_images.append(item)
        if _write_lane(
            dl / "image_source_plan.json",
            "image",
            {
                "collections": [
                    {
                        "sourceCollectionId": f"commons:{entity_id}",
                        "creator": "Wikimedia Commons contributors",
                        "credit": "Wikimedia Commons contributors",
                        "collectionPageUrl": (
                            "https://commons.wikimedia.org/wiki/Special:MediaSearch?"
                            f"type=image&search={urllib.parse.quote(entity_id)}"
                        ),
                        "platform": "Wikimedia Commons",
                        "license": collection_images[0]["license"] if collection_images else "",
                        "termsUrl": collection_images[0]["termsUrl"] if collection_images else "",
                        "licenseSnapshot": "Per-file licenses recorded in Wikimedia Commons extmetadata",
                        "authorizationProof": "Wikimedia Commons API imageinfo/extmetadata",
                        "usageScope": "app_publish",
                        "images": collection_images,
                    }
                ] if collection_images else [],
            },
            force=force,
        ):
            updated.append({"entityId": entity_id, "lane": "image", "images": len(collection_images)})
    return {
        "schemaVersion": "quwoquan.download.auto_research_plan",
        "taskId": task_id,
        "batchId": batch_id,
        "updated": updated,
        "issues": issues,
    }


def handle_research_plan(args: argparse.Namespace) -> None:
    report = write_auto_research_plans(
        str(args.task),
        str(args.batch),
        [item.strip() for item in str(args.entity_ids or "").split(",") if item.strip()],
        entity_type=str(args.entity_type or ""),
        force=bool(getattr(args, "force", False)),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report.get("issues") and getattr(args, "strict", False):
        raise SystemExit(1)


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "research-plan",
        help="Bootstrap separated homepage/article/image source plans from registered public sources",
    )
    p.add_argument("--task", required=True)
    p.add_argument("--batch", required=True)
    p.add_argument("--entity-ids", required=True)
    p.add_argument("--entity-type", default="")
    p.add_argument("--force", action="store_true", help="Overwrite non-empty lane plans")
    p.add_argument("--strict", action="store_true", help="Exit non-zero when public-source discovery has gaps")
    p.set_defaults(handler=handle_research_plan)

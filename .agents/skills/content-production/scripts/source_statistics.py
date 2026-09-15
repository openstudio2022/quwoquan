"""显式 canonical manifest 范围的本地统计；不扫描、出网或判断发布资格。"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

CARRIERS = ("homepage", "article", "image", "video")
ROLES = ("adopted", "discovery", "original")
EXCLUDED_HOSTS = {"upload.wikimedia.org", "i.pinimg.com", "creativecommons.org"}
ALIASES = {"zh.wikipedia.org": "wikipedia.org", "en.wikipedia.org": "wikipedia.org",
           "www.wikipedia.org": "wikipedia.org", "www.pinterest.com": "pinterest.com",
           "www.youtube.com": "youtube.com", "youtu.be": "youtube.com"}


def safe_path(root, relative):
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("SOURCE_STATS.PATH_OUTSIDE_ROOT: 必须使用根内相对路径")
    result = root / path
    # 即使链接指回根内也拒绝，避免不同 locator 隐式共享另一个对象包。
    if any(p.is_symlink() for p in (result, *result.parents)):
        raise ValueError("SOURCE_STATS.SYMLINK_FORBIDDEN")
    if not result.resolve().is_relative_to(root):
        raise ValueError("SOURCE_STATS.PATH_OUTSIDE_ROOT")
    return result


def read_json(path):
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"SOURCE_STATS.INVALID_DOCUMENT: {path.name}")
    return value


def website(value, excluded=()):
    """只归一显式别名；未知网站保留完整 hostname，不截取末两段。"""
    if value in (None, ""):
        return None, False
    if not isinstance(value, str) or any(c.isspace() or ord(c) < 32 for c in value):
        return None, True
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        if parsed.scheme not in {"https", "http"} or not host or parsed.username or parsed.password:
            return None, True
        parsed.port  # 无效端口同样不能冒充合法 URL。
        host = host.encode("idna").decode("ascii").lower().rstrip(".")
        if not all(part and all(c.isalnum() or c == "-" for c in part) for part in host.split(".")):
            return None, True
    except (ValueError, UnicodeError):
        return None, True
    if value in excluded or host in EXCLUDED_HOSTS or (not parsed.path.startswith("/wiki/") and Path(parsed.path).suffix.lower() in {
        ".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".webm", ".m3u8", ".ogv"
    }):
        return None, False
    return ALIASES.get(host, host), False


def source_facts(source):
    metadata = source.get("metadata", {})
    work = source.get("sourceWork", {})
    if not isinstance(work, dict):
        raise ValueError("SOURCE_STATS.INVALID_SOURCE_METADATA")
    identity = work.get("identity", {})
    if not isinstance(metadata, dict) or not isinstance(identity, dict):
        raise ValueError("SOURCE_STATS.INVALID_SOURCE_METADATA")
    # 只读明确结构化槽位，不递归解析 evidence、HTML、Credit 或 raw provenance。
    assets = source.get("assets", [])
    if not isinstance(assets, list) or any(not isinstance(asset, dict) for asset in assets):
        raise ValueError("SOURCE_STATS.INVALID_SOURCE_ASSETS")
    records = [source, metadata, source.get("sourceAttribution", {})]
    records += assets
    excluded = [row[key] for row in records if isinstance(row, dict)
                for key in ("directUrl", "originalAssetUrl", "licenseUrl", "termsUrl", "cdnUrl") if key in row]
    discovery = [row.get("discoveryUrl") for row in (source, metadata)]
    page = source.get("sourceUrl")
    page_host, _ = website(page)
    if page_host == "video.baidu.com":
        discovery.append(page)  # 聚合发现不等于实际供稿/播放网站。
    adopted = [] if page in discovery else [page]
    original = [identity.get("originalUrl"), *(row.get("originalUrl") for row in records if isinstance(row, dict))]
    hosts, invalid = {}, {}
    for role, values in zip(ROLES, (adopted, discovery, original)):
        parsed = [website(value, excluded) for value in values]
        hosts[role] = {host for host, _ in parsed if host}
        invalid[role] = any(bad for _, bad in parsed)
    native = None
    provider, native_id = identity.get("provider"), identity.get("nativeId")
    if (all(isinstance(v, str) and v.strip() and v.lower() != "unknown" for v in (provider, native_id))
            and identity.get("pageUrl") == page and website(page)[0]):
        native = (provider, native_id)
    conflicts = []
    if identity.get("pageUrl") and identity["pageUrl"] != page:
        conflicts.append("sourceWork.identity.pageUrl != sourceUrl")
    if metadata.get("canonicalUrl") and metadata["canonicalUrl"] != page:
        conflicts.append("metadata.canonicalUrl != sourceUrl")
    if len({url for url in original if isinstance(url, str) and url}) > 1:
        conflicts.append("originalUrl 字段不一致；分别保留，不判定哪条为真")
    return hosts, invalid, native, conflicts


def manifest_selection(root, paths):
    """同 ID 取本次所选最高版本；同 ID/版本多个 locator 拒绝，不拼接历史。"""
    selected, seen, ignored = {}, {}, []
    for relative in dict.fromkeys(paths):
        path = safe_path(root, relative)
        if path.name != "manifest.json":
            raise ValueError("SOURCE_STATS.MANIFEST_REQUIRED")
        manifest = read_json(path)
        schema = manifest.get("schema")
        if (schema not in {"quwoquan_data.post_object", "quwoquan_data.entity_object"}
                or manifest.get("stage") not in (None, "canonical")
                or any(part in {"1.download", "4.draft", "5.review"} for part in path.relative_to(root).parts)):
            raise ValueError("SOURCE_STATS.CANONICAL_ONLY: 草稿/下载/review 不可混入")
        carrier = "homepage" if schema == "quwoquan_data.entity_object" else manifest.get("contentType")
        identity = manifest.get("entityId" if carrier == "homepage" else "contentId")
        version = manifest.get("version")
        if carrier not in CARRIERS or not isinstance(identity, str) or not identity.strip() or type(version) is not int or version < 1:
            raise ValueError("SOURCE_STATS.IDENTITY_REQUIRED")
        key = ("entity" if carrier == "homepage" else "content", identity)
        version_key = (*key, version)
        if version_key in seen:
            raise ValueError("SOURCE_STATS.VERSION_CONFLICT: 同 ID/版本有多个 locator，请显式选一份，不能假定来源副本相同")
        seen[version_key] = relative
        row = {"path": relative, "manifest": manifest, "carrier": carrier, "id": identity, "version": version}
        prior = selected.get(key)
        if prior and prior["carrier"] != carrier:
            raise ValueError("SOURCE_STATS.CARRIER_CONFLICT")
        if prior and prior["version"] >= version:
            ignored.append(relative)
        else:
            if prior:
                ignored.append(prior["path"])
            selected[key] = row
    return list(selected.values()), ignored


def object_facts(root, row):
    hosts = {role: set() for role in ROLES}
    invalid = {role: False for role in ROLES}
    native_ids, missing_refs, unknown, conflicts = set(), [], False, []
    refs = row["manifest"].get("sourceRefs", [])
    if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
        raise ValueError("SOURCE_STATS.INVALID_SOURCE_REFS")
    object_root = safe_path(root, row["path"]).parent
    for ref in dict.fromkeys(refs):
        rel = Path(ref)
        if len(rel.parts) != 3 or rel.parts[0] != "sources" or rel.name != "source.json":
            raise ValueError("SOURCE_STATS.INVALID_SOURCE_REF")
        path = safe_path(object_root, ref)
        if not path.exists():
            missing_refs.append(ref)
            unknown = True
            continue
        facts, bad, native, issues = source_facts(read_json(path))
        conflicts.extend({"sourceRef": ref, "message": issue} for issue in issues)
        for role in ROLES:
            hosts[role].update(facts[role])
            invalid[role] |= bad[role]
        if native:
            native_ids.add(native)
        else:
            unknown = True
    # 文章/主页共同引用同一参考文献不构成同一作品；媒体多源/身份缺失也不猜合并。
    native = next(iter(native_ids)) if len(native_ids) == 1 and not unknown else None
    return {**row, "hosts": hosts, "invalid": invalid, "native": native, "missingSourceRefs": missing_refs, "sourceConflicts": conflicts}


def unique_works(rows):
    groups = {}
    for row in rows:
        native = row["native"] if row["carrier"] in {"image", "video"} else None
        key = (row["carrier"], "native", native) if native else (row["carrier"], "id", row["id"])
        groups.setdefault(key, []).append(row)
    result = []
    for members in groups.values():
        result.append({"carrier": members[0]["carrier"], "members": members,
                       "hosts": {role: set().union(*(r["hosts"][role] for r in members)) for role in ROLES},
                       "invalid": {role: any(r["invalid"][role] for r in members) for role in ROLES}})
    return result


def summarize(works, role):
    total = len(works)
    counts = Counter(host for work in works for host in work["hosts"][role])
    associations = sum(counts.values())
    with_source = sum(bool(work["hosts"][role]) for work in works)
    return {"total": total, "withSource": with_source, "missingSource": total - with_source,
            "invalidURL": sum(work["invalid"][role] for work in works), "websiteCount": len(counts),
            "associationCount": associations,
            "websites": [{"website": host, "works": count, "coverageRate": count / total if total else 0,
                          "associationShare": count / associations if associations else 0}
                         for host, count in sorted(counts.items())]}


def report(root, paths):
    root = root.absolute()
    if any(p.is_symlink() for p in (root, *root.parents)) or not root.is_dir():
        raise ValueError("SOURCE_STATS.INVALID_ROOT: 根必须是实际目录且不可为 symlink")
    root = root.resolve()
    selected, ignored = manifest_selection(root, paths)
    rows = [object_facts(root, row) for row in selected]
    works = unique_works(rows)
    return {"scope": {"root": str(root), "stage": "canonical", "manifests": list(dict.fromkeys(paths)),
                      "selectedManifests": [row["path"] for row in rows], "ignoredVersions": ignored},
            "semantics": {"rates": "fraction; coverageRate 合计可大于 1；associationShare 非空时合计 1",
                          "missingSource": "没有有效作品页网站；invalidURL 可与有来源或缺失重叠",
                          "versions": "所选最高版本整份取用；同 ID/版本多个 locator 拒绝，调用方须选一份",
                          "nativeDedup": "仅 image/video 所有来源具有同一明确 provider/nativeId 时去重；其余 unknown",
                          "verification": "只读结构化事实；未验证媒体、证据摘要、发布时间或发布资格"},
            "overall": {role: summarize(works, role) for role in ROLES},
            "byCarrier": {carrier: {role: summarize([w for w in works if w["carrier"] == carrier], role)
                                     for role in ROLES} for carrier in CARRIERS},
            "nativeIdentityUnknown": sum(row["native"] is None for row in rows),
            "objects": [{"manifest": row["path"], "id": row["id"], "version": row["version"],
                         "nativeIdentity": {"provider": row["native"][0], "nativeId": row["native"][1]} if row["native"] else "unknown",
                         "missingSourceRefs": row["missingSourceRefs"], "sourceConflicts": row["sourceConflicts"]} for row in rows],
            "deduplicatedWorks": [[row["path"] for row in work["members"]] for work in works if len(work["members"]) > 1]}

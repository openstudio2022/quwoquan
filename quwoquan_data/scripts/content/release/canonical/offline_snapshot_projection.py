"""把精确 canonical 输入派生为现役公开投影；无推荐决策与环境激活。"""
from __future__ import annotations

import hashlib
import re

from content.release.canonical.offline_snapshot_contract import POST_CONTRACT, OfflineSnapshotError, PublicContractValidator, digest
from content.release.canonical.offline_snapshot_source import CanonicalSource
from core.article_package import build_article_asset_manifest

IMPORT_ROOT = "quwoquan_service/services/content-service/internal/content/post/infrastructure/releaseimport"
ENTITY_ROOT = "quwoquan_service/services/entity-service/internal/entity_homepage/homepage"


def runtime_post_id(content_id: str) -> str:
    # Go RuntimePostID 的纯身份算法；局部合同直接执行当前 Go 函数比较结果。
    value = content_id.strip()
    return "data_post_" + hashlib.sha256(("qwq-content-post:" + value).encode()).hexdigest() if value else ""


def runtime_homepage_id(entity_ref: str) -> str:
    # Homepage StableID 对 source-owned 导入的分支；不拿 Data entityId 当 homepageId。
    return "hp_" + hashlib.sha256(("source\x00qwq_data\x00" + entity_ref.strip().removeprefix("/entity/")).encode()).hexdigest()[:32]


def article_summary(markdown: str, limit: int) -> str:
    # 与 ProjectImportedArticleSummary 一致：保留正文全文，只对卡片摘要做投影。
    import yaml
    text = markdown.replace("\r\n", "\n").lstrip("\ufeff")
    lines = text.split("\n")
    explicit = ""
    if lines[0].strip() == "---":
        end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
        if end is None:
            return ""
        metadata = yaml.safe_load("\n".join(lines[1:end]))
        if isinstance(metadata, dict):
            explicit = str(metadata.get("summary") or "").strip()
        lines = lines[end + 1:]
    paragraph, directive = [], False
    for line in lines:
        line = line.strip()
        if line.startswith(":::"):
            directive = not directive
            continue
        if directive or line.startswith("asset://") or line.startswith("#"):
            continue
        if not line:
            if paragraph:
                break
            continue
        paragraph.append(line)
    value = explicit or " ".join(paragraph)
    if not explicit:
        value = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", value)
        for token in ("**", "__", "`"):
            value = value.replace(token, "")
    value = " ".join(value.split())
    return value if len(value) <= limit else value[:limit - 1] + "…"


def project_post(source: CanonicalSource, ref: str, media: dict[str, dict], validator: PublicContractValidator) -> dict:
    m = source.json(ref + "/manifest.json")
    creator = source.json("creators/" + m["creatorProfileId"] + "/profile.json")
    avatar = media[creator["avatarAsset"]["assetId"]]
    content_type = m["contentType"]
    post_id = runtime_post_id(m["contentId"])
    if not post_id:
        raise OfflineSnapshotError("OFFLINE.POST_ID_MISSING")
    view = {"postId": post_id, "contentType": content_type, "contentIdentity": m["contentIdentity"],
            "authorId": m["authorId"], "authorDisplayName": creator["displayName"],
            "authorAvatarUrl": avatar["canonicalReference"], "authorAvatarAssetId": avatar["assetId"], "authorAvatarAccessMode": "public",
            "title": m["title"] if content_type == "image" else m["publishTitle"],
            "likeCount": 0, "commentCount": 0, "shareCount": 0, "viewerLiked": None,
            "createdAt": m["createdAt"], "updatedAt": m["updatedAt"], "publishedAt": m["publishedAt"], "contentVertical": m["vertical"]}
    detail = {**view, "status": "published", "visibility": "public", "viewCount": 0,
              "tagRefs": m["tagRefs"], "entityRefs": m["entityRefs"],
              "sourceAttribution": {f["name"]: m["sourceAttribution"][f["name"]] for f in validator.types["SourceAttribution"]["fields"] if f["name"] in m["sourceAttribution"]}}
    if m["entityRefs"]:
        homepage_ref = m["entityRefs"][0]
        entity = source.json("entities/" + homepage_ref.removeprefix("/entity/") + "/manifest.json")
        for target in (view, detail):
            target.update(primaryHomepageId=runtime_homepage_id(homepage_ref), primaryHomepageType=_homepage_type(entity["type"], validator))
    elif content_type not in {"image", "video"}:
        raise OfflineSnapshotError("OFFLINE.HOMEPAGE_REFERENCE_MISSING")
    if content_type == "article":
        _project_article(source, ref, m, media, validator, view, detail)
    if m["assets"] or content_type != "article":
        _project_media(m, media, validator, view, detail)
    validator.validate_projection(view, "content_post_projection")
    validator.validate_projection(detail, "content_post_detail_slice")
    return {"sourceObjectRef": ref, "projection": view, "detail": detail}


def _homepage_type(entity_type: str, validator: PublicContractValidator) -> str:
    # 从现役 importer 的具名闭集读取，不复制第三份类型映射或默认 sight。
    ref = f"{ENTITY_ROOT}/infrastructure/homepageimport/loader.go"
    raw = validator.repo.joinpath(ref).read_bytes()
    validator.files[ref] = raw
    block = re.search(r"var entityTypeToHomepageType = map\[string\]string\{(.*?)\n\}", raw.decode(), re.S)
    if block is None:
        raise OfflineSnapshotError("OFFLINE.HOMEPAGE_TYPE_CONTRACT_INVALID")
    mapping = dict(re.findall(r'"([^"]+)":\s*"([^"]+)"', block.group(1)))
    if entity_type.strip() not in mapping:
        raise OfflineSnapshotError("OFFLINE.HOMEPAGE_TYPE_UNSUPPORTED")
    return mapping[entity_type.strip()]


def _project_article(source, ref, metadata, media, validator, view, detail):
    markdown = source.read(ref + "/article.md").decode("utf-8")
    profile = metadata["articleRenderProfile"]
    manifest = build_article_asset_manifest(markdown, metadata["assets"], render_profile=profile)
    manifest["documentVersionSha256"] = manifest.pop("documentBundleSha256")
    # 摘要继续绑定原始 Data package；wire 资产只从当前公共合同字段投影。
    public_fields = {field["name"] for field in validator.types["PostArticleAsset"]["fields"]}
    manifest["assets"] = []
    for asset in metadata["assets"]:
        row = media[asset["assetId"]]
        public = {key: value for key, value in asset.items() if key in public_fields}
        public.update(accessMode="public", publicSliceKey=row["canonicalReference"])
        manifest["assets"].append(public)
    validator.validate_type(manifest, "PostArticleAssetManifest")
    limit = validator.load(f"{POST_CONTRACT}/publication_policy.yaml")["text_limits"]["summary_max_runes"]
    for target in (view, detail):
        target.update(body=markdown, summary=article_summary(markdown, limit), articleTemplate=profile["template"], articleFontPreset=profile["fontPreset"])
    detail.update(articleMarkdown=markdown, markdownDialect=metadata["markdownDialect"], articleMarkdownDigest=manifest["articleMarkdownDigest"], articleAssetManifest=manifest, articleRenderProfile=profile)


def _project_media(metadata, media, validator, view, detail):
    content_type = metadata["contentType"]
    public_fields = {field["name"] for field in validator.types["PostMediaItem"]["fields"]}
    sequence, asset_ids = [], []
    for asset in metadata["assets"]:
        if content_type == "video" and asset["kind"] != "video":
            continue
        row = media[asset["assetId"]]
        item = {"kind": row["kind"], "mediaAssetId": row["assetId"], "mediaAssetVersion": 1, "accessMode": "public", "url": row["canonicalReference"]}
        asset_ids.append(row["assetId"])
        for key in ("caption", "role"):
            if asset.get(key):
                item[key] = asset[key]
        for key in ("width", "height", "durationMs"):
            if key in row:
                item[key] = row[key]
        if content_type == "video":
            poster = media[asset["posterAssetId"]]
            asset_ids.append(poster["assetId"])
            item.update(coverUrl=poster["canonicalReference"], thumbnailUrl=poster["canonicalReference"], coverAssetId=poster["assetId"],
                        coverStrategy=asset.get("coverStrategy") or "first_frame", coverFrameTimeMs=asset.get("coverFrameTimeMs", 0))
        sequence.append({key: value for key, value in item.items() if key in public_fields})
    if not sequence or content_type == "video" and len(sequence) != 1:
        raise OfflineSnapshotError("OFFLINE.POST_MEDIA_CLOSURE_INVALID")
    first = sequence[0]
    for target in (view, detail):
        target.update(mediaItems=sequence, coverUrl=first.get("coverUrl", first["url"]), mediaUrls=[i["url"] for i in sequence])
        for key in ("width", "height", "durationMs"):
            if key in first:
                target[key] = first[key]
        if content_type == "image":
            target.update(body=metadata["caption"], summary=metadata["caption"])
        elif content_type == "video":
            # 无 article.md 的视频保持现役 importer 空 body/summary，不从 caption 发明语义。
            target.update(body="", summary="", videoUrl=first["url"], thumbnailUrl=first["coverUrl"])
    detail["mediaAssetIds"] = list(dict.fromkeys(asset_ids))
    view.update(mediaAssetId=first["mediaAssetId"], mediaAssetVersion=1)


def project_configuration(validator: PublicContractValidator) -> dict:
    ui = validator.load(f"{POST_CONTRACT}/ui_config.yaml")
    # 只派生已有 UI 默认值；灰度配置不声称在线流量分桶或实验准入。
    public_flags = {f.get("client_wire_name", f["name"]) for f in validator.types["ContentAppConfigFeatureFlags"]["fields"]}
    content = {"feature_flags": {r["flag"]: r["default"] for r in ui["feature_flags"] if r["flag"] in public_flags},
               "gray_release": {"experiment_bucket": "alpha_offline_engineering", "current_stage": "alpha_offline_engineering", "canary_matrix": []}}
    # 不整体覆盖首页频道 UI；实际离线内容成员由 bundle.channels 独立绑定。
    validator.validate_type(content, "ContentAppConfig")
    return {"content": content}


def project_creators(source: CanonicalSource, refs: list[str], media: dict[str, dict], posts: list[dict], selected_at: str) -> list[dict]:
    results = []
    for ref in refs:
        profile = source.json(f"creators/{ref}/profile.json")
        avatar = media[profile["avatarAsset"]["assetId"]]
        public = {"personaId": profile["authorId"], "subjectType": "creator", "userHandle": profile["userHandle"],
                  "displayName": profile["displayName"], "nicknameCustomized": False, "bio": profile["bio"], "headline": profile["headline"],
                  "disclosure": profile["disclosure"]["displayText"], "avatarUrl": avatar["canonicalReference"],
                  "avatarAssetId": avatar["assetId"], "avatarAccessMode": "public", "followerCount": 0, "followingCount": 0,
                  "postCount": sum(p["projection"]["authorId"] == profile["authorId"] for p in posts), "circleCount": 0, "likeCount": 0,
                  "profileVisibility": "public", "isolationLevel": "open", "inheritsFromOwner": False, "updatedAt": selected_at}
        results.append({"sourceObjectRef": f"creators/{ref}", "projection": public})
    return results


def project_homepages(source: CanonicalSource, refs: list[str], media: dict[str, dict], selected_at: str, validator: PublicContractValidator) -> list[dict]:
    results = []
    for ref in refs:
        manifest = source.json(f"entities/{ref}/manifest.json")
        header = manifest
        homepage_type = _homepage_type(header["type"], validator)
        markdown = source.read(f"entities/{ref}/page.md").decode("utf-8")
        assets = [{"assetId": a["assetId"], "url": media[a["assetId"]]["canonicalReference"], "accessMode": "public", "caption": a["caption"],
                   "role": {"cover": "cover", "detail": "inline", "inline": "inline", "related": "related"}[a["role"]]} for a in manifest["assets"]]
        public = {"homepageId": runtime_homepage_id(header["entityRef"]), "displayName": header["label"], "homepageType": homepage_type,
                  "summary": "", "sections": [{"kind": "body", "title": header["label"], "bodyMarkdown": markdown, "assets": assets, "timelineItems": []}],
                  "relatedObjects": [], "primarySource": {field["name"]: header["primarySource"][field["name"]] for field in validator.load(f"{validator.entity_contract}/homepage_source.yaml")["fields"]},
                  "sourceUrls": header["sourceUrls"], "updatedAt": selected_at}
        results.append({"sourceObjectRef": f"entities/{ref}", "projection": public})
    return results

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
    homepage_ref = m["entityRefs"][0]
    # exact 西湖 cohort 属于已登记景区类型；其他实体类型不得猜测映射。
    entity = source.json("entities/" + homepage_ref.removeprefix("/entity/") + "/_entity.json")
    if entity["type"] != "景区":
        raise OfflineSnapshotError("OFFLINE.HOMEPAGE_TYPE_UNSUPPORTED")
    for target in (view, detail):
        target.update(primaryHomepageId=runtime_homepage_id(homepage_ref), primaryHomepageType="sight")
    assets = m["assets"]
    if content_type == "article":
        markdown = source.read(ref + "/article.md").decode("utf-8")
        if assets or m.get("publishMediaMode") != "text_only":
            raise OfflineSnapshotError("OFFLINE.ILLUSTRATED_ARTICLE_NOT_IMPLEMENTED")
        limit = validator.load(f"{POST_CONTRACT}/publication_policy.yaml")["text_limits"]["summary_max_runes"]
        profile = m["articleRenderProfile"]
        manifest = build_article_asset_manifest(markdown, [], render_profile=profile)
        # Data package 内的 bundle 名称不属于公共 wire；公共合同名为 documentVersionSha256。
        manifest["documentVersionSha256"] = manifest.pop("documentBundleSha256")
        for target in (view, detail):
            target.update(body=markdown, summary=article_summary(markdown, limit), articleTemplate=profile["template"], articleFontPreset=profile["fontPreset"])
        detail.update(articleMarkdown=markdown, markdownDialect=m["markdownDialect"], articleMarkdownDigest=manifest["articleMarkdownDigest"], articleAssetManifest=manifest, articleRenderProfile=profile)
    else:
        sequence = []
        for asset in assets:
            if content_type == "video" and asset["kind"] != "video":
                continue
            row = media[asset["assetId"]]
            item = {"kind": row["kind"], "mediaAssetId": row["assetId"], "mediaAssetVersion": 1, "accessMode": "public", "url": row["canonicalReference"]}
            for key in ("width", "height", "durationMs"):
                if key in row:
                    item[key] = row[key]
            if content_type == "video":
                poster = media[asset["posterAssetId"]]
                item.update(coverUrl=poster["canonicalReference"], coverAssetId=poster["assetId"])
            sequence.append(item)
        if not sequence or content_type == "video" and len(sequence) != 1:
            raise OfflineSnapshotError("OFFLINE.POST_MEDIA_CLOSURE_INVALID")
        first = sequence[0]
        for target in (view, detail):
            target["mediaItems"] = sequence
            target["coverUrl"] = first.get("coverUrl", first["url"])
            for key in ("width", "height", "durationMs"):
                if key in first:
                    target[key] = first[key]
            if content_type == "image":
                target.update(body=m["caption"], summary=m["caption"], mediaUrls=[i["url"] for i in sequence])
            else:
                # 当前 importer 对无 article.md 的 video body/summary 为空，不擅自用 caption 改线上语义。
                target.update(body="", summary="", videoUrl=first["url"], thumbnailUrl=first["coverUrl"])
        detail["mediaAssetIds"] = [i["mediaAssetId"] for i in sequence]
        view.update(mediaAssetId=first["mediaAssetId"], mediaAssetVersion=1)
    validator.validate_projection(view, "content_post_projection")
    validator.validate_projection(detail, "content_post_detail_slice")
    return {"sourceObjectRef": ref, "projection": view, "detail": detail}


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
        header = source.json(f"entities/{ref}/_entity.json")
        manifest = source.json(f"entities/{ref}/manifest.json")
        if header["type"] != "景区":
            raise OfflineSnapshotError("OFFLINE.HOMEPAGE_TYPE_UNSUPPORTED")
        markdown = source.read(f"entities/{ref}/page.md").decode("utf-8")
        assets = [{"assetId": a["assetId"], "url": media[a["assetId"]]["canonicalReference"], "accessMode": "public", "caption": a["caption"],
                   "role": {"cover": "cover", "detail": "inline", "inline": "inline", "related": "related"}[a["role"]]} for a in manifest["assets"]]
        public = {"homepageId": runtime_homepage_id(header["entityRef"]), "displayName": header["label"], "homepageType": "sight",
                  "summary": "", "sections": [{"kind": "body", "title": header["label"], "bodyMarkdown": markdown, "assets": assets, "timelineItems": []}],
                  "relatedObjects": [], "primarySource": {field["name"]: header["primarySource"][field["name"]] for field in validator.load(f"{validator.entity_contract}/homepage_source.yaml")["fields"]},
                  "sourceUrls": header["sourceUrls"], "updatedAt": selected_at}
        results.append({"sourceObjectRef": f"entities/{ref}", "projection": public})
    return results

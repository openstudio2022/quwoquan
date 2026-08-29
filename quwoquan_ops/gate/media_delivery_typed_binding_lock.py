"""release 媒体消费面的 typed 交付绑定防回潮锁（DEC-033）。

私有媒体消费只在「每个消费点都经同一 typed 入口」时才成立。历史形态是每个页面
自己写一次 `accessMode == signedGrant ? 私有原子 : 公开原子`，于是「什么算私有」
被复制成 N 份：新增一处消费点漏判，私有资产要么走公开 URL 把授权判定悄悄跳过，
要么直接空图，而两种后果在 local_contract 里都不会红。

本锁把两种回潮形态各自判否：

- **直连公开图片原子**：消费面直接构造 `AppCachedNetworkImage`。允许的唯一形态是
  作为 typed 入口的分流回调（`publicBuilder` / `readyBuilder`），即分流已经发生、
  这里只负责渲染已定的那一路。
- **传非 typed 裸 URL**：已 typed 化的组件 API 重新暴露裸 URL 或旧的非绑定入参。

锁只覆盖已完成收口的消费面清单——没收口的面留在 OPEN 里，不靠把锁放宽来假装通过。
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_LIB = ROOT / "quwoquan_app" / "lib"

# 已收口的 release 媒体消费面：这些文件里不得再直连公开图片原子。
_SEALED_CONSUMER_SURFACES = (
    "service/content_service/media/media_asset/presentation/works_immersive_viewer_canvas.dart",
    "service/content_service/media/media_asset/presentation/works_immersive_viewer_build.dart",
    "service/content_service/media/media_asset/presentation/works_immersive_viewer_presentation.dart",
    "service/content_service/media/media_asset/presentation/video_player_surface_builder.dart",
    "service/content_service/media/media_asset/presentation/video_playback_failure_overlay.dart",
    "service/content_service/content/post/presentation/home_multi_form_feed_media.dart",
    "service/content_service/content/post/presentation/home_multi_form_feed_media_grid.dart",
    "service/content_service/content/post/presentation/article_reader/content/article_reader_page_surfaces_frontispiece.dart",
    "service/content_service/media/media_asset/presentation/image_book_canvas.dart",
    "service/content_service/content/post/presentation/article_reader/content/article_reader_page_surfaces_blocks.dart",
    "service/entity_service/entity_homepage/homepage/presentation/homepage_detail_shell_builders.dart",
)

_PUBLIC_IMAGE_ATOM = "AppCachedNetworkImage("

# 分流已发生的合法渲染位：typed 入口把已定的那一路交回消费面渲染。
_DISPATCH_CALLBACKS = ("publicBuilder", "readyBuilder", "signedReadyBuilder")

# 已 typed 化的组件 API 与其禁止回潮的入参。
_TYPED_API_SURFACES = {
    "service/content_service/media/media_asset/presentation/video_player_widget_api.dart": {
        "required": ("MediaDeliveryBinding thumbnailBinding",),
        "forbidden": ("thumbnailUrl", "MediaDeliveryReference? thumbnailReference"),
    },
    "service/content_service/media/original_access_quota/presentation/media_delivery_image.dart": {
        "required": ("MediaDeliveryBinding binding",),
        "forbidden": (),
    },
    "service/content_service/media/media_asset/presentation/image_book_canvas.dart": {
        "required": ("List<MediaDeliveryBinding> deliveries",),
        # 沉浸图书自己解码而非用图片 widget，回潮形态是页序退回 URL 字符串列表。
        "forbidden": ("List<String> imageUrls", "required this.imageUrls"),
    },
    "service/content_service/media/original_access_quota/presentation/media_delivery_video.dart": {
        "required": ("MediaDeliveryBinding binding",),
        "forbidden": (),
    },
    "service/content_service/content/post/presentation/article_reader/content/article_reader_page_surfaces_blocks.dart": {
        "required": ("MediaDeliveryBinding binding",),
        "forbidden": (),
    },
    "service/entity_service/entity_homepage/homepage/presentation/homepage_detail_shell_builders.dart": {
        # hero 三处渲染位共用同一个绑定推导；推导函数消失即回潮。
        "required": ("MediaDeliveryBinding _resolvedHeroBinding()",),
        "forbidden": ("imageSource: coverUrl",),
    },
}

# 私有视频取址必经短签交付：播放器不得重新暴露裸 URL 入参，消费面也不得在
# 私有绑定上拿公开引用顶替。两者都会让授权判定被悄悄跳过。
_SIGNED_VIDEO_DELIVERY_SURFACE = (
    "service/content_service/media/media_asset/presentation/video_player_widget_api.dart"
)
_SIGNED_VIDEO_REQUIRED_TOKENS = (
    "SignedVideoDelivery? signedDelivery",
    "MediaDeliveryReference? deliveryReference",
)
_SIGNED_VIDEO_FORBIDDEN_TOKENS = (
    "required this.deliveryReference",
    "String videoUrl",
)

# 私有交付的换签编排唯一入口。这些文件里出现 requestOriginalAccess 直调，说明
# 某个消费面又自建了一条授权路径，grant 缓存、单飞与校验就不再是单点。
_COORDINATOR_ONLY_GRANT_SURFACES = (
    "service/content_service/media/media_asset/presentation/works_immersive_viewer_engagement_actions.dart",
    "service/content_service/media/media_asset/presentation/image_book_canvas.dart",
    "service/content_service/media/original_access_quota/presentation/media_delivery_video.dart",
    "service/content_service/content/post/presentation/home_multi_form_feed_media_grid.dart",
    "service/content_service/media/media_asset/presentation/works_immersive_viewer_canvas.dart",
)

_DIRECT_GRANT_CALL = "requestOriginalAccess("


def _direct_public_atom_lines(text: str) -> list[int]:
    """返回直连公开图片原子的行号（1 基），排除分流回调内的合法渲染位。"""
    offenders: list[int] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if _PUBLIC_IMAGE_ATOM not in line:
            continue
        if any(callback in line for callback in _DISPATCH_CALLBACKS):
            continue
        offenders.append(number)
    return offenders


def validate(issues: list[str]) -> None:
    for relative in _SEALED_CONSUMER_SURFACES:
        path = APP_LIB / relative
        if not path.is_file():
            issues.append(
                f"typed 交付锁指向的消费面已不存在，锁与代码脱节需同步: {relative}"
            )
            continue
        offenders = _direct_public_atom_lines(path.read_text(encoding="utf-8"))
        if offenders:
            lines = ", ".join(str(number) for number in offenders)
            issues.append(
                f"{relative}:{lines} 直连 AppCachedNetworkImage 绕过 typed 交付入口；"
                "公开图片原子只允许作为 publicBuilder/readyBuilder 分流回调渲染"
            )

    for relative, rules in _TYPED_API_SURFACES.items():
        path = APP_LIB / relative
        if not path.is_file():
            issues.append(f"typed 交付锁指向的组件 API 已不存在: {relative}")
            continue
        text = path.read_text(encoding="utf-8")
        for token in rules["required"]:
            if token not in text:
                issues.append(f"{relative} 缺 typed 绑定入参: {token}")
        for token in rules["forbidden"]:
            if token in text:
                issues.append(f"{relative} 重新暴露非 typed 入参: {token}")

    for relative in _COORDINATOR_ONLY_GRANT_SURFACES:
        path = APP_LIB / relative
        if not path.is_file():
            issues.append(f"typed 交付锁指向的消费面已不存在: {relative}")
            continue
        text = path.read_text(encoding="utf-8")
        if _DIRECT_GRANT_CALL in text:
            issues.append(
                f"{relative} 直调 requestOriginalAccess 绕过 "
                "SignedMediaDeliveryCoordinator；grant 兑换、校验、缓存与换签"
                "只允许收敛在协调器一处"
            )

    signed_video_path = APP_LIB / _SIGNED_VIDEO_DELIVERY_SURFACE
    if not signed_video_path.is_file():
        issues.append(
            f"typed 交付锁指向的视频 API 已不存在: {_SIGNED_VIDEO_DELIVERY_SURFACE}"
        )
    else:
        text = signed_video_path.read_text(encoding="utf-8")
        for token in _SIGNED_VIDEO_REQUIRED_TOKENS:
            if token not in text:
                issues.append(
                    f"{_SIGNED_VIDEO_DELIVERY_SURFACE} 缺私有视频交付接缝: {token}"
                )
        for token in _SIGNED_VIDEO_FORBIDDEN_TOKENS:
            if token in text:
                issues.append(
                    f"{_SIGNED_VIDEO_DELIVERY_SURFACE} 重新把公开引用变为必填或"
                    f"暴露裸 URL 入参: {token}"
                )

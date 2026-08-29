import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/runtime/di/media_delivery_composition.dart';

/// 从 Post 投影推导渲染 URL 的 typed 交付绑定（DEC-033）。
///
/// 「什么算私有」只有这一处实现。每个消费面各自从 `mediaItems` 里翻一遍
/// assetId/accessMode，就等于把判据复制成 N 份：新增一处消费点漏翻，私有资产
/// 要么走公开 URL 把授权判定悄悄跳过，要么直接空图，而两种后果在本地契约里
/// 都不会红。
///
/// 索引同时收录逐条媒体的 `url→mediaAssetId` 与封面的 `coverUrl→coverAssetId`：
/// 视频封面与视频本体是两个资产，封面用视频自身的 mediaAssetId 换签会换错对象。
Map<String, MediaDeliveryBinding> contentPostMediaBindings(
  ContentPostViewData post,
) {
  final index = <String, MediaDeliveryBinding>{};
  for (final media in post.mediaItems) {
    final url = media.url.trim();
    if (url.isNotEmpty) {
      index[url] = MediaDeliveryBinding(
        assetId: media.mediaAssetId?.trim() ?? '',
        accessMode: media.accessMode,
        publicUrl: url,
      );
    }
    final coverUrl = media.coverUrl?.trim() ?? '';
    if (coverUrl.isNotEmpty) {
      index[coverUrl] = MediaDeliveryBinding(
        assetId: media.coverAssetId?.trim() ?? '',
        accessMode: media.accessMode,
        publicUrl: coverUrl,
      );
    }
  }
  return index;
}

/// 作者头像的 typed 交付绑定（DEC-033，kind 用 avatar 而非 image）。
///
/// 头像与内容图是两条 kind，签发与缓存身份都不同；消费面不得拿内容图的推导
/// 顶替。资产身份缺席即退回公开路，不猜 accessMode。
MediaDeliveryBinding contentPostAuthorAvatarBinding(ContentPostViewData post) {
  return MediaDeliveryBinding(
    assetId: post.authorAvatarAssetId?.trim() ?? '',
    accessMode: post.authorAvatarAccessMode,
    publicUrl: post.avatarUrl.trim(),
  );
}

/// 取某个渲染 URL 的交付绑定。
///
/// 投影未声明该 URL 的交付形态时返回仅带公开 URL 的绑定，由统一入口按四形态
/// 判定；此处不替它猜一个 accessMode——猜 public 会让私有资产走公开直连。
MediaDeliveryBinding contentPostMediaBinding(
  ContentPostViewData post,
  String url,
) {
  final normalized = url.trim();
  if (normalized.isEmpty) {
    return const MediaDeliveryBinding.absent();
  }
  return contentPostMediaBindings(post)[normalized] ??
      MediaDeliveryBinding(
        assetId: '',
        accessMode: null,
        publicUrl: normalized,
      );
}

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/adapters/cdn_image_url_builder.dart';
import 'package:quwoquan_app/design_system/media/cdn_image_url_port.dart';

/// [CdnImageUrlPort] 的 content 域 production 实现。
///
/// 只有本组合根文件可以命名 content 域的 CDN adapter；通用图片原子只依赖端口。
final class _ContentCdnImageUrlAdapter implements CdnImageUrlPort {
  const _ContentCdnImageUrlAdapter();

  @override
  String thumbnail(String url) => CdnImageUrlBuilder.thumbnail(url);

  @override
  String cover(String url) => CdnImageUrlBuilder.cover(url);

  @override
  String display(String url) => CdnImageUrlBuilder.display(url);

  @override
  String avatar(String url, {required int size}) =>
      CdnImageUrlBuilder.avatar(url, size: size);

  @override
  String full(String url) => CdnImageUrlBuilder.full(url);
}

final cdnImageUrlPortProvider = Provider<CdnImageUrlPort>(
  (ref) => const _ContentCdnImageUrlAdapter(),
);

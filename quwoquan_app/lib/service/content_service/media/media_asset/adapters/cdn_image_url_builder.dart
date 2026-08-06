import 'package:quwoquan_app/service/content_service/media/media_asset/application/generated/content_image_variant_policy.g.dart';
import 'package:quwoquan_app/runtime/transport/media/cdn_media_url_processor.dart';

/// CDN image processing URL builder.
///
/// Appends OSS/CDN image processing parameters for on-the-fly resize,
/// format conversion, and quality optimization. Compatible with:
/// - Alibaba Cloud OSS image processing
/// - Cloudflare Image Resizing
/// - MinIO (passthrough, no processing)
class CdnImageUrlBuilder {
  CdnImageUrlBuilder._();

  static String thumbnail(String originalUrl) {
    return _contentProfile(originalUrl, 'thumbnail');
  }

  static String avatar(String originalUrl, {int size = 120}) {
    return CdnMediaUrlProcessor.avatar(originalUrl, size: size);
  }

  static String display(String originalUrl) {
    return _contentProfile(originalUrl, 'display');
  }

  static String cover(String originalUrl) {
    return _contentProfile(originalUrl, 'cover');
  }

  static String full(String originalUrl) {
    return _contentProfile(originalUrl, 'full');
  }

  static String _contentProfile(String originalUrl, String profileName) {
    final profile = ContentImageVariantPolicy.profile(profileName);
    return CdnMediaUrlProcessor.applyOssProcess(
      originalUrl,
      profile.processing,
    );
  }
}

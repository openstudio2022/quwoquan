import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/application/content/media/generated/content_image_variant_policy.g.dart';

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
    if (originalUrl.isEmpty) return originalUrl;
    if (!_isCdnUrl(originalUrl)) return originalUrl;
    return _appendOssProcess(
      originalUrl,
      'image/resize,w_$size,h_$size,m_fill/format,webp/quality,q_85',
    );
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
    if (originalUrl.isEmpty) return originalUrl;
    if (!_isCdnUrl(originalUrl)) return originalUrl;
    final profile = ContentImageVariantPolicy.profile(profileName);
    return _appendOssProcess(originalUrl, profile.processing);
  }

  static bool _isCdnUrl(String url) {
    final candidate = Uri.tryParse(url);
    if (candidate == null || candidate.host.isEmpty) return false;
    for (final baseUrl in <String>[
      CloudRuntimeConfig.mediaAvatarCdnBaseUrl,
      CloudRuntimeConfig.mediaImageCdnBaseUrl,
    ]) {
      final authority = Uri.tryParse(baseUrl);
      if (authority != null &&
          authority.host.isNotEmpty &&
          candidate.scheme == authority.scheme &&
          candidate.host == authority.host &&
          candidate.port == authority.port) {
        return true;
      }
    }
    return false;
  }

  static String _appendOssProcess(String url, String process) {
    final separator = url.contains('?') ? '&' : '?';
    return '$url${separator}x-oss-process=$process';
  }
}

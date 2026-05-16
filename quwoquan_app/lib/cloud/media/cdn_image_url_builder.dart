import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';

/// CDN image processing URL builder.
///
/// Appends OSS/CDN image processing parameters for on-the-fly resize,
/// format conversion, and quality optimization. Compatible with:
/// - Alibaba Cloud OSS image processing
/// - Cloudflare Image Resizing
/// - MinIO (passthrough, no processing)
class CdnImageUrlBuilder {
  CdnImageUrlBuilder._();

  static String thumbnail(String originalUrl, {int width = 400}) {
    if (originalUrl.isEmpty) return originalUrl;
    if (!_isCdnUrl(originalUrl)) return originalUrl;
    return _appendOssProcess(originalUrl, 'image/resize,w_$width/format,webp/quality,q_80');
  }

  static String avatar(String originalUrl, {int size = 120}) {
    if (originalUrl.isEmpty) return originalUrl;
    if (!_isCdnUrl(originalUrl)) return originalUrl;
    return _appendOssProcess(originalUrl, 'image/resize,w_$size,h_$size,m_fill/format,webp/quality,q_85');
  }

  static String cover(String originalUrl, {int width = 750}) {
    if (originalUrl.isEmpty) return originalUrl;
    if (!_isCdnUrl(originalUrl)) return originalUrl;
    return _appendOssProcess(originalUrl, 'image/resize,w_$width/format,webp/quality,q_85');
  }

  static String full(String originalUrl) {
    if (originalUrl.isEmpty) return originalUrl;
    if (!_isCdnUrl(originalUrl)) return originalUrl;
    return _appendOssProcess(originalUrl, 'image/format,webp/quality,q_90');
  }

  static bool _isCdnUrl(String url) {
    final cdnDomain = CloudRuntimeConfig.cdnDomain;
    if (cdnDomain.isEmpty) return false;
    return url.contains(cdnDomain);
  }

  static String _appendOssProcess(String url, String process) {
    final separator = url.contains('?') ? '&' : '?';
    return '$url${separator}x-oss-process=$process';
  }
}

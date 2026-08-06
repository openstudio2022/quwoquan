import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';

/// Applies CDN image transforms only to authorities injected by the runtime
/// package. Business surfaces provide the transform profile; this utility owns
/// the shared origin validation and query composition.
abstract final class CdnMediaUrlProcessor {
  static String avatar(String originalUrl, {int size = 120}) {
    return applyOssProcess(
      originalUrl,
      'image/resize,w_$size,h_$size,m_fill/format,webp/quality,q_85',
    );
  }

  static String applyOssProcess(String originalUrl, String process) {
    if (originalUrl.isEmpty || !_isCdnUrl(originalUrl)) {
      return originalUrl;
    }
    final separator = originalUrl.contains('?') ? '&' : '?';
    return '$originalUrl${separator}x-oss-process=$process';
  }

  static bool _isCdnUrl(String url) {
    final candidate = Uri.tryParse(url);
    if (candidate == null || candidate.host.isEmpty) {
      return false;
    }
    for (final baseUrl in <String>[
      CloudRuntimeConfig.mediaAvatarCdnBaseUrl,
      CloudRuntimeConfig.mediaImageCdnBaseUrl,
    ]) {
      final authority = Uri.tryParse(baseUrl);
      if (authority != null &&
          authority.host.isNotEmpty &&
          candidate.scheme == authority.scheme &&
          candidate.host == authority.host &&
          candidate.port == authority.port &&
          _isWithinBasePath(candidate.path, authority.path)) {
        return true;
      }
    }
    return false;
  }

  static bool _isWithinBasePath(String candidatePath, String basePath) {
    final normalizedBase = basePath.replaceFirst(RegExp(r'/+$'), '');
    return normalizedBase.isNotEmpty &&
        (candidatePath == normalizedBase ||
            candidatePath.startsWith('$normalizedBase/'));
  }
}

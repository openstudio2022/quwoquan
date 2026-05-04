import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';

/// 将服务端头像引用解析为可被 Flutter 图片组件加载的 URL。
///
/// beta/local-gamma 中头像字段可能是 `/media/avatar/...` 或
/// `media/avatar/...`。UI 组件不能直接把这类相对路径交给
/// `Image.network`，否则会落到文字占位。
String resolveAvatarImageUrl(
  String? raw, {
  String? gatewayBaseUrl,
  String? avatarCdnBaseUrl,
}) {
  final source = raw?.trim() ?? '';
  if (source.isEmpty) {
    return '';
  }

  final lower = source.toLowerCase();
  if (lower.startsWith('data:image/')) {
    return source;
  }
  if (lower.startsWith('http://') || lower.startsWith('https://')) {
    return _resolveAbsoluteAvatarUrl(
      source,
      gatewayBaseUrl: gatewayBaseUrl ?? CloudRuntimeConfig.gatewayBaseUrl,
      avatarCdnBaseUrl:
          avatarCdnBaseUrl ?? CloudRuntimeConfig.mediaAvatarCdnBaseUrl,
    );
  }
  if (source.startsWith('//')) {
    return 'https:$source';
  }
  if (_looksLikeBareHostUrl(source)) {
    return 'https://$source';
  }

  final base = _relativeAvatarBase(
    gatewayBaseUrl ?? CloudRuntimeConfig.gatewayBaseUrl,
    avatarCdnBaseUrl ?? CloudRuntimeConfig.mediaAvatarCdnBaseUrl,
  );
  if (base.isEmpty) {
    return '';
  }

  if (source.startsWith('/')) {
    return _joinBaseAndPath(base, source);
  }
  if (_looksLikeMediaObjectKey(source)) {
    return _joinBaseAndPath(base, '/$source');
  }

  return '';
}

String _resolveAbsoluteAvatarUrl(
  String source, {
  required String gatewayBaseUrl,
  required String avatarCdnBaseUrl,
}) {
  final uri = Uri.tryParse(source);
  if (uri == null || !uri.hasScheme || uri.host.isEmpty) {
    return source;
  }
  if (!_looksLikeMediaObjectKey(uri.path.replaceFirst(RegExp(r'^/+'), ''))) {
    return source;
  }

  final base = _relativeAvatarBase(gatewayBaseUrl, avatarCdnBaseUrl);
  if (base.isEmpty) {
    return source;
  }

  // beta/local-gamma 服务端早期配置可能把媒体 URL 写成 127.0.0.1:18088；
  // 对 iPad 来说这是设备本机，必须改写到 App 当前可访问的媒体/gateway base。
  final shouldRewriteLoopback = _isLoopbackHost(uri.host);
  final shouldRewriteHttpToHttps =
      uri.scheme.toLowerCase() == 'http' &&
      _normalizeBase(base).startsWith('https://');
  if (!shouldRewriteLoopback && !shouldRewriteHttpToHttps) {
    return source;
  }

  return _joinBaseAndPath(base, _uriPathWithQuery(uri));
}

String _relativeAvatarBase(String gatewayBaseUrl, String avatarCdnBaseUrl) {
  final gateway = _normalizeBase(gatewayBaseUrl);
  final cdn = _normalizeBase(avatarCdnBaseUrl);
  if (cdn.isNotEmpty && !_isLoopbackBase(cdn)) {
    return cdn;
  }
  if (gateway.isNotEmpty) {
    return gateway;
  }
  return cdn;
}

String _normalizeBase(String raw) {
  final value = raw.trim();
  if (value.isEmpty) {
    return '';
  }
  final lower = value.toLowerCase();
  if (!lower.startsWith('http://') && !lower.startsWith('https://')) {
    return '';
  }
  return value.replaceFirst(RegExp(r'/+$'), '');
}

String _joinBaseAndPath(String base, String path) {
  final cleanBase = base.replaceFirst(RegExp(r'/+$'), '');
  final cleanPath = path.startsWith('/') ? path : '/$path';
  return '$cleanBase$cleanPath';
}

bool _looksLikeMediaObjectKey(String source) {
  final lower = source.toLowerCase();
  return lower.startsWith('media/avatar/') ||
      lower.startsWith('avatar/') ||
      lower.startsWith('media/');
}

bool _looksLikeBareHostUrl(String source) {
  if (source.contains(' ') || source.contains('/media/')) {
    return false;
  }
  final firstSegment = source.split('/').first;
  return firstSegment.contains('.') && !firstSegment.startsWith('.');
}

bool _isLoopbackBase(String base) {
  final uri = Uri.tryParse(base);
  final host = uri?.host.toLowerCase() ?? '';
  return _isLoopbackHost(host);
}

bool _isLoopbackHost(String host) {
  return host == 'localhost' || host == '127.0.0.1' || host == '::1';
}

String _uriPathWithQuery(Uri uri) {
  final query = uri.hasQuery ? '?${uri.query}' : '';
  final fragment = uri.hasFragment ? '#${uri.fragment}' : '';
  final path = uri.path.isEmpty ? '/' : uri.path;
  return '$path$query$fragment';
}

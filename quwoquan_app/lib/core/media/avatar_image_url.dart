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
  final candidates = resolveAvatarImageUrlCandidates(
    raw,
    gatewayBaseUrl: gatewayBaseUrl,
    avatarCdnBaseUrl: avatarCdnBaseUrl,
  );
  return candidates.isEmpty ? '' : candidates.first;
}

/// 返回头像可访问 URL 候选集，供 UI 在首选媒体入口失败时继续尝试 gateway 代理。
List<String> resolveAvatarImageUrlCandidates(
  String? raw, {
  String? gatewayBaseUrl,
  String? avatarCdnBaseUrl,
}) {
  final source = raw?.trim() ?? '';
  if (source.isEmpty) {
    return const <String>[];
  }

  final gateway = gatewayBaseUrl ?? CloudRuntimeConfig.gatewayBaseUrl;
  final cdn = avatarCdnBaseUrl ?? CloudRuntimeConfig.mediaAvatarCdnBaseUrl;
  final lower = source.toLowerCase();
  if (lower.startsWith('data:image/')) {
    return <String>[source];
  }
  if (lower.startsWith('http://') || lower.startsWith('https://')) {
    return _resolveAbsoluteAvatarUrlCandidates(
      source,
      gatewayBaseUrl: gateway,
      avatarCdnBaseUrl: cdn,
    );
  }
  if (source.startsWith('//')) {
    return <String>['https:$source'];
  }
  if (_looksLikeBareHostUrl(source)) {
    return <String>['https://$source'];
  }

  final paths = <String>[];
  if (source.startsWith('/')) {
    paths.add(source);
  } else if (_looksLikeMediaObjectKey(source)) {
    paths.add('/$source');
  }
  if (paths.isEmpty) {
    return const <String>[];
  }

  return _mediaUrlCandidates(
    paths.first,
    gatewayBaseUrl: gateway,
    avatarCdnBaseUrl: cdn,
  );
}

List<String> _resolveAbsoluteAvatarUrlCandidates(
  String source, {
  required String gatewayBaseUrl,
  required String avatarCdnBaseUrl,
}) {
  final uri = Uri.tryParse(source);
  if (uri == null || !uri.hasScheme || uri.host.isEmpty) {
    return <String>[source];
  }
  final objectKey = uri.path.replaceFirst(RegExp(r'^/+'), '');
  if (!_looksLikeMediaObjectKey(objectKey)) {
    return <String>[source];
  }
  final path = _uriPathWithQuery(uri);
  final shouldRewriteHttpToHttps =
      uri.scheme.toLowerCase() == 'http' &&
      _normalizeBase(avatarCdnBaseUrl).startsWith('https://');

  final candidates = _mediaUrlCandidates(
    path,
    gatewayBaseUrl: gatewayBaseUrl,
    avatarCdnBaseUrl: avatarCdnBaseUrl,
  );
  if (_isLoopbackHost(uri.host) || shouldRewriteHttpToHttps) {
    return candidates.isEmpty ? <String>[source] : candidates;
  }
  return _uniqueNonEmpty(<String>[source, ...candidates]);
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

List<String> _mediaUrlCandidates(
  String path, {
  required String gatewayBaseUrl,
  required String avatarCdnBaseUrl,
}) {
  final cdn = _normalizeBase(avatarCdnBaseUrl);
  final gateway = _normalizeBase(gatewayBaseUrl);
  return _uniqueNonEmpty(<String>[
    if (cdn.isNotEmpty) _joinBaseAndPath(cdn, path),
    if (gateway.isNotEmpty) _joinBaseAndPath(gateway, path),
  ]);
}

List<String> _uniqueNonEmpty(Iterable<String> values) {
  final seen = <String>{};
  final result = <String>[];
  for (final value in values) {
    final normalized = value.trim();
    if (normalized.isEmpty || !seen.add(normalized)) {
      continue;
    }
    result.add(normalized);
  }
  return List<String>.unmodifiable(result);
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

bool _isLoopbackHost(String host) {
  return host == 'localhost' || host == '127.0.0.1' || host == '::1';
}

String _uriPathWithQuery(Uri uri) {
  final query = uri.hasQuery ? '?${uri.query}' : '';
  final fragment = uri.hasFragment ? '#${uri.fragment}' : '';
  final path = uri.path.isEmpty ? '/' : uri.path;
  return '$path$query$fragment';
}

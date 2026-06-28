import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';

const List<String> _archivedSeedAvatarFallbackPool = <String>[
  'media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png',
  'media/avatar/s/archived-avatar/user/fixture_user_friend/v1/avatar.png',
  'media/avatar/s/archived-avatar/user/fixture_user_photo/v1/avatar.png',
  'media/avatar/s/archived-avatar/user/fixture_user_travel/v1/avatar.png',
  'media/avatar/s/archived-avatar/user/fixture_user_article/v1/avatar.png',
];

/// 将服务端头像引用解析为可被 Flutter 图片组件加载的 URL。
///
/// beta/local-gamma 中头像字段可能是 `/media/avatar/...` 或
/// `media/avatar/...`。UI 组件不能直接把这类相对路径交给
/// `Image.network`，否则会落到文字占位。
String resolveAvatarImageUrl(
  String? raw, {
  String? gatewayBaseUrl,
  String? avatarCdnBaseUrl,
  int? avatarVersion,
}) {
  final candidates = resolveAvatarImageUrlCandidates(
    raw,
    gatewayBaseUrl: gatewayBaseUrl,
    avatarCdnBaseUrl: avatarCdnBaseUrl,
    avatarVersion: avatarVersion,
  );
  return candidates.isEmpty ? '' : candidates.first;
}

/// 返回头像可访问 URL 候选集，供 UI 在首选媒体入口失败时继续尝试 gateway 代理。
List<String> resolveAvatarImageUrlCandidates(
  String? raw, {
  String? gatewayBaseUrl,
  String? avatarCdnBaseUrl,
  int? avatarVersion,
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
      avatarVersion: avatarVersion,
    );
  }
  if (source.startsWith('//')) {
    return _resolveAbsoluteAvatarUrlCandidates(
      'https:$source',
      gatewayBaseUrl: gateway,
      avatarCdnBaseUrl: cdn,
      avatarVersion: avatarVersion,
    );
  }
  if (_looksLikeBareHostUrl(source)) {
    return _resolveAbsoluteAvatarUrlCandidates(
      'https://$source',
      gatewayBaseUrl: gateway,
      avatarCdnBaseUrl: cdn,
      avatarVersion: avatarVersion,
    );
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

  final normalizedPath = _rewriteArchivedSeedAvatarPath(paths.first);
  return _applyAvatarVersionToUrls(
    _mediaUrlCandidates(
      normalizedPath,
      gatewayBaseUrl: gateway,
      avatarCdnBaseUrl: cdn,
    ),
    avatarVersion,
  );
}

List<String> _resolveAbsoluteAvatarUrlCandidates(
  String source, {
  required String gatewayBaseUrl,
  required String avatarCdnBaseUrl,
  required int? avatarVersion,
}) {
  final uri = Uri.tryParse(source);
  if (uri == null || !uri.hasScheme || uri.host.isEmpty) {
    return _applyAvatarVersionToUrls(<String>[source], avatarVersion);
  }
  final objectKey = uri.path.replaceFirst(RegExp(r'^/+'), '');
  if (!_looksLikeMediaObjectKey(objectKey)) {
    return _applyAvatarVersionToUrls(
      _isTrustedRuntimeHost(
            uri,
            gatewayBaseUrl: gatewayBaseUrl,
            avatarCdnBaseUrl: avatarCdnBaseUrl,
          )
          ? <String>[source]
          : const <String>[],
      avatarVersion,
    );
  }
  final path = _uriPathWithQuery(uri);
  final normalizedPath = _rewriteArchivedSeedAvatarPath(path);
  if (normalizedPath != path) {
    return _applyAvatarVersionToUrls(
      _mediaUrlCandidates(
        normalizedPath,
        gatewayBaseUrl: gatewayBaseUrl,
        avatarCdnBaseUrl: avatarCdnBaseUrl,
      ),
      avatarVersion,
    );
  }
  final shouldRewriteHttpToHttps =
      uri.scheme.toLowerCase() == 'http' &&
      _normalizeBase(avatarCdnBaseUrl).startsWith('https://');

  final candidates = _applyAvatarVersionToUrls(
    _mediaUrlCandidates(
      normalizedPath,
      gatewayBaseUrl: gatewayBaseUrl,
      avatarCdnBaseUrl: avatarCdnBaseUrl,
    ),
    avatarVersion,
  );
  if (_isLoopbackHost(uri.host) || shouldRewriteHttpToHttps) {
    return candidates.isEmpty
        ? _applyAvatarVersionToUrls(<String>[source], avatarVersion)
        : candidates;
  }
  if (!_isTrustedRuntimeHost(
    uri,
    gatewayBaseUrl: gatewayBaseUrl,
    avatarCdnBaseUrl: avatarCdnBaseUrl,
  )) {
    return candidates;
  }
  return _applyAvatarVersionToUrls(<String>[
    source,
    ...candidates,
  ], avatarVersion);
}

String _normalizeBase(String raw) {
  final value = raw.trim();
  if (value.isEmpty) {
    return '';
  }
  final uri = Uri.tryParse(value);
  if (uri == null ||
      uri.host.isEmpty ||
      (uri.scheme != 'https' && uri.scheme != 'http')) {
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
    for (final base in _localEnvHostBaseCandidates(cdn))
      _joinBaseAndPath(base, path),
    for (final base in _localEnvHostBaseCandidates(gateway))
      _joinBaseAndPath(base, path),
  ]);
}

List<String> _localEnvHostBaseCandidates(String base) {
  final normalized = _normalizeBase(base);
  if (normalized.isEmpty) {
    return const <String>[];
  }
  final uri = Uri.tryParse(normalized);
  if (uri == null || !_isLocalEnvTestHost(uri.host)) {
    return <String>[normalized];
  }
  return _uniqueNonEmpty(<String>[
    uri.replace(host: 'localhost').toString().replaceFirst(RegExp(r'/+$'), ''),
    uri.replace(host: '127.0.0.1').toString().replaceFirst(RegExp(r'/+$'), ''),
    uri.replace(host: '10.0.2.2').toString().replaceFirst(RegExp(r'/+$'), ''),
    normalized,
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

List<String> _applyAvatarVersionToUrls(
  Iterable<String> values,
  int? avatarVersion,
) {
  if (avatarVersion == null || avatarVersion <= 0) {
    return _uniqueNonEmpty(values);
  }
  return _uniqueNonEmpty(
    values.map((value) => _replaceVersionQuery(value, avatarVersion)),
  );
}

String _replaceVersionQuery(String raw, int avatarVersion) {
  final value = raw.trim();
  final uri = Uri.tryParse(value);
  if (uri == null || !uri.hasScheme || uri.host.isEmpty) {
    return value;
  }
  final nextQuery = Map<String, String>.from(uri.queryParameters);
  nextQuery['v'] = avatarVersion.toString();
  return uri.replace(queryParameters: nextQuery).toString();
}

bool _looksLikeMediaObjectKey(String source) {
  final lower = source.toLowerCase();
  return lower.startsWith('media/avatar/') ||
      lower.startsWith('avatar/') ||
      lower.startsWith('media/') ||
      lower.startsWith('cold_start/');
}

String _rewriteArchivedSeedAvatarPath(String path) {
  final objectKey = path.replaceFirst(RegExp(r'^/+'), '');
  if (!_isArchivedSeedAvatarObjectKey(objectKey)) {
    return path;
  }
  final fallbackObjectKey =
      _archivedSeedAvatarFallbackPool[_stableMockAvatarIndex(objectKey)];
  return '/$fallbackObjectKey';
}

bool _isArchivedSeedAvatarObjectKey(String objectKey) {
  final lower = objectKey.toLowerCase();
  // 仅 mock 种子（s/mock/**）与畸形归档种子（archived-avatar/seed/**）需要回退到
  // 固定 fixture 头像；archived-avatar/user/** 是真实归档用户头像，必须原样保留
  // （仅换 CDN base），否则会把真实 user_<id> 头像错误替换成 fixture 头像。
  return lower.startsWith('media/avatar/s/mock/') ||
      lower.startsWith('media/avatar/s/archived-avatar/seed/');
}

int _stableMockAvatarIndex(String objectKey) {
  var hash = 0;
  for (final codeUnit in objectKey.codeUnits) {
    hash = (hash * 31 + codeUnit) & 0x7fffffff;
  }
  return hash % _archivedSeedAvatarFallbackPool.length;
}

bool _looksLikeBareHostUrl(String source) {
  if (source.contains(' ') || source.contains('/media/')) {
    return false;
  }
  final firstSegment = source.split('/').first;
  return firstSegment.contains('.') && !firstSegment.startsWith('.');
}

bool _isLoopbackHost(String host) {
  return host == 'localhost' ||
      host == '127.0.0.1' ||
      host == '::1' ||
      _isLocalEnvTestHost(host);
}

bool _isTrustedRuntimeHost(
  Uri uri, {
  required String gatewayBaseUrl,
  required String avatarCdnBaseUrl,
}) {
  final hosts = <String>{
    _hostFromBase(gatewayBaseUrl),
    _hostFromBase(avatarCdnBaseUrl),
  }..remove('');
  return hosts.contains(uri.host.toLowerCase());
}

String _hostFromBase(String raw) {
  final uri = Uri.tryParse(raw.trim());
  return uri?.host.toLowerCase() ?? '';
}

String _uriPathWithQuery(Uri uri) {
  final query = uri.hasQuery ? '?${uri.query}' : '';
  final fragment = uri.hasFragment ? '#${uri.fragment}' : '';
  final path = uri.path.isEmpty ? '/' : uri.path;
  return '$path$query$fragment';
}

bool _isLocalEnvTestHost(String host) =>
    host.toLowerCase().endsWith('.quwoquan-env.test');

import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';

const List<String> _archivedSeedImageFallbackPool = <String>[
  'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
  'media/image/s/archived-image/post/fixture_photo_002/v1/cover.png',
  'media/image/s/archived-image/post/fixture_photo_003/v1/cover.png',
  'media/image/s/archived-image/post/fixture_article_001/v1/cover.png',
  'media/image/s/archived-image/post/fixture_moment_001/v1/cover.png',
  'media/image/s/archived-image/post/fixture_video_001/v1/cover.png',
];

const List<String> _archivedSeedBackgroundFallbackPool = <String>[
  'media/background/s/archived-avatar/user/fixture_user_current/v1/background.png',
  'media/background/s/archived-avatar/user/fixture_user_friend/v1/background.png',
  'media/background/s/archived-avatar/user/fixture_user_photo/v1/background.png',
  'media/background/s/archived-avatar/user/fixture_user_travel/v1/background.png',
  'media/background/s/archived-avatar/user/fixture_user_article/v1/background.png',
];

const List<String> _archivedSeedVideoFallbackPool = <String>[
  'media/video/s/archived-video/beta-sample.mp4',
];

/// 将内容媒体引用解析成可直接加载的绝对 URL。
///
/// 契约 seed / 本地联调里经常返回 `media/image/...` 这类 object key。
/// 如果直接交给 `NetworkImage` / `CachedNetworkImage`，会触发
/// `No host specified in URI`。
String resolveContentMediaUrl(
  String? raw, {
  String? gatewayBaseUrl,
  String? imageCdnBaseUrl,
  String? videoCdnBaseUrl,
}) {
  final candidates = resolveContentMediaUrlCandidates(
    raw,
    gatewayBaseUrl: gatewayBaseUrl ?? CloudRuntimeConfig.gatewayBaseUrl,
    imageCdnBaseUrl: imageCdnBaseUrl ?? CloudRuntimeConfig.mediaImageCdnBaseUrl,
    videoCdnBaseUrl: videoCdnBaseUrl ?? CloudRuntimeConfig.mediaVideoCdnBaseUrl,
  );
  return candidates.isEmpty ? '' : candidates.first;
}

List<String> resolveContentMediaUrlCandidates(
  String? raw, {
  String? gatewayBaseUrl,
  String? imageCdnBaseUrl,
  String? videoCdnBaseUrl,
}) {
  final source = raw?.trim() ?? '';
  if (source.isEmpty) {
    return const <String>[];
  }

  final gateway = gatewayBaseUrl ?? CloudRuntimeConfig.gatewayBaseUrl;
  final imageCdn = imageCdnBaseUrl ?? CloudRuntimeConfig.mediaImageCdnBaseUrl;
  final videoCdn = videoCdnBaseUrl ?? CloudRuntimeConfig.mediaVideoCdnBaseUrl;

  final lower = source.toLowerCase();
  if (lower.startsWith('data:') ||
      lower.startsWith('asset://') ||
      lower.startsWith('file://')) {
    return <String>[source];
  }

  if (source.startsWith('//')) {
    return _resolveAbsoluteContentMediaUrlCandidates(
      'https:$source',
      gatewayBaseUrl: gateway,
      imageCdnBaseUrl: imageCdn,
      videoCdnBaseUrl: videoCdn,
    );
  }

  if (_looksLikeBareHostUrl(source)) {
    return _resolveAbsoluteContentMediaUrlCandidates(
      'https://$source',
      gatewayBaseUrl: gateway,
      imageCdnBaseUrl: imageCdn,
      videoCdnBaseUrl: videoCdn,
    );
  }

  if (lower.startsWith('http://') || lower.startsWith('https://')) {
    return _resolveAbsoluteContentMediaUrlCandidates(
      source,
      gatewayBaseUrl: gateway,
      imageCdnBaseUrl: imageCdn,
      videoCdnBaseUrl: videoCdn,
    );
  }

  if (!_looksLikeMediaObjectKey(source) && !source.startsWith('/')) {
    return <String>[source];
  }

  final normalizedPath = _rewriteArchivedSeedContentPath(
    source.startsWith('/') ? source : '/$source',
  );
  return _contentMediaUrlCandidatesForPath(
    normalizedPath,
    gatewayBaseUrl: gateway,
    imageCdnBaseUrl: imageCdn,
    videoCdnBaseUrl: videoCdn,
  );
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
  final cleanPath = path.startsWith('/') ? path : '/$path';
  return '$base$cleanPath';
}

List<String> _resolveAbsoluteContentMediaUrlCandidates(
  String source, {
  required String gatewayBaseUrl,
  required String imageCdnBaseUrl,
  required String videoCdnBaseUrl,
}) {
  final uri = Uri.tryParse(source);
  if (uri == null || !uri.hasScheme || uri.host.isEmpty) {
    return <String>[source];
  }
  final path = _uriPathWithQuery(uri);
  final normalizedPath = _rewriteArchivedSeedContentPath(path);
  if (normalizedPath != path) {
    return _contentMediaUrlCandidatesForPath(
      normalizedPath,
      gatewayBaseUrl: gatewayBaseUrl,
      imageCdnBaseUrl: imageCdnBaseUrl,
      videoCdnBaseUrl: videoCdnBaseUrl,
    );
  }
  final objectKey = uri.path.replaceFirst(RegExp(r'^/+'), '');
  if (!_looksLikeMediaObjectKey(objectKey)) {
    return _isTrustedRuntimeHost(
          uri,
          gatewayBaseUrl: gatewayBaseUrl,
          imageCdnBaseUrl: imageCdnBaseUrl,
          videoCdnBaseUrl: videoCdnBaseUrl,
        )
        ? <String>[source]
        : const <String>[];
  }

  final candidates = _contentMediaUrlCandidatesForPath(
    normalizedPath,
    gatewayBaseUrl: gatewayBaseUrl,
    imageCdnBaseUrl: imageCdnBaseUrl,
    videoCdnBaseUrl: videoCdnBaseUrl,
  );
  if (_isPrivateDevHost(uri.host) ||
      _shouldRewriteHttpToHttps(
        uri,
        path,
        imageCdnBaseUrl: imageCdnBaseUrl,
        videoCdnBaseUrl: videoCdnBaseUrl,
      )) {
    return candidates.isEmpty ? <String>[source] : candidates;
  }
  if (!_isTrustedRuntimeHost(
    uri,
    gatewayBaseUrl: gatewayBaseUrl,
    imageCdnBaseUrl: imageCdnBaseUrl,
    videoCdnBaseUrl: videoCdnBaseUrl,
  )) {
    return candidates;
  }
  return _uniqueNonEmpty(<String>[source, ...candidates]);
}

List<String> _contentMediaUrlCandidatesForPath(
  String path, {
  required String gatewayBaseUrl,
  required String imageCdnBaseUrl,
  required String videoCdnBaseUrl,
}) {
  final orderedBases = _orderedBasesForPath(
    path,
    gatewayBaseUrl: gatewayBaseUrl,
    imageCdnBaseUrl: imageCdnBaseUrl,
    videoCdnBaseUrl: videoCdnBaseUrl,
  );
  return _uniqueNonEmpty(
    orderedBases.map((base) => _joinBaseAndPath(base, path)),
  );
}

List<String> _orderedBasesForPath(
  String path, {
  required String gatewayBaseUrl,
  required String imageCdnBaseUrl,
  required String videoCdnBaseUrl,
}) {
  final gateway = _normalizeBase(gatewayBaseUrl);
  final preferredCdn = _preferredBaseForPath(
    path,
    imageCdnBaseUrl: imageCdnBaseUrl,
    videoCdnBaseUrl: videoCdnBaseUrl,
  );
  return _uniqueNonEmpty(<String>[
    ..._localHostBaseCandidates(preferredCdn),
    ..._localHostBaseCandidates(gateway),
  ]);
}

String _preferredBaseForPath(
  String path, {
  required String imageCdnBaseUrl,
  required String videoCdnBaseUrl,
}) {
  final lower = path.toLowerCase();
  if (lower.startsWith('/media/video/') || lower.startsWith('/video/')) {
    return _normalizeBase(videoCdnBaseUrl);
  }
  return _normalizeBase(imageCdnBaseUrl);
}

bool _shouldRewriteHttpToHttps(
  Uri uri,
  String path, {
  required String imageCdnBaseUrl,
  required String videoCdnBaseUrl,
}) {
  if (uri.scheme.toLowerCase() != 'http') {
    return false;
  }
  final preferredBase = _preferredBaseForPath(
    path,
    imageCdnBaseUrl: imageCdnBaseUrl,
    videoCdnBaseUrl: videoCdnBaseUrl,
  );
  return preferredBase.startsWith('https://');
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
  final normalized = source.replaceFirst(RegExp(r'^/+'), '').toLowerCase();
  return normalized.startsWith('media/image/') ||
      normalized.startsWith('media/video/') ||
      normalized.startsWith('media/background/') ||
      normalized.startsWith('image/') ||
      normalized.startsWith('video/') ||
      normalized.startsWith('media/');
}

String _rewriteArchivedSeedContentPath(String path) {
  final objectKey = path.replaceFirst(RegExp(r'^/+'), '');
  final lower = objectKey.toLowerCase();
  if (lower.startsWith('media/image/s/mock/') ||
      lower.startsWith('media/image/s/archived-image/seed/')) {
    final fallbackObjectKey =
        _archivedSeedImageFallbackPool[_stableArchivedSeedMediaIndex(
          objectKey,
        )];
    return '/$fallbackObjectKey';
  }
  if (lower.startsWith('media/background/s/mock/') ||
      lower.startsWith('media/background/s/archived-avatar/seed/') ||
      lower.startsWith('media/background/s/archived-avatar/user/user_')) {
    final fallbackObjectKey =
        _archivedSeedBackgroundFallbackPool[_stableArchivedSeedMediaIndex(
          objectKey,
        )];
    return '/$fallbackObjectKey';
  }
  if (lower.startsWith('media/video/s/mock/') ||
      lower.startsWith('media/video/s/archived-video/seed/')) {
    final fallbackObjectKey =
        _archivedSeedVideoFallbackPool[_stableArchivedSeedMediaIndex(
          objectKey,
        )];
    return '/$fallbackObjectKey';
  }
  return path;
}

int _stableArchivedSeedMediaIndex(String objectKey) {
  var hash = 0;
  for (final codeUnit in objectKey.codeUnits) {
    hash = (hash * 31 + codeUnit) & 0x7fffffff;
  }
  if (objectKey.toLowerCase().startsWith('media/video/')) {
    return hash % _archivedSeedVideoFallbackPool.length;
  }
  if (objectKey.toLowerCase().startsWith('media/background/')) {
    return hash % _archivedSeedBackgroundFallbackPool.length;
  }
  return hash % _archivedSeedImageFallbackPool.length;
}

bool _looksLikeBareHostUrl(String source) {
  if (source.contains(' ') || source.contains('/media/')) {
    return false;
  }
  final firstSegment = source.split('/').first;
  return firstSegment.contains('.') && !firstSegment.startsWith('.');
}

bool _isPrivateDevHost(String host) {
  final lower = host.toLowerCase();
  return lower == 'localhost' ||
      lower == '127.0.0.1' ||
      lower == '::1' ||
      lower == '10.0.2.2' ||
      lower.startsWith('192.168.');
}

List<String> _localHostBaseCandidates(String base) {
  final normalized = _normalizeBase(base);
  if (normalized.isEmpty) {
    return const <String>[];
  }
  final uri = Uri.tryParse(normalized);
  if (uri == null || !_isPrivateDevHost(uri.host)) {
    return <String>[normalized];
  }
  return _uniqueNonEmpty(<String>[
    normalized,
    for (final host in const <String>['127.0.0.1', 'localhost', '10.0.2.2'])
      uri.replace(host: host).toString().replaceFirst(RegExp(r'/+$'), ''),
  ]);
}

bool _isTrustedRuntimeHost(
  Uri uri, {
  required String gatewayBaseUrl,
  required String imageCdnBaseUrl,
  required String videoCdnBaseUrl,
}) {
  final hosts = <String>{
    _hostFromBase(gatewayBaseUrl),
    _hostFromBase(imageCdnBaseUrl),
    _hostFromBase(videoCdnBaseUrl),
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

/// 是否为本地文件图片来源（相册 / 拍照选取的临时文件）。
///
/// 用于在「本地选图预览 / 刚保存未上传」与「服务端媒体对象键 / 远端 URL」之间
/// 区分：服务端对象键（`media/...`、`avatar/...`、`/media/...`）与 http(s)/data
/// 均不是本地文件，需经媒体解析器换成可访问 URL；其余以 `file://` 或文件系统
/// 绝对路径出现的来源视为本地文件，可直接交给 `FileImage` 渲染。
bool isLocalFileImageSource(String? source) {
  final normalized = (source ?? '').trim();
  if (normalized.isEmpty) {
    return false;
  }
  final lower = normalized.toLowerCase();
  if (lower.startsWith('http://') ||
      lower.startsWith('https://') ||
      lower.startsWith('data:')) {
    return false;
  }
  if (lower.startsWith('file://')) {
    return true;
  }
  if (lower.startsWith('media/') ||
      lower.startsWith('/media/') ||
      lower.startsWith('avatar/') ||
      lower.startsWith('image/') ||
      lower.startsWith('video/')) {
    return false;
  }
  return normalized.startsWith('/');
}

bool isPrivateDevContentMediaUrl(String raw) {
  final value = raw.trim();
  if (value.isEmpty) {
    return false;
  }
  final uri = Uri.tryParse(value);
  if (uri == null || uri.host.isEmpty) {
    return false;
  }
  return _isPrivateDevHost(uri.host);
}

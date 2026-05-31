import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';

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
    imageCdnBaseUrl:
        imageCdnBaseUrl ?? CloudRuntimeConfig.mediaImageCdnBaseUrl,
    videoCdnBaseUrl:
        videoCdnBaseUrl ?? CloudRuntimeConfig.mediaVideoCdnBaseUrl,
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
    return <String>['https:$source'];
  }

  if (_looksLikeBareHostUrl(source)) {
    return <String>['https://$source'];
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

  final normalizedPath = source.startsWith('/') ? source : '/$source';
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
  final lower = value.toLowerCase();
  if (!lower.startsWith('http://') && !lower.startsWith('https://')) {
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
  final objectKey = uri.path.replaceFirst(RegExp(r'^/+'), '');
  if (!_looksLikeMediaObjectKey(objectKey)) {
    return <String>[source];
  }

  final candidates = _contentMediaUrlCandidatesForPath(
    path,
    gatewayBaseUrl: gatewayBaseUrl,
    imageCdnBaseUrl: imageCdnBaseUrl,
    videoCdnBaseUrl: videoCdnBaseUrl,
  );
  if (_isPrivateDevHost(uri.host) || _shouldRewriteHttpToHttps(uri, path,
      imageCdnBaseUrl: imageCdnBaseUrl, videoCdnBaseUrl: videoCdnBaseUrl)) {
    return candidates.isEmpty ? <String>[source] : candidates;
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
  return _uniqueNonEmpty(<String>[preferredCdn, gateway]);
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
      normalized.startsWith('image/') ||
      normalized.startsWith('video/') ||
      normalized.startsWith('media/');
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

String _uriPathWithQuery(Uri uri) {
  final query = uri.hasQuery ? '?${uri.query}' : '';
  final fragment = uri.hasFragment ? '#${uri.fragment}' : '';
  final path = uri.path.isEmpty ? '/' : uri.path;
  return '$path$query$fragment';
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

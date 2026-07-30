import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';

/// 媒体公开交付的业务种类。种类由上游 typed projection 声明，解析器不从路径或扩展名猜测。
enum MediaDeliveryKind { avatar, image, video, background, attachment }

/// 环境包注入的媒体端点。该对象不携带环境名；环境差异只体现在注入的 authority。
@immutable
class MediaEndpointConfig {
  MediaEndpointConfig({
    required String avatarBaseUrl,
    required String imageBaseUrl,
    required String videoBaseUrl,
    required String attachmentBaseUrl,
  }) : _bases = _availableBases(
         avatarBaseUrl: avatarBaseUrl,
         imageBaseUrl: imageBaseUrl,
         videoBaseUrl: videoBaseUrl,
         attachmentBaseUrl: attachmentBaseUrl,
         requireAll: true,
       );

  const MediaEndpointConfig._(this._bases);

  factory MediaEndpointConfig.fromRuntimeConfig() {
    return MediaEndpointConfig(
      avatarBaseUrl: CloudRuntimeConfig.mediaAvatarCdnBaseUrl,
      imageBaseUrl: CloudRuntimeConfig.mediaImageCdnBaseUrl,
      videoBaseUrl: CloudRuntimeConfig.mediaVideoCdnBaseUrl,
      attachmentBaseUrl: CloudRuntimeConfig.mediaImageCdnBaseUrl,
    );
  }

  /// Creates the resolver view available to a non-launched UI.
  ///
  /// It never invents an authority: missing endpoints remain unavailable and
  /// resolve to no public URL. The normal constructor remains the only full
  /// runtime-package constructor.
  static MediaEndpointConfig? tryCreateAvailable({
    required String avatarBaseUrl,
    required String imageBaseUrl,
    required String videoBaseUrl,
    required String attachmentBaseUrl,
  }) {
    try {
      return MediaEndpointConfig._(
        _availableBases(
          avatarBaseUrl: avatarBaseUrl,
          imageBaseUrl: imageBaseUrl,
          videoBaseUrl: videoBaseUrl,
          attachmentBaseUrl: attachmentBaseUrl,
        ),
      );
    } on ArgumentError {
      return null;
    }
  }

  final Map<MediaDeliveryKind, Uri> _bases;

  Uri baseFor(MediaDeliveryKind kind) {
    final base = _bases[kind];
    if (base == null) {
      throw MediaDeliveryResolutionException(
        MediaDeliveryResolutionFailure.endpointUnavailable,
        '未注入 ${kind.name} 媒体交付端点',
      );
    }
    if (kind == MediaDeliveryKind.background ||
        kind == MediaDeliveryKind.attachment) {
      return base.replace(path: '');
    }
    return base;
  }

  bool allowsOrigin(MediaDeliveryKind kind, Uri candidate) {
    final base = _bases[kind];
    if (base == null || !_sameOrigin(base, candidate)) {
      return false;
    }
    if (kind == MediaDeliveryKind.background ||
        kind == MediaDeliveryKind.attachment) {
      return true;
    }
    return _pathHasPrefix(candidate.pathSegments, base.pathSegments);
  }

  static Map<MediaDeliveryKind, Uri> _availableBases({
    required String avatarBaseUrl,
    required String imageBaseUrl,
    required String videoBaseUrl,
    required String attachmentBaseUrl,
    bool requireAll = false,
  }) {
    final declared = <MediaDeliveryKind, String>{
      MediaDeliveryKind.avatar: avatarBaseUrl,
      MediaDeliveryKind.image: imageBaseUrl,
      MediaDeliveryKind.video: videoBaseUrl,
      MediaDeliveryKind.attachment: attachmentBaseUrl,
    };
    if (requireAll && declared.values.any((value) => value.trim().isEmpty)) {
      throw ArgumentError('完整运行时媒体端点不可为空');
    }
    final bases = <MediaDeliveryKind, Uri>{};
    for (final entry in declared.entries) {
      if (entry.value.trim().isEmpty) {
        continue;
      }
      bases[entry.key] = _parseHttpsBase(
        entry.value,
        '${entry.key.name}BaseUrl',
      );
    }
    final imageBase = bases[MediaDeliveryKind.image];
    if (imageBase != null) {
      bases[MediaDeliveryKind.background] = imageBase;
    }
    return Map<MediaDeliveryKind, Uri>.unmodifiable(bases);
  }

  static Uri _parseHttpsBase(String raw, String name) {
    final uri = Uri.tryParse(raw.trim());
    if (uri == null ||
        uri.scheme.toLowerCase() != 'https' ||
        uri.host.isEmpty ||
        uri.hasQuery ||
        uri.hasFragment) {
      throw ArgumentError.value(
        raw,
        name,
        '媒体端点必须是无 query/fragment 的 HTTPS absolute URI',
      );
    }
    return uri.replace(path: uri.path.replaceFirst(RegExp(r'/+$'), ''));
  }
}

/// Production and tests consume one typed media-endpoint source.
///
/// Environment packages inject the compile-time values through
/// [CloudRuntimeConfig]. Missing values stay unavailable; callers must render
/// their declared recovery/fallback state instead of inventing an authority.
final mediaEndpointConfigProvider = Provider<MediaEndpointConfig?>((ref) {
  return MediaEndpointConfig.tryCreateAvailable(
    avatarBaseUrl: CloudRuntimeConfig.mediaAvatarCdnBaseUrl,
    imageBaseUrl: CloudRuntimeConfig.mediaImageCdnBaseUrl,
    videoBaseUrl: CloudRuntimeConfig.mediaVideoCdnBaseUrl,
    attachmentBaseUrl: CloudRuntimeConfig.mediaImageCdnBaseUrl,
  );
});

/// 已验证的公开媒体交付引用。
///
/// UI、缓存和网络播放器只能消费此类型；内部 CAS key / upload object key 不能构造本类型。
@immutable
class MediaDeliveryReference {
  const MediaDeliveryReference._({
    required this.kind,
    required this.deliveryUri,
    this.assetId = '',
    this.version = 0,
    this.sha256,
  });

  final MediaDeliveryKind kind;
  final Uri deliveryUri;
  final String assetId;
  final int version;
  final String? sha256;

  String get url => deliveryUri.toString();

  /// 与环境端点、公开 pathname 和版本绑定，禁止以原始 object key 作为缓存身份。
  String get cacheIdentity {
    final query = deliveryUri.hasQuery ? '?${deliveryUri.query}' : '';
    return '${kind.name}|${deliveryUri.origin}${deliveryUri.path}$query|'
        '${assetId.trim()}|$version';
  }

  @override
  bool operator ==(Object other) {
    return other is MediaDeliveryReference &&
        other.cacheIdentity == cacheIdentity &&
        other.sha256 == sha256;
  }

  @override
  int get hashCode => Object.hash(cacheIdentity, sha256);
}

enum MediaDeliveryResolutionFailure {
  emptyReference,
  endpointUnavailable,
  unsupportedScheme,
  untrustedOrigin,
  invalidCanonicalPath,
  invalidCanonicalQuery,
}

class MediaDeliveryResolutionException implements Exception {
  const MediaDeliveryResolutionException(this.failure, this.message);

  final MediaDeliveryResolutionFailure failure;
  final String message;

  @override
  String toString() =>
      'MediaDeliveryResolutionException(${failure.name}: $message)';
}

/// 唯一的公开媒体 URL 构建边界。
///
/// 相对 public slice key 只会与注入端点组合；绝对 URI 必须已经属于对应端点。
/// 不存在 host 改写、环境分支、候选回退或按文件名替换资产的行为。
@immutable
class MediaDeliveryResolver {
  const MediaDeliveryResolver(this.endpointConfig);

  final MediaEndpointConfig endpointConfig;

  factory MediaDeliveryResolver.fromRuntimeConfig() {
    return MediaDeliveryResolver(MediaEndpointConfig.fromRuntimeConfig());
  }

  MediaDeliveryReference resolve(
    String rawReference, {
    required MediaDeliveryKind kind,
    String assetId = '',
    int version = 0,
    String? sha256,
  }) {
    final source = rawReference.trim();
    if (source.isEmpty) {
      throw const MediaDeliveryResolutionException(
        MediaDeliveryResolutionFailure.emptyReference,
        '媒体公开引用为空',
      );
    }
    if (_containsNonCanonicalPathSyntax(source)) {
      throw const MediaDeliveryResolutionException(
        MediaDeliveryResolutionFailure.invalidCanonicalPath,
        '媒体公开路径不是 canonical slice path',
      );
    }
    if (source.startsWith('//')) {
      throw const MediaDeliveryResolutionException(
        MediaDeliveryResolutionFailure.unsupportedScheme,
        '媒体交付 URI 必须显式声明 HTTPS scheme',
      );
    }

    final parsed = Uri.tryParse(source);
    if (parsed == null) {
      throw const MediaDeliveryResolutionException(
        MediaDeliveryResolutionFailure.invalidCanonicalPath,
        '媒体公开引用不是合法 URI',
      );
    }

    if (parsed.hasScheme) {
      if (parsed.scheme.toLowerCase() != 'https' || parsed.host.isEmpty) {
        throw const MediaDeliveryResolutionException(
          MediaDeliveryResolutionFailure.unsupportedScheme,
          '媒体交付 URI 必须是 HTTPS absolute URI',
        );
      }
      final segments = _validateCanonicalPath(parsed.path);
      final queryParameters = _validateCanonicalQuery(
        parsed,
        kind: kind,
        segments: segments,
      );
      final endpointKind = _effectiveEndpointKind(
        kind,
        segments,
        queryParameters,
      );
      if (!endpointConfig.allowsOrigin(endpointKind, parsed)) {
        throw MediaDeliveryResolutionException(
          MediaDeliveryResolutionFailure.untrustedOrigin,
          '媒体交付 origin 不属于注入的 ${endpointKind.name} 端点',
        );
      }
      final canonical = _canonicalizePublicUri(
        parsed,
        segments: segments,
        queryParameters: queryParameters,
        requestedVersion: version,
      );
      return MediaDeliveryReference._(
        kind: kind,
        deliveryUri: canonical.uri,
        assetId: assetId,
        version: canonical.version,
        sha256: sha256,
      );
    }

    if (parsed.hasAuthority || parsed.hasFragment) {
      throw const MediaDeliveryResolutionException(
        MediaDeliveryResolutionFailure.invalidCanonicalPath,
        '媒体公开路径不能包含 authority 或 fragment',
      );
    }
    final segments = _validateCanonicalPath(parsed.path);
    final queryParameters = _validateCanonicalQuery(
      parsed,
      kind: kind,
      segments: segments,
    );
    final endpointKind = _effectiveEndpointKind(
      kind,
      segments,
      queryParameters,
    );
    final base = endpointConfig.baseFor(endpointKind);
    final relativeSegments = _withoutExistingBasePrefix(
      segments,
      base.pathSegments,
    );
    final uri = base.replace(
      pathSegments: <String>[...base.pathSegments, ...relativeSegments],
      queryParameters: queryParameters.isEmpty ? null : queryParameters,
    );
    final canonical = _canonicalizePublicUri(
      uri,
      segments: segments,
      queryParameters: queryParameters,
      requestedVersion: version,
    );
    return MediaDeliveryReference._(
      kind: kind,
      deliveryUri: canonical.uri,
      assetId: assetId,
      version: canonical.version,
      sha256: sha256,
    );
  }

  MediaDeliveryReference? tryResolve(
    String? rawReference, {
    required MediaDeliveryKind kind,
    String assetId = '',
    int version = 0,
    String? sha256,
  }) {
    try {
      return resolve(
        rawReference ?? '',
        kind: kind,
        assetId: assetId,
        version: version,
        sha256: sha256,
      );
    } on MediaDeliveryResolutionException {
      return null;
    }
  }

  static List<String> _validateCanonicalPath(String rawPath) {
    final normalized = rawPath.trim().replaceFirst(RegExp(r'^/+'), '');
    if (normalized.isEmpty) {
      throw const MediaDeliveryResolutionException(
        MediaDeliveryResolutionFailure.invalidCanonicalPath,
        '媒体公开路径不能为空',
      );
    }
    final segments = normalized.split('/');
    if (segments.any(
      (segment) =>
          segment.isEmpty ||
          segment == '.' ||
          segment == '..' ||
          segment.contains('\\') ||
          !RegExp(r'^[A-Za-z0-9][A-Za-z0-9._-]*$').hasMatch(segment),
    )) {
      throw const MediaDeliveryResolutionException(
        MediaDeliveryResolutionFailure.invalidCanonicalPath,
        '媒体公开路径不是 canonical slice path',
      );
    }
    return List<String>.unmodifiable(segments);
  }

  static bool _containsNonCanonicalPathSyntax(String source) {
    final lowerSource = source.toLowerCase();
    return RegExp(r'(^|/)\.{1,2}(?=/|$)').hasMatch(source) ||
        lowerSource.contains('%2e') ||
        source.contains('\\');
  }

  static MediaDeliveryKind _effectiveEndpointKind(
    MediaDeliveryKind kind,
    List<String> segments,
    Map<String, String> queryParameters,
  ) {
    final expectedRoot = switch (kind) {
      MediaDeliveryKind.avatar => 'avatar',
      MediaDeliveryKind.image => 'image',
      MediaDeliveryKind.video => 'video',
      MediaDeliveryKind.background => 'background',
      MediaDeliveryKind.attachment => 'attachment',
    };
    if (segments.length >= 4 &&
        segments.first == 'media' &&
        segments[1] == expectedRoot &&
        segments[2] == 's') {
      return kind;
    }
    // A video service may expose a generated first-frame derivative under the
    // canonical video slice path. This is not a host fallback: the explicit
    // `variant=thumb` contract selects the same injected video authority while
    // preserving the caller's image presentation semantics.
    if (kind == MediaDeliveryKind.image &&
        segments.length >= 4 &&
        segments.first == 'media' &&
        segments[1] == 'video' &&
        segments[2] == 's' &&
        queryParameters['variant'] == 'thumb') {
      return MediaDeliveryKind.video;
    }
    throw MediaDeliveryResolutionException(
      MediaDeliveryResolutionFailure.invalidCanonicalPath,
      kind == MediaDeliveryKind.image
          ? 'image 类型必须使用 media/image/，或显式 video first-frame thumbnail slice'
          : '${kind.name} 类型必须使用 media/$expectedRoot/ 下的公开 slice key',
    );
  }

  static Map<String, String> _validateCanonicalQuery(
    Uri uri, {
    required MediaDeliveryKind kind,
    required List<String> segments,
  }) {
    const allowedKeys = <String>{'variant', 't'};
    final allParameters = uri.queryParametersAll;
    if (allParameters.keys.any((key) => !allowedKeys.contains(key)) ||
        allParameters.values.any((values) => values.length != 1)) {
      throw const MediaDeliveryResolutionException(
        MediaDeliveryResolutionFailure.invalidCanonicalQuery,
        '公开媒体引用不得携带版本信封、签名、授权或重复 query 参数',
      );
    }

    final isVideoThumbnail =
        kind == MediaDeliveryKind.image &&
        segments.length >= 4 &&
        segments.first == 'media' &&
        segments[1] == 'video' &&
        segments[2] == 's';
    final variant = uri.queryParameters['variant'];
    final frameTime = uri.queryParameters['t'];
    if (isVideoThumbnail) {
      final frameTimeMs = frameTime == null ? 0 : int.tryParse(frameTime);
      if (variant != 'thumb' ||
          frameTimeMs == null ||
          frameTimeMs < 0 ||
          frameTimeMs > 3600000) {
        throw const MediaDeliveryResolutionException(
          MediaDeliveryResolutionFailure.invalidCanonicalQuery,
          'video 首帧引用只允许 variant=thumb 和 0..3600000 毫秒的 t',
        );
      }
    } else if (variant != null || frameTime != null) {
      throw const MediaDeliveryResolutionException(
        MediaDeliveryResolutionFailure.invalidCanonicalQuery,
        '只有显式 video 首帧引用可携带 variant/t',
      );
    }

    final canonical = <String, String>{};
    if (variant != null) {
      canonical['variant'] = variant;
    }
    if (frameTime != null) {
      canonical['t'] = frameTime;
    }
    return canonical;
  }

  static ({Uri uri, int version}) _canonicalizePublicUri(
    Uri uri, {
    required List<String> segments,
    required Map<String, String> queryParameters,
    required int requestedVersion,
  }) {
    if (requestedVersion < 0) {
      throw const MediaDeliveryResolutionException(
        MediaDeliveryResolutionFailure.invalidCanonicalQuery,
        '媒体版本不得为负数',
      );
    }
    final pathVersions = segments
        .skip(3)
        .map((segment) => RegExp(r'^v([1-9][0-9]*)$').firstMatch(segment))
        .whereType<RegExpMatch>()
        .map((match) => int.parse(match.group(1)!))
        .toList(growable: false);
    if (pathVersions.length != 1) {
      throw const MediaDeliveryResolutionException(
        MediaDeliveryResolutionFailure.invalidCanonicalPath,
        '公开媒体路径必须且只能包含一个正整数版本段',
      );
    }
    final pathVersion = pathVersions.single;
    if (requestedVersion > 0 && requestedVersion != pathVersion) {
      throw const MediaDeliveryResolutionException(
        MediaDeliveryResolutionFailure.invalidCanonicalQuery,
        '请求版本与媒体路径版本不一致',
      );
    }
    return (
      uri: uri.replace(
        queryParameters: queryParameters.isEmpty ? null : queryParameters,
      ),
      version: pathVersion,
    );
  }
}

bool _sameOrigin(Uri left, Uri uri) {
  return left.scheme.toLowerCase() == uri.scheme.toLowerCase() &&
      left.host.toLowerCase() == uri.host.toLowerCase() &&
      _effectivePort(left) == _effectivePort(uri);
}

int _effectivePort(Uri uri) {
  if (uri.hasPort) {
    return uri.port;
  }
  return uri.scheme.toLowerCase() == 'https' ? 443 : 80;
}

bool _pathHasPrefix(List<String> path, List<String> prefix) {
  final normalizedPrefix = prefix
      .where((segment) => segment.isNotEmpty)
      .toList();
  if (normalizedPrefix.isEmpty) {
    return true;
  }
  if (path.length < normalizedPrefix.length) {
    return false;
  }
  for (var index = 0; index < normalizedPrefix.length; index++) {
    if (path[index] != normalizedPrefix[index]) {
      return false;
    }
  }
  return true;
}

List<String> _withoutExistingBasePrefix(
  List<String> path,
  List<String> prefix,
) {
  final normalizedPrefix = prefix
      .where((segment) => segment.isNotEmpty)
      .toList();
  if (!_pathHasPrefix(path, normalizedPrefix)) {
    return path;
  }
  return path.sublist(normalizedPrefix.length);
}

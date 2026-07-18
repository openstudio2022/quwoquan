import 'package:flutter/foundation.dart';
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
  }) : avatarBaseUri = _parseHttpsBase(avatarBaseUrl, 'avatarBaseUrl'),
       imageBaseUri = _parseHttpsBase(imageBaseUrl, 'imageBaseUrl'),
       videoBaseUri = _parseHttpsBase(videoBaseUrl, 'videoBaseUrl'),
       attachmentBaseUri = _parseHttpsBase(
         attachmentBaseUrl,
         'attachmentBaseUrl',
       );

  factory MediaEndpointConfig.fromRuntimeConfig() {
    return MediaEndpointConfig(
      avatarBaseUrl: CloudRuntimeConfig.mediaAvatarCdnBaseUrl,
      imageBaseUrl: CloudRuntimeConfig.mediaImageCdnBaseUrl,
      videoBaseUrl: CloudRuntimeConfig.mediaVideoCdnBaseUrl,
      attachmentBaseUrl: CloudRuntimeConfig.mediaImageCdnBaseUrl,
    );
  }

  final Uri avatarBaseUri;
  final Uri imageBaseUri;
  final Uri videoBaseUri;
  final Uri attachmentBaseUri;

  Uri baseFor(MediaDeliveryKind kind) {
    switch (kind) {
      case MediaDeliveryKind.avatar:
        return avatarBaseUri;
      case MediaDeliveryKind.image:
      case MediaDeliveryKind.background:
        return imageBaseUri;
      case MediaDeliveryKind.video:
        return videoBaseUri;
      case MediaDeliveryKind.attachment:
        return attachmentBaseUri;
    }
  }

  bool allowsOrigin(MediaDeliveryKind kind, Uri candidate) {
    return _sameOrigin(baseFor(kind), candidate);
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
  unsupportedScheme,
  untrustedOrigin,
  invalidCanonicalPath,
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
      final endpointKind = _effectiveEndpointKind(
        kind,
        segments,
        parsed.queryParameters,
      );
      if (!endpointConfig.allowsOrigin(endpointKind, parsed)) {
        throw MediaDeliveryResolutionException(
          MediaDeliveryResolutionFailure.untrustedOrigin,
          '媒体交付 origin 不属于注入的 ${endpointKind.name} 端点',
        );
      }
      return MediaDeliveryReference._(
        kind: kind,
        deliveryUri: _withVersion(parsed, version),
        assetId: assetId,
        version: version,
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
    final endpointKind = _effectiveEndpointKind(
      kind,
      segments,
      parsed.queryParameters,
    );
    final base = endpointConfig.baseFor(endpointKind);
    final uri = base.replace(
      pathSegments: <String>[...base.pathSegments, ...segments],
      queryParameters: parsed.queryParameters.isEmpty
          ? null
          : parsed.queryParameters,
    );
    return MediaDeliveryReference._(
      kind: kind,
      deliveryUri: _withVersion(uri, version),
      assetId: assetId,
      version: version,
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
    if (segments.length >= 2 &&
        segments.first == 'media' &&
        segments[1] == expectedRoot) {
      return kind;
    }
    // A video service may expose a generated first-frame derivative under the
    // canonical video slice path. This is not a host fallback: the explicit
    // `variant=thumb` contract selects the same injected video authority while
    // preserving the caller's image presentation semantics.
    if (kind == MediaDeliveryKind.image &&
        segments.length >= 2 &&
        segments.first == 'media' &&
        segments[1] == 'video' &&
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

  static Uri _withVersion(Uri uri, int version) {
    if (version <= 0) {
      return uri;
    }
    final query = Map<String, String>.from(uri.queryParameters)
      ..['v'] = version.toString();
    return uri.replace(queryParameters: query);
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

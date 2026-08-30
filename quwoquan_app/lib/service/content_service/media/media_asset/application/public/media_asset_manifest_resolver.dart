import 'package:quwoquan_app/service/content_service/media/media_asset/application/public/media_asset_url_resolver.dart';

typedef MediaAssetReferenceResolver = String Function(
  String raw, {
  String? gatewayBaseUrl,
  String? imageCdnBaseUrl,
  String? videoCdnBaseUrl,
});

enum MediaAssetVariantProfile {
  thumbnail,
  display,
  cover,
  full,
  original,
  adaptive,
}

class MediaAssetVariant {
  const MediaAssetVariant({
    required this.profile,
    required this.url,
    required this.publicSliceKey,
    required this.requiresAccess,
    this.sourceSha256 = '',
    this.mimeType = '',
    this.format = '',
    this.width,
    this.height,
    this.quality,
  });

  final String profile;
  final String url;
  final String publicSliceKey;
  final bool requiresAccess;
  final String sourceSha256;
  final String mimeType;
  final String format;
  final int? width;
  final int? height;
  final int? quality;

  bool get isDirectlyLoadable => url.isNotEmpty && !requiresAccess;
}

class MediaAssetVariants {
  const MediaAssetVariants({
    required this.assetId,
    required this.kind,
    required this.variants,
    this.accessMode = '',
    this.fallbackUrl = '',
    this.width,
    this.height,
  });

  final String assetId;
  final String kind;
  final Map<String, MediaAssetVariant> variants;

  /// 契约声明的交付访问模式（PostArticleAsset.accessMode，DEC-033）。
  /// 空串表示契约缺席（存量 public 交付）；消费面按 typed 绑定分流，
  /// 不从 URL 形态反推。
  final String accessMode;

  final String fallbackUrl;

  /// manifest 顶层资产行声明的像素宽高（PostArticleAsset.width/height，
  /// NULLABLE 契约字段）；缺席保持 null，不得塌陷为 0。
  final int? width;
  final int? height;

  /// 展示用途的像素宽高：优先 display variant 的实测尺寸，缺席回退顶层声明。
  int? get displayWidth => variants['display']?.width ?? width;
  int? get displayHeight => variants['display']?.height ?? height;

  String urlFor(MediaAssetVariantProfile profile) {
    final preferred = _profileName(profile);
    final variant = variants[preferred];
    if (variant != null && variant.isDirectlyLoadable) {
      return variant.url;
    }
    for (final fallbackProfile in _fallbackProfiles(profile)) {
      final fallback = variants[fallbackProfile];
      if (fallback != null && fallback.isDirectlyLoadable) {
        return fallback.url;
      }
    }
    return fallbackUrl;
  }
}

class MediaAssetManifestResolver implements MediaAssetUrlResolver {
  const MediaAssetManifestResolver({
    required this.resolveReference,
    this.gatewayBaseUrl,
    this.imageCdnBaseUrl,
    this.videoCdnBaseUrl,
  });

  final String? gatewayBaseUrl;
  final String? imageCdnBaseUrl;
  final String? videoCdnBaseUrl;
  final MediaAssetReferenceResolver resolveReference;

  @override
  Map<String, String> resolveManifestUrls(Map<String, Object?>? manifest) {
    final variantsById = resolveManifestVariants(manifest);
    if (variantsById.isNotEmpty) {
      return Map<String, String>.unmodifiable(
        variantsById.map(
          (assetId, variants) => MapEntry(
            assetId,
            variants.urlFor(MediaAssetVariantProfile.display),
          ),
        )..removeWhere((_, url) => url.isEmpty),
      );
    }
    final rawAssets = manifest?['assets'];
    if (rawAssets is! Iterable) {
      return const <String, String>{};
    }
    final out = <String, String>{};
    for (final raw in rawAssets) {
      if (raw is! Map) {
        continue;
      }
      final row = Map<String, Object?>.from(raw.cast<String, Object?>());
      final assetId = (row['assetId'] ?? '').toString().trim();
      if (assetId.isEmpty) {
        continue;
      }
      final url = resolveAssetRowUrl(row);
      if (url.isNotEmpty) {
        out[assetId] = url;
      }
    }
    return Map<String, String>.unmodifiable(out);
  }

  Map<String, MediaAssetVariants> resolveManifestVariants(
    Map<String, Object?>? manifest,
  ) {
    final rawAssets = manifest?['assets'];
    if (rawAssets is! Iterable) {
      return const <String, MediaAssetVariants>{};
    }
    final out = <String, MediaAssetVariants>{};
    for (final raw in rawAssets) {
      if (raw is! Map) {
        continue;
      }
      final row = Map<String, Object?>.from(raw.cast<String, Object?>());
      final assetId = (row['assetId'] ?? '').toString().trim();
      if (assetId.isEmpty) {
        continue;
      }
      final fallbackUrl = resolveAssetRowUrl(row);
      final variants = _resolveRowVariants(row);
      final width = _intValue(row['width']);
      final height = _intValue(row['height']);
      final accessMode = (row['accessMode'] ?? '').toString().trim();
      // 交付 URL 全缺席但声明了像素宽高的行仍需保留（REQ-017）：
      // 缺席态占位框比例由元数据派生，不得连同几何一起丢弃。
      // 私有交付的行同样必须保留：它本就没有公开 URL，按「无 URL 即丢弃」
      // 处理会让 research 相位的文章内嵌图整片消失。
      if (variants.isEmpty &&
          fallbackUrl.isEmpty &&
          accessMode.isEmpty &&
          (width == null || height == null)) {
        continue;
      }
      out[assetId] = MediaAssetVariants(
        assetId: assetId,
        kind: (row['kind'] ?? '').toString().trim(),
        variants: variants,
        accessMode: accessMode,
        fallbackUrl: fallbackUrl,
        width: width,
        height: height,
      );
    }
    return Map<String, MediaAssetVariants>.unmodifiable(out);
  }

  @override
  String resolveAssetRowUrl(Map<String, Object?> row) {
    return _firstResolvedContentMediaUrl(<Object?>[
      row['cdnUrl'],
      row['publicSliceKey'],
    ]);
  }

  String resolveAssetUrl(String assetId, Map<String, String> assetsById) {
    return assetsById[assetId.trim()] ?? '';
  }

  String resolveVariantUrl(
    String assetId,
    Map<String, MediaAssetVariants> assetsById, {
    MediaAssetVariantProfile profile = MediaAssetVariantProfile.display,
  }) {
    return assetsById[assetId.trim()]?.urlFor(profile) ?? '';
  }

  Map<String, MediaAssetVariant> _resolveRowVariants(Map<String, Object?> row) {
    final rawVariants = row['variants'];
    if (rawVariants is! Map) {
      return const <String, MediaAssetVariant>{};
    }
    final out = <String, MediaAssetVariant>{};
    for (final entry in rawVariants.entries) {
      final profile = entry.key.toString().trim();
      final raw = entry.value;
      if (profile.isEmpty || raw is! Map) {
        continue;
      }
      final variant = Map<String, Object?>.from(raw.cast<String, Object?>());
      final requiresAccess = variant['requiresAccess'] == true;
      final url = requiresAccess
          ? ''
          : _firstResolvedContentMediaUrl(<Object?>[
              variant['cdnUrl'],
              variant['publicSliceKey'],
            ]);
      out[profile] = MediaAssetVariant(
        profile: profile,
        url: url,
        publicSliceKey: (variant['publicSliceKey'] ?? '').toString().trim(),
        requiresAccess: requiresAccess,
        sourceSha256: (variant['sourceSha256'] ?? '').toString().trim(),
        mimeType: (variant['mimeType'] ?? '').toString().trim(),
        format: (variant['format'] ?? '').toString().trim(),
        width: _intValue(variant['width']),
        height: _intValue(variant['height']),
        quality: _intValue(variant['quality']),
      );
    }
    return Map<String, MediaAssetVariant>.unmodifiable(out);
  }

  String _firstResolvedContentMediaUrl(Iterable<Object?> rawValues) {
    for (final raw in rawValues) {
      final candidate = raw?.toString().trim() ?? '';
      if (candidate.isEmpty) {
        continue;
      }
      final resolved = resolveReference(
        candidate,
        gatewayBaseUrl: gatewayBaseUrl,
        imageCdnBaseUrl: imageCdnBaseUrl,
        videoCdnBaseUrl: videoCdnBaseUrl,
      );
      if (resolved.isNotEmpty) {
        return resolved;
      }
    }
    return '';
  }
}

String _profileName(MediaAssetVariantProfile profile) {
  switch (profile) {
    case MediaAssetVariantProfile.thumbnail:
      return 'thumbnail';
    case MediaAssetVariantProfile.display:
      return 'display';
    case MediaAssetVariantProfile.cover:
      return 'cover';
    case MediaAssetVariantProfile.full:
      return 'full';
    case MediaAssetVariantProfile.original:
      return 'original';
    case MediaAssetVariantProfile.adaptive:
      return 'adaptive';
  }
}

List<String> _fallbackProfiles(MediaAssetVariantProfile profile) {
  switch (profile) {
    case MediaAssetVariantProfile.thumbnail:
      return const <String>['cover', 'display', 'full'];
    case MediaAssetVariantProfile.cover:
      return const <String>['display', 'thumbnail', 'full'];
    case MediaAssetVariantProfile.full:
      return const <String>['display', 'cover', 'thumbnail'];
    case MediaAssetVariantProfile.original:
      return const <String>['full', 'display'];
    case MediaAssetVariantProfile.adaptive:
      return const <String>['display', 'full'];
    case MediaAssetVariantProfile.display:
      return const <String>['cover', 'thumbnail', 'full', 'adaptive'];
  }
}

int? _intValue(Object? value) {
  if (value is int) {
    return value;
  }
  if (value is num) {
    return value.toInt();
  }
  return int.tryParse(value?.toString() ?? '');
}

import 'dart:async';

import 'package:quwoquan_app/runtime/transport/media/media_delivery_binding.dart';
import 'package:quwoquan_app/runtime/di/signed_media_delivery_dependencies.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/domain/signed_media_delivery_lease.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart'
    show mediaDownloadCacheProvider;
import 'package:quwoquan_app/runtime/observability/app_exception_telemetry_service.dart';
import 'package:flutter/painting.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:video_player/video_player.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/platform/media/app_image_cache_controller.dart';
import 'package:quwoquan_app/runtime/platform/media/public_media_delivery_port.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/design_system/media/cdn_image_url_port.dart';
import 'package:quwoquan_app/runtime/di/content_image_delivery_dependencies.dart';
import 'package:quwoquan_app/runtime/di/cloud_http_client_provider.dart';
export 'package:quwoquan_app/runtime/platform/media/public_media_delivery_port.dart';

/// 仅启动组合根安装；公共在线依赖闭包不引用 Alpha 实现。
void installPublicMediaDelivery(PublicMediaDeliveryPort delivery) {
  _selected = delivery;
  _identity = CloudRuntimeConfig.runtimeConfigPackageDigest;
}

PublicMediaDeliveryPort get publicMediaDelivery {
  final identity = CloudRuntimeConfig.runtimeConfigPackageDigest;
  if (_selected == null || _identity != identity) {
    _selected = RemotePublicMediaDelivery(
      MediaEndpointConfig.tryCreateAvailable(
        avatarBaseUrl: CloudRuntimeConfig.mediaAvatarCdnBaseUrl,
        imageBaseUrl: CloudRuntimeConfig.mediaImageCdnBaseUrl,
        videoBaseUrl: CloudRuntimeConfig.mediaVideoCdnBaseUrl,
        attachmentBaseUrl: CloudRuntimeConfig.mediaImageCdnBaseUrl,
      ),
    );
    _identity = identity;
  }
  return _selected!;
}

String? _identity;
PublicMediaDeliveryPort? _selected;

final publicMediaDeliveryProvider = Provider<PublicMediaDeliveryPort>((ref) {
  final endpoints = ref.watch(mediaEndpointConfigProvider);
  return endpoints == null
      ? publicMediaDelivery
      : RemotePublicMediaDelivery(
          endpoints,
          httpClient: () => ref.read(unauthenticatedCloudHttpClientProvider),
          imageProfiles: ref.watch(cdnImageUrlPortProvider),
          cachedVideoPath: (url) =>
              ref.read(mediaDownloadCacheProvider).getCachedFilePath(url),
          signedMedia: (binding, kind, refresh) {
            final coordinator = ref.read(
              signedMediaDeliveryCoordinatorProvider,
            );
            return refresh
                ? coordinator.refresh(assetId: binding.assetId, kind: kind)
                : coordinator.resolve(
                    assetId: binding.assetId,
                    kind: kind,
                    accessMode: binding.accessMode!,
                  );
          },
        );
});

/// Beta/Gamma/Prod 共用此实现，配置不携带业务分支。
final class RemotePublicMediaDelivery implements PublicMediaDeliveryPort {
  const RemotePublicMediaDelivery(
    this.endpoints, {
    this.httpClient,
    this.cachedVideoPath,
    this.signedMedia,
    this.imageProfiles = contentImageProfiles,
  });
  final CdnImageUrlPort imageProfiles;
  final CloudHttpClient Function()? httpClient;
  final Future<String?> Function(String)? cachedVideoPath;
  final Future<SignedMediaDeliveryLease> Function(
    MediaDeliveryBinding,
    MediaDeliveryKind,
    bool,
  )?
  signedMedia;

  @override
  Future<SignedMediaDeliveryLease> acquireLease(
    String reference, {
    required MediaDeliveryBinding binding,
    required MediaDeliveryKind kind,
    bool refresh = false,
  }) async {
    if (!binding.isSignedGrant ||
        binding.isUnsupportedPrivateHls ||
        reference != binding.publicUrl ||
        signedMedia == null) {
      throw const FormatException('private media binding invalid');
    }
    return signedMedia!(binding, kind, refresh);
  }

  @override
  Future<ImageProvider<Object>> acquireImage(
    String reference, {
    required MediaDeliveryBinding binding,
    CdnImagePreset profile = CdnImagePreset.none,
    bool refresh = false,
  }) async {
    if (binding.isContractFailure ||
        binding.isSignedGrantWithoutAsset ||
        binding.isUnsupportedPrivateHls) {
      throw const FormatException('media access binding invalid');
    }
    if (binding.isSignedGrant) {
      final lease = await acquireLease(
        reference,
        binding: binding,
        kind: MediaDeliveryKind.image,
        refresh: refresh,
      );
      return imageProvider(
        lease.deliveryUri.toString(),
        profile: profile,
        cacheKey: lease.cacheIdentity,
        lease: lease,
      );
    }
    if (!binding.isPublic) throw const FormatException('media content absent');
    return imageProvider(reference, profile: profile);
  }

  @override
  final MediaEndpointConfig? endpoints;
  @override
  MediaDeliveryReference? tryResolve(
    String? reference, {
    required MediaDeliveryKind kind,
    String assetId = '',
    int version = 0,
    String? sha256,
  }) => endpoints == null
      ? null
      : MediaDeliveryResolver(endpoints!).tryResolve(
          reference,
          kind: kind,
          assetId: assetId,
          version: version,
          sha256: sha256,
        );

  @override
  List<String> candidates(
    String reference,
    MediaDeliveryKind kind, {
    int version = 0,
  }) {
    final resolved = tryResolve(reference, kind: kind, version: version);
    return resolved == null ? const [] : [resolved.url];
  }

  @override
  ImageProvider<Object> imageProvider(
    String reference, {
    CdnImagePreset profile = CdnImagePreset.none,
    MediaDeliveryKind kind = MediaDeliveryKind.image,
    String? cacheKey,
    SignedMediaDeliveryLease? lease,
  }) {
    lease?.validateFor(reference, kind);
    // 旧通用图片宿主不拥有媒体路由；canonical 分类只在获取边界执行。
    final segments = Uri.tryParse(reference)?.pathSegments ?? const <String>[];
    final effectiveKind =
        kind == MediaDeliveryKind.image &&
            segments.length > 1 &&
            segments.first == 'media'
        ? switch (segments[1]) {
            'avatar' => MediaDeliveryKind.avatar,
            'background' => MediaDeliveryKind.background,
            'attachment' => MediaDeliveryKind.attachment,
            _ => kind,
          }
        : kind;
    final resolved = lease != null
        ? reference
        : tryResolve(
            reference,
            kind: profile == CdnImagePreset.avatar
                ? MediaDeliveryKind.avatar
                : effectiveKind,
          )?.url;
    if (resolved == null) {
      throw const FormatException('media image reference invalid');
    }
    final url = lease != null
        ? resolved
        : switch (profile) {
            CdnImagePreset.avatar => imageProfiles.avatar(resolved, size: 120),
            CdnImagePreset.thumbnail => imageProfiles.thumbnail(resolved),
            CdnImagePreset.cover => imageProfiles.cover(resolved),
            CdnImagePreset.inline => imageProfiles.display(resolved),
            CdnImagePreset.full => imageProfiles.full(resolved),
            CdnImagePreset.none => resolved,
          };
    return CachedNetworkImageProvider(
      url,
      cacheKey: lease?.cacheIdentity ?? cacheKey,
      cacheManager: AppImageCacheController.cacheManagerForPreset(profile),
    );
  }

  @override
  Future<List<PlayableVideoSource>> playableSources(
    String reference, {
    MediaDeliveryReference? binding,
    SignedMediaDeliveryLease? lease,
    VideoViewType? viewType,
  }) async {
    if (binding?.bundleDigest != null) {
      throw const FormatException('media video authority mismatch');
    }
    lease?.validateFor(reference, MediaDeliveryKind.video);
    if (binding != null && binding.sourceReference != reference) {
      throw const FormatException('media video input binding mismatch');
    }
    final uri =
        lease?.deliveryUri ??
        binding?.deliveryUri ??
        tryResolve(reference, kind: MediaDeliveryKind.video)?.deliveryUri;
    if (uri == null || uri.scheme != 'https' || uri.host.isEmpty) {
      throw const FormatException('media video reference invalid');
    }
    final adaptive = uri.path.toLowerCase().endsWith('.m3u8');
    final sources = <PlayableVideoSource>[];
    if (!adaptive && cachedVideoPath != null) {
      try {
        final path = await cachedVideoPath!(uri.toString());
        if (path != null) {
          sources.add(PlayableVideoSource.cachedFile(path, viewType: viewType));
        }
      } catch (error, stackTrace) {
        unawaited(
          AppExceptionTelemetryService.instance.recordHandledException(
            source: 'content.video_player.cached_source_lookup',
            error: error,
            stackTrace: stackTrace,
          ),
        );
      }
    }
    sources.add(
      PlayableVideoSource.network(
        uri,
        formatHint: adaptive ? VideoFormat.hls : null,
        viewType: viewType,
      ),
    );
    return sources;
  }

  @override
  Future<Map<String, dynamic>> loadJson(
    String reference, {
    required MediaDeliveryReference binding,
  }) async {
    if (reference != binding.sourceReference ||
        binding.bundleDigest != null ||
        httpClient == null) {
      throw const FormatException('media manifest authority unavailable');
    }
    final decoded = await httpClient!().getJson(
      binding.deliveryUri,
      headers: const {'Accept': 'application/json'},
    );
    if (decoded is! Map<String, dynamic>) {
      throw const FormatException('media manifest must be an object');
    }
    return decoded;
  }
}

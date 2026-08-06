import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';

/// 将服务端头像引用解析为可被 Flutter 图片组件加载的 URL。
///
/// 仅委托 [MediaDeliveryResolver]；不再生成 gateway/loopback 候选或路径回写。
String resolveAvatarImageUrl(
  String? raw, {
  String? gatewayBaseUrl,
  String? avatarCdnBaseUrl,
  int? avatarVersion,
  MediaEndpointConfig? endpointConfig,
}) {
  final candidates = resolveAvatarImageUrlCandidates(
    raw,
    gatewayBaseUrl: gatewayBaseUrl,
    avatarCdnBaseUrl: avatarCdnBaseUrl,
    avatarVersion: avatarVersion,
    endpointConfig: endpointConfig,
  );
  return candidates.isEmpty ? '' : candidates.first;
}

/// 返回唯一注入 avatar endpoint URL；不再扩展 localhost/gateway 候选。
List<String> resolveAvatarImageUrlCandidates(
  String? raw, {
  String? gatewayBaseUrl,
  String? avatarCdnBaseUrl,
  int? avatarVersion,
  MediaEndpointConfig? endpointConfig,
}) {
  final source = raw?.trim() ?? '';
  if (source.isEmpty) {
    return const <String>[];
  }
  final lower = source.toLowerCase();
  if (lower.startsWith('data:image/')) {
    return <String>[source];
  }

  final avatarBase =
      avatarCdnBaseUrl ?? CloudRuntimeConfig.mediaAvatarCdnBaseUrl;
  final endpoints =
      endpointConfig ??
      MediaEndpointConfig.tryCreateAvailable(
        avatarBaseUrl: avatarBase,
        imageBaseUrl: CloudRuntimeConfig.mediaImageCdnBaseUrl,
        videoBaseUrl: CloudRuntimeConfig.mediaVideoCdnBaseUrl,
        attachmentBaseUrl: CloudRuntimeConfig.mediaImageCdnBaseUrl,
      );
  if (endpoints == null) {
    return const <String>[];
  }
  final resolver = MediaDeliveryResolver(endpoints);
  final resolved = resolver.tryResolve(
    source,
    kind: MediaDeliveryKind.avatar,
    version: avatarVersion ?? 0,
  );
  if (resolved == null) {
    return const <String>[];
  }
  return <String>[resolved.url];
}

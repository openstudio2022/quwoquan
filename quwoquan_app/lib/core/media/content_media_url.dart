import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/core/media/media_delivery_reference.dart';

/// 将内容媒体引用解析成可直接加载的绝对 URL。
///
/// 仅委托 [MediaDeliveryResolver]；不再做 host 改写、候选回退或路径特判。
String resolveContentMediaUrl(
  String? raw, {
  String? gatewayBaseUrl,
  String? imageCdnBaseUrl,
  String? videoCdnBaseUrl,
}) {
  final candidates = resolveContentMediaUrlCandidates(
    raw,
    gatewayBaseUrl: gatewayBaseUrl,
    imageCdnBaseUrl: imageCdnBaseUrl,
    videoCdnBaseUrl: videoCdnBaseUrl,
  );
  return candidates.isEmpty ? '' : candidates.first;
}

String resolveContentVideoUrl(
  String? raw, {
  String? gatewayBaseUrl,
  String? imageCdnBaseUrl,
  String? videoCdnBaseUrl,
}) {
  final candidates = resolveContentVideoUrlCandidates(
    raw,
    gatewayBaseUrl: gatewayBaseUrl,
    imageCdnBaseUrl: imageCdnBaseUrl,
    videoCdnBaseUrl: videoCdnBaseUrl,
  );
  return candidates.isEmpty ? '' : candidates.first;
}

List<String> resolveContentMediaUrlCandidates(
  String? raw, {
  String? gatewayBaseUrl,
  String? imageCdnBaseUrl,
  String? videoCdnBaseUrl,
}) {
  return _resolveMediaReference(
    raw,
    kind: _inferNonVideoKind(raw),
    imageCdnBaseUrl: imageCdnBaseUrl,
    videoCdnBaseUrl: videoCdnBaseUrl,
  );
}

List<String> resolveContentVideoUrlCandidates(
  String? raw, {
  String? gatewayBaseUrl,
  String? imageCdnBaseUrl,
  String? videoCdnBaseUrl,
}) {
  return _resolveMediaReference(
    raw,
    kind: MediaDeliveryKind.video,
    imageCdnBaseUrl: imageCdnBaseUrl,
    videoCdnBaseUrl: videoCdnBaseUrl,
  );
}

/// 是否像可播放视频源：仅当公开视频引用能解析为唯一注入交付 URI 时为真。
bool isLikelyContentVideoMediaSource(String? raw) {
  return resolveContentVideoUrlCandidates(raw).isNotEmpty;
}

/// 本地相册/拍照尚未上传的临时文件路径，不经公开媒体交付解析。
bool isLocalFileImageSource(String? raw) {
  final source = raw?.trim() ?? '';
  if (source.isEmpty) {
    return false;
  }
  final lower = source.toLowerCase();
  return lower.startsWith('file://') ||
      lower.startsWith('content://') ||
      source.startsWith('/');
}

List<String> _resolveMediaReference(
  String? raw, {
  required MediaDeliveryKind kind,
  String? imageCdnBaseUrl,
  String? videoCdnBaseUrl,
}) {
  final source = raw?.trim() ?? '';
  if (source.isEmpty) {
    return const <String>[];
  }
  final lower = source.toLowerCase();
  if (kind != MediaDeliveryKind.video &&
      (lower.startsWith('data:') ||
          lower.startsWith('asset://') ||
          lower.startsWith('file://'))) {
    return <String>[source];
  }

  final resolver = MediaDeliveryResolver(
    MediaEndpointConfig(
      avatarBaseUrl:
          imageCdnBaseUrl ?? CloudRuntimeConfig.mediaAvatarCdnBaseUrl,
      imageBaseUrl: imageCdnBaseUrl ?? CloudRuntimeConfig.mediaImageCdnBaseUrl,
      videoBaseUrl: videoCdnBaseUrl ?? CloudRuntimeConfig.mediaVideoCdnBaseUrl,
      attachmentBaseUrl:
          imageCdnBaseUrl ?? CloudRuntimeConfig.mediaImageCdnBaseUrl,
    ),
  );
  final resolved = resolver.tryResolve(source, kind: kind);
  if (resolved == null) {
    return const <String>[];
  }
  return <String>[resolved.url];
}

MediaDeliveryKind _inferNonVideoKind(String? raw) {
  final source = (raw ?? '').trim();
  final parsed = Uri.tryParse(source);
  final path = (parsed != null && parsed.hasScheme ? parsed.path : source)
      .replaceFirst(RegExp(r'^/+'), '');
  if (path.startsWith('media/background/')) {
    return MediaDeliveryKind.background;
  }
  if (path.startsWith('media/avatar/')) {
    return MediaDeliveryKind.avatar;
  }
  if (path.startsWith('media/attachment/')) {
    return MediaDeliveryKind.attachment;
  }
  return MediaDeliveryKind.image;
}

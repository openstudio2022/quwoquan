import 'package:flutter/foundation.dart';

import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/core/media/media_delivery_reference.dart';
import 'package:quwoquan_app/core/platform/platform_capabilities.dart';

/// content-service `ui_config.yaml` 中 HLS/CMAF ABR 的 canonical flag。
const String hlsCmafAdaptivePlaybackFeatureFlag =
    ContentFeatureFlags.enableHlsCmafAbr;

/// 同一媒体版本的 ABR + progressive P0 交付集合。
///
/// HLS 只能作为第一候选，且必须与 progressive 引用拥有相同 asset/version；
/// 缺少能力、flag、descriptor 或配对事实时只返回 progressive，禁止猜测路径。
@immutable
class AdaptiveVideoDeliverySet {
  const AdaptiveVideoDeliverySet({
    required this.progressive,
    this.adaptive,
    this.adaptiveDescriptorVersion = 0,
  });

  final MediaDeliveryReference progressive;
  final MediaDeliveryReference? adaptive;
  final int adaptiveDescriptorVersion;

  List<MediaDeliveryReference> candidates({
    required bool featureEnabled,
    required PlatformCapabilities capabilities,
  }) {
    final adaptiveReference = adaptive;
    if (!featureEnabled ||
        !capabilities.adaptiveVideoPlayback ||
        adaptiveDescriptorVersion <= 0 ||
        adaptiveReference == null ||
        !_isCanonicalPair(adaptiveReference)) {
      return <MediaDeliveryReference>[progressive];
    }
    return <MediaDeliveryReference>[adaptiveReference, progressive];
  }

  bool _isCanonicalPair(MediaDeliveryReference candidate) {
    final assetId = progressive.assetId.trim();
    return progressive.kind == MediaDeliveryKind.video &&
        candidate.kind == MediaDeliveryKind.video &&
        assetId.isNotEmpty &&
        candidate.assetId.trim() == assetId &&
        progressive.version > 0 &&
        candidate.version == progressive.version;
  }
}

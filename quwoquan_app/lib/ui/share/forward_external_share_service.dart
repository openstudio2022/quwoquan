import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/platform/native_bridge.dart';
import 'package:quwoquan_app/core/platform/platform_capabilities.dart';
import 'package:quwoquan_app/core/platform/platform_providers.dart';
import 'package:quwoquan_app/ui/share/forward_share_models.dart';
import 'package:share_plus/share_plus.dart';
import 'package:uuid/uuid.dart';

enum ForwardExternalShareTarget { wechatFriend, wechatMoments }

enum ForwardExternalShareDelivery {
  wechatAccepted,
  wechatCompleted,
  systemShareFallback,
  cancelled,
  unavailable,
}

class ForwardExternalShareResult {
  const ForwardExternalShareResult({
    required this.target,
    required this.delivery,
    this.requestId = '',
  });

  final ForwardExternalShareTarget target;
  final ForwardExternalShareDelivery delivery;
  final String requestId;
}

abstract interface class ForwardSystemShareGateway {
  Future<void> share({required String text, required String subject});
}

abstract interface class ForwardWechatShareGateway {
  Future<NativeShareResult> share({
    required AppForwardPayload payload,
    required ForwardExternalShareTarget target,
  });
}

abstract interface class ForwardExternalShareService {
  Future<ForwardExternalShareResult> share({
    required AppForwardPayload payload,
    required ForwardExternalShareTarget target,
  });
}

final forwardExternalShareServiceProvider =
    Provider<ForwardExternalShareService>(
      (ref) => SharePlusForwardExternalShareService(
        capabilities: ref.watch(platformCapabilitiesProvider),
        wechatShareGateway: NativeBridgeForwardWechatShareGateway(
          ref.watch(nativeShareBridgeProvider),
        ),
      ),
    );

class SharePlusForwardSystemShareGateway implements ForwardSystemShareGateway {
  const SharePlusForwardSystemShareGateway();

  @override
  Future<void> share({required String text, required String subject}) {
    return SharePlus.instance.share(ShareParams(text: text, subject: subject));
  }
}

class NativeBridgeForwardWechatShareGateway
    implements ForwardWechatShareGateway {
  const NativeBridgeForwardWechatShareGateway(this.bridge);

  final NativeShareBridge bridge;

  @override
  Future<NativeShareResult> share({
    required AppForwardPayload payload,
    required ForwardExternalShareTarget target,
  }) async {
    final referralId = payload.extra['shareId']?.toString().trim() ?? '';
    final landingUrl = _httpsLandingUrl(payload);
    return bridge.shareWebpageCard(
      NativeShareWebpageCard(
        requestId: const Uuid().v4(),
        target: _nativeTargetFor(target),
        title: payload.title,
        description: payload.subtitle,
        webpageUrl: landingUrl,
        referralDigest: referralId.isEmpty
            ? ''
            : sha256.convert(utf8.encode(referralId)).toString(),
      ),
    );
  }

  String _httpsLandingUrl(AppForwardPayload payload) {
    for (final candidate in <String>[payload.landingUrl, payload.deeplink]) {
      final uri = Uri.tryParse(candidate.trim());
      if (uri != null && uri.scheme == 'https' && uri.host.isNotEmpty) {
        return uri.toString();
      }
    }
    return payload.landingUrl.trim();
  }

  NativeShareTarget _nativeTargetFor(ForwardExternalShareTarget target) {
    return switch (target) {
      ForwardExternalShareTarget.wechatFriend => NativeShareTarget.wechatFriend,
      ForwardExternalShareTarget.wechatMoments =>
        NativeShareTarget.wechatMoments,
    };
  }
}

class SharePlusForwardExternalShareService
    implements ForwardExternalShareService {
  const SharePlusForwardExternalShareService({
    required this.capabilities,
    this.systemShareGateway = const SharePlusForwardSystemShareGateway(),
    this.wechatShareGateway,
  });

  final PlatformCapabilities capabilities;
  final ForwardSystemShareGateway systemShareGateway;
  final ForwardWechatShareGateway? wechatShareGateway;

  @override
  Future<ForwardExternalShareResult> share({
    required AppForwardPayload payload,
    required ForwardExternalShareTarget target,
  }) async {
    final wechatGateway = wechatShareGateway;
    if (capabilities.wechatTargetedShare && wechatGateway != null) {
      final nativeResult = await wechatGateway.share(
        payload: payload,
        target: target,
      );
      switch (nativeResult.outcome) {
        case NativeShareOutcome.accepted:
          return ForwardExternalShareResult(
            target: target,
            delivery: ForwardExternalShareDelivery.wechatAccepted,
            requestId: nativeResult.requestId,
          );
        case NativeShareOutcome.completed:
          return ForwardExternalShareResult(
            target: target,
            delivery: ForwardExternalShareDelivery.wechatCompleted,
            requestId: nativeResult.requestId,
          );
        case NativeShareOutcome.cancelled:
          return ForwardExternalShareResult(
            target: target,
            delivery: ForwardExternalShareDelivery.cancelled,
            requestId: nativeResult.requestId,
          );
        case NativeShareOutcome.unavailable:
        case NativeShareOutcome.failed:
          break;
      }
    }
    if (!capabilities.systemShareSheet) {
      return ForwardExternalShareResult(
        target: target,
        delivery: ForwardExternalShareDelivery.unavailable,
      );
    }
    final text = payload.shareText.trim().isNotEmpty
        ? payload.shareText.trim()
        : payload.messagePreview;
    await systemShareGateway.share(text: text, subject: payload.title);
    return ForwardExternalShareResult(
      target: target,
      delivery: ForwardExternalShareDelivery.systemShareFallback,
    );
  }
}

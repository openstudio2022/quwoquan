import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:share_plus/share_plus.dart';
import 'package:quwoquan_app/core/platform/platform_capabilities.dart';
import 'package:quwoquan_app/core/platform/native_bridge.dart';
import 'package:quwoquan_app/core/platform/platform_providers.dart';
import 'package:quwoquan_app/ui/share/forward_share_models.dart';

enum ForwardExternalShareTarget { wechatFriend, wechatMoments }

enum ForwardExternalShareDelivery {
  targetedWechat,
  systemShareFallback,
  unavailable,
}

class ForwardExternalShareResult {
  const ForwardExternalShareResult({
    required this.target,
    required this.delivery,
  });

  final ForwardExternalShareTarget target;
  final ForwardExternalShareDelivery delivery;
}

abstract interface class ForwardSystemShareGateway {
  Future<void> share({required String text, required String subject});
}

abstract interface class ForwardWechatShareGateway {
  Future<bool> share({
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
  Future<bool> share({
    required AppForwardPayload payload,
    required ForwardExternalShareTarget target,
  }) async {
    final text = payload.shareText.trim().isNotEmpty
        ? payload.shareText.trim()
        : payload.messagePreview;
    final result = await bridge.shareText(
      target: _nativeTargetFor(target),
      text: text,
      subject: payload.title,
    );
    return result.isDelivered;
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
      final delivered = await wechatGateway.share(
        payload: payload,
        target: target,
      );
      if (delivered) {
        return ForwardExternalShareResult(
          target: target,
          delivery: ForwardExternalShareDelivery.targetedWechat,
        );
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

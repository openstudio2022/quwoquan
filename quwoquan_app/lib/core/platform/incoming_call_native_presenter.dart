import 'package:flutter/services.dart';
import 'package:flutter_callkit_incoming/entities/android_params.dart';
import 'package:flutter_callkit_incoming/entities/call_kit_params.dart';
import 'package:flutter_callkit_incoming/entities/ios_params.dart';
import 'package:flutter_callkit_incoming/flutter_callkit_incoming.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/platform/incoming_call_envelope.dart';

final class IncomingCallPresentationResult {
  const IncomingCallPresentationResult({
    required this.presented,
    required this.fullScreenAllowed,
  });

  final bool presented;
  final bool fullScreenAllowed;
}

abstract interface class IncomingCallNativePresenter {
  Future<IncomingCallPresentationResult> present(
    IncomingCallEnvelope envelope, {
    required bool fullScreenAllowed,
    String? ringtonePath,
  });
}

/// `flutter_callkit_incoming` 的唯一参数装配点。
///
/// 品牌名和颜色从现有 App 真相源派生；插件 API 要求十六进制字符串，因此只在这里
/// 做一次格式转换，禁止业务文件散落颜色字面量。
final class CallKitIncomingNativePresenter
    implements IncomingCallNativePresenter {
  const CallKitIncomingNativePresenter();

  static String get brandColorHex {
    final rgb = AppColors.primaryColor.toARGB32() & 0x00ffffff;
    return '#${rgb.toRadixString(16).padLeft(6, '0').toUpperCase()}';
  }

  @override
  Future<IncomingCallPresentationResult> present(
    IncomingCallEnvelope envelope, {
    required bool fullScreenAllowed,
    String? ringtonePath,
  }) async {
    final params = CallKitParams(
      id: envelope.callId,
      nameCaller: envelope.callerName,
      appName: UITextConstants.settingsAppOfficialName,
      handle: envelope.callerName,
      type: envelope.isVideo ? 1 : 0,
      duration: 30000,
      extra: <String, dynamic>{...envelope.toMap()},
      headers: const <String, dynamic>{},
      android: AndroidParams(
        isCustomNotification: true,
        isShowLogo: false,
        ringtonePath: ringtonePath ?? 'system_ringtone_default',
        backgroundColor: brandColorHex,
        actionColor: brandColorHex,
        isShowFullLockedScreen: fullScreenAllowed,
        isFullScreen: false,
        isImportant: true,
        textAccept: UITextConstants.callAccept,
        textDecline: UITextConstants.callReject,
      ),
      ios: IOSParams(
        iconName: 'CallKitLogo',
        handleType: 'generic',
        supportsVideo: true,
        maximumCallGroups: 1,
        maximumCallsPerCallGroup: 1,
        audioSessionMode: 'default',
        audioSessionActive: true,
        audioSessionPreferredSampleRate: 44100.0,
        audioSessionPreferredIOBufferDuration: 0.005,
        supportsDTMF: false,
        supportsHolding: false,
        supportsGrouping: false,
        supportsUngrouping: false,
        ringtonePath: ringtonePath ?? 'system_ringtone_default',
      ),
    );
    try {
      await FlutterCallkitIncoming.showCallkitIncoming(params);
      return IncomingCallPresentationResult(
        presented: true,
        fullScreenAllowed: fullScreenAllowed,
      );
    } on MissingPluginException {
      return IncomingCallPresentationResult(
        presented: false,
        fullScreenAllowed: fullScreenAllowed,
      );
    } on PlatformException {
      return IncomingCallPresentationResult(
        presented: false,
        fullScreenAllowed: fullScreenAllowed,
      );
    }
  }
}

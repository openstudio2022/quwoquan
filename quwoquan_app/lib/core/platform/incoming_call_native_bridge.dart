import 'package:flutter/services.dart';
import 'package:flutter_callkit_incoming/flutter_callkit_incoming.dart';
import 'package:quwoquan_app/core/platform/incoming_call_envelope.dart';

enum IncomingCallNativeActionType {
  accept('accept'),
  decline('decline'),
  end('end'),
  timeout('timeout');

  const IncomingCallNativeActionType(this.wireName);

  final String wireName;

  static IncomingCallNativeActionType? fromWire(String value) {
    for (final candidate in values) {
      if (candidate.wireName == value) {
        return candidate;
      }
    }
    return null;
  }
}

final class IncomingCallNativeAction {
  const IncomingCallNativeAction({
    required this.callId,
    required this.type,
    required this.occurredAt,
  });

  final String callId;
  final IncomingCallNativeActionType type;
  final DateTime occurredAt;

  String get dedupeKey => '${type.wireName}:$callId';
}

final class IncomingCallNativeCapability {
  const IncomingCallNativeCapability({
    required this.nativeUiAvailable,
    required this.fullScreenPresentationAllowed,
    required this.backgroundPushConfigured,
  });

  const IncomingCallNativeCapability.unsupported()
    : nativeUiAvailable = false,
      fullScreenPresentationAllowed = false,
      backgroundPushConfigured = false;

  final bool nativeUiAvailable;
  final bool fullScreenPresentationAllowed;
  final bool backgroundPushConfigured;

  bool get usesHeadsUpFallback =>
      nativeUiAvailable && !fullScreenPresentationAllowed;
}

abstract interface class IncomingCallNativeBridge {
  Future<void> setFlutterReady(bool ready);

  Future<List<IncomingCallEnvelope>> readPendingEnvelopes();

  Future<List<IncomingCallNativeAction>> consumePendingActions();

  Future<IncomingCallNativeCapability> readCapability();

  Future<void> endNativeCall(String callId);
}

final class MethodChannelIncomingCallNativeBridge
    implements IncomingCallNativeBridge {
  const MethodChannelIncomingCallNativeBridge({
    this.channel = const MethodChannel('quwoquan/rtc/incoming_call'),
  });

  final MethodChannel channel;

  @override
  Future<void> setFlutterReady(bool ready) async {
    try {
      await channel.invokeMethod<void>(
        'setIncomingCallFlutterReady',
        <String, Object>{'ready': ready},
      );
    } on MissingPluginException {
      return;
    } on PlatformException {
      return;
    }
  }

  @override
  Future<List<IncomingCallEnvelope>> readPendingEnvelopes() async {
    final envelopes = <IncomingCallEnvelope>[];
    try {
      final raw = await channel.invokeMethod<Object?>(
        'readPendingIncomingCalls',
      );
      _appendEnvelopes(envelopes, raw);
    } on MissingPluginException {
      // Android 主要从插件 activeCalls 恢复；不需要主 Activity 才能展示后台来电。
    } on PlatformException {
      // 原生桥不可用时仍尝试插件自身持久化的 activeCalls。
    }

    try {
      final activeCalls = await FlutterCallkitIncoming.activeCalls();
      for (final activeCall in activeCalls) {
        final extra = activeCall.extra;
        if (extra == null) {
          continue;
        }
        _appendEnvelope(envelopes, extra);
      }
    } on MissingPluginException {
      // 由调用方根据能力位降级到站内来电。
    } on PlatformException {
      // 同上。
    }
    return List<IncomingCallEnvelope>.unmodifiable(envelopes);
  }

  @override
  Future<List<IncomingCallNativeAction>> consumePendingActions() async {
    try {
      final raw = await channel.invokeMethod<Object?>(
        'consumePendingIncomingCallActions',
      );
      if (raw is! List) {
        return const <IncomingCallNativeAction>[];
      }
      final actions = <IncomingCallNativeAction>[];
      for (final item in raw) {
        if (item is! Map) {
          continue;
        }
        final callId = item['callId']?.toString().trim() ?? '';
        final type = IncomingCallNativeActionType.fromWire(
          item['action']?.toString().trim() ?? '',
        );
        final occurredAt = DateTime.tryParse(
          item['occurredAt']?.toString() ?? '',
        )?.toUtc();
        if (callId.isEmpty || type == null || occurredAt == null) {
          continue;
        }
        actions.add(
          IncomingCallNativeAction(
            callId: callId,
            type: type,
            occurredAt: occurredAt,
          ),
        );
      }
      return List<IncomingCallNativeAction>.unmodifiable(actions);
    } on MissingPluginException {
      return const <IncomingCallNativeAction>[];
    } on PlatformException {
      return const <IncomingCallNativeAction>[];
    }
  }

  @override
  Future<IncomingCallNativeCapability> readCapability() async {
    var fullScreenAllowed = false;
    var nativeUiAvailable = true;
    try {
      fullScreenAllowed = await FlutterCallkitIncoming.canUseFullScreenIntent();
    } on MissingPluginException {
      nativeUiAvailable = false;
    } on PlatformException {
      // Android 14 权限探测失败时 fail-closed：只允许 heads-up，不直接打开 Activity。
      fullScreenAllowed = false;
    }

    var backgroundPushConfigured = false;
    try {
      final raw = await channel.invokeMethod<Object?>(
        'readIncomingCallCapability',
      );
      if (raw is Map) {
        backgroundPushConfigured =
            raw['backgroundPushConfigured'] as bool? ?? false;
      }
    } on MissingPluginException {
      // Firebase 配置状态由 Dart Firebase runtime 单独补充。
    } on PlatformException {
      // 保持 fail-closed。
    }
    return IncomingCallNativeCapability(
      nativeUiAvailable: nativeUiAvailable,
      fullScreenPresentationAllowed: fullScreenAllowed,
      backgroundPushConfigured: backgroundPushConfigured,
    );
  }

  @override
  Future<void> endNativeCall(String callId) async {
    if (callId.trim().isEmpty) {
      return;
    }
    try {
      await FlutterCallkitIncoming.endCall(callId);
    } on MissingPluginException {
      return;
    } on PlatformException {
      return;
    }
  }

  static void _appendEnvelopes(List<IncomingCallEnvelope> target, Object? raw) {
    if (raw is! List) {
      return;
    }
    for (final item in raw) {
      _appendEnvelope(target, item);
    }
  }

  static void _appendEnvelope(List<IncomingCallEnvelope> target, Object? raw) {
    if (raw is! Map) {
      return;
    }
    try {
      target.add(IncomingCallEnvelope.fromMap(raw));
    } on FormatException {
      return;
    }
  }
}

final class UnsupportedIncomingCallNativeBridge
    implements IncomingCallNativeBridge {
  const UnsupportedIncomingCallNativeBridge();

  @override
  Future<void> setFlutterReady(bool ready) async {}

  @override
  Future<List<IncomingCallEnvelope>> readPendingEnvelopes() async =>
      const <IncomingCallEnvelope>[];

  @override
  Future<List<IncomingCallNativeAction>> consumePendingActions() async =>
      const <IncomingCallNativeAction>[];

  @override
  Future<IncomingCallNativeCapability> readCapability() async =>
      const IncomingCallNativeCapability.unsupported();

  @override
  Future<void> endNativeCall(String callId) async {}
}

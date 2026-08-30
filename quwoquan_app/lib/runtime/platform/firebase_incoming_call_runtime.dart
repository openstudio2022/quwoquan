import 'dart:async';
import 'dart:convert';
import 'dart:developer' as developer;

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_callkit_incoming/flutter_callkit_incoming.dart';
import 'package:quwoquan_app/runtime/platform/incoming_call_envelope.dart';
import 'package:quwoquan_app/runtime/platform/incoming_call_native_presenter.dart';
import 'package:quwoquan_app/runtime/platform/platform_target.dart';
import 'package:quwoquan_app/runtime/platform/push_endpoint_gateway.dart';
import 'package:shared_preferences/shared_preferences.dart';

@pragma('vm:entry-point')
Future<void> firebaseIncomingCallBackgroundHandler(
  RemoteMessage message,
) async {
  WidgetsFlutterBinding.ensureInitialized();
  if (currentAppPlatform != AppPlatform.android) {
    return;
  }
  try {
    if (Firebase.apps.isEmpty) {
      await Firebase.initializeApp();
    }
  } on FirebaseException {
    // 缺少真实 google-services 配置时 fail-closed，不伪造 Firebase App。
    return;
  } on PlatformException {
    // Background engine 或原生 Firebase 配置不可用时同样 fail-closed。
    return;
  } on MissingPluginException {
    // startup-critical 注册缺失时不尝试构造假来电。
    return;
  }

  final IncomingCallPushEnvelope push;
  try {
    push = IncomingCallPushEnvelope.fromMap(message.data);
  } on FormatException {
    return;
  }
  final now = DateTime.now().toUtc();
  if (push.call.isExpiredAt(now) ||
      push.occurredAt.isAfter(now.add(const Duration(minutes: 5)))) {
    return;
  }
  if (push.action == IncomingCallPushAction.cancel) {
    await _claimFirebaseDelivery(push.call);
    try {
      await FlutterCallkitIncoming.endCall(push.call.callId);
    } on PlatformException {
      return;
    } on MissingPluginException {
      return;
    }
    return;
  }
  if (!await _claimFirebaseDelivery(push.call)) {
    return;
  }

  var fullScreenAllowed = false;
  try {
    fullScreenAllowed = await FlutterCallkitIncoming.canUseFullScreenIntent();
  } on Object {
    // Android 14 探测失败时只允许 heads-up；禁止后台直接 startActivity。
    fullScreenAllowed = false;
  }
  await const CallKitIncomingNativePresenter().present(
    push.call,
    fullScreenAllowed: fullScreenAllowed,
  );
}

bool _backgroundHandlerRegistered = false;

/// 必须在 `runApp` 前注册，确保 Android 在主 isolate 尚未启动时也能找到回调句柄。
void registerFirebaseIncomingCallBackgroundHandler() {
  if (currentAppPlatform != AppPlatform.android ||
      _backgroundHandlerRegistered) {
    return;
  }
  FirebaseMessaging.onBackgroundMessage(firebaseIncomingCallBackgroundHandler);
  _backgroundHandlerRegistered = true;
}

const _firebaseDeliveryDedupeKey = 'rtc.incoming.fcm_seen_deliveries';
const _firebaseDeliveryDedupeLimit = 128;
final _firebaseProcessDedupe = BoundedIncomingCallDedupe(
  capacity: _firebaseDeliveryDedupeLimit,
);

Future<void> clearFirebaseIncomingCallStateForTerminalAccountClosure() async {
  _firebaseProcessDedupe.clear();
  final preferences = await SharedPreferences.getInstance();
  await preferences.remove(_firebaseDeliveryDedupeKey);
  if (preferences.containsKey(_firebaseDeliveryDedupeKey)) {
    throw StateError('firebase incoming call cleanup verification failed');
  }
}

Future<bool> _claimFirebaseDelivery(IncomingCallEnvelope envelope) async {
  try {
    final preferences = await SharedPreferences.getInstance();
    final now = DateTime.now().toUtc();
    final retained = <Map<String, String>>[];
    final encoded = preferences.getString(_firebaseDeliveryDedupeKey);
    if (encoded != null && encoded.isNotEmpty) {
      final raw = jsonDecode(encoded);
      if (raw is List) {
        for (final item in raw) {
          if (item is! Map) {
            continue;
          }
          final deliveryKey = item['deliveryKey']?.toString() ?? '';
          final callId = item['callId']?.toString() ?? '';
          final expiresAt = DateTime.tryParse(
            item['expiresAt']?.toString() ?? '',
          )?.toUtc();
          if (deliveryKey.isEmpty ||
              callId.isEmpty ||
              expiresAt == null ||
              !expiresAt.isAfter(now)) {
            continue;
          }
          if (deliveryKey == envelope.deliveryKey ||
              callId == envelope.callId) {
            return false;
          }
          retained.add(<String, String>{
            'deliveryKey': deliveryKey,
            'callId': callId,
            'expiresAt': expiresAt.toIso8601String(),
          });
        }
      }
    }
    retained.add(<String, String>{
      'deliveryKey': envelope.deliveryKey,
      'callId': envelope.callId,
      'expiresAt': envelope.expiresAt.toIso8601String(),
    });
    if (retained.length > _firebaseDeliveryDedupeLimit) {
      retained.removeRange(0, retained.length - _firebaseDeliveryDedupeLimit);
    }
    await preferences.setString(
      _firebaseDeliveryDedupeKey,
      jsonEncode(retained),
    );
    return true;
  } on FormatException {
    return _firebaseProcessDedupe.claim(envelope) ==
        IncomingCallClaimResult.accepted;
  } on PlatformException {
    return _firebaseProcessDedupe.claim(envelope) ==
        IncomingCallClaimResult.accepted;
  } on MissingPluginException {
    return _firebaseProcessDedupe.claim(envelope) ==
        IncomingCallClaimResult.accepted;
  }
}

final class PushTapIntent {
  const PushTapIntent({
    required this.targetType,
    required this.targetId,
    required this.callId,
  });

  factory PushTapIntent.fromData(Map<String, dynamic> data) => PushTapIntent(
    targetType: (data['targetType'] ?? '').toString().trim(),
    targetId: (data['targetId'] ?? '').toString().trim(),
    callId: (data['callId'] ?? '').toString().trim(),
  );

  final String targetType;
  final String targetId;
  final String callId;
}

abstract interface class PushTapIntentSource {
  Future<void> start(void Function(PushTapIntent intent) onIntent);

  Future<void> stop();
}

abstract interface class FirebasePushMessagingClient {
  Future<void> initialize();

  Future<String?> readToken();

  Stream<String> get tokenRefreshes;

  Stream<RemoteMessage> get foregroundMessages;

  /// 用户点按系统推送把应用从后台带回前台的消息流。
  Stream<RemoteMessage> get openedMessages;

  /// 应用因点按推送而冷启动时的初始消息（无则为 null）。
  Future<RemoteMessage?> readInitialMessage();

  Future<bool> readNotificationAuthorization();
}

final class FirebasePluginPushMessagingClient
    implements FirebasePushMessagingClient {
  const FirebasePluginPushMessagingClient();

  @override
  Future<void> initialize() async {
    if (Firebase.apps.isEmpty) {
      await Firebase.initializeApp();
    }
  }

  @override
  Future<String?> readToken() => FirebaseMessaging.instance.getToken();

  @override
  Stream<String> get tokenRefreshes =>
      FirebaseMessaging.instance.onTokenRefresh;

  @override
  Stream<RemoteMessage> get foregroundMessages => FirebaseMessaging.onMessage;

  @override
  Stream<RemoteMessage> get openedMessages =>
      FirebaseMessaging.onMessageOpenedApp;

  @override
  Future<RemoteMessage?> readInitialMessage() =>
      FirebaseMessaging.instance.getInitialMessage();

  @override
  Future<bool> readNotificationAuthorization() async {
    final settings = await FirebaseMessaging.instance.getNotificationSettings();
    return settings.authorizationStatus == AuthorizationStatus.authorized ||
        settings.authorizationStatus == AuthorizationStatus.provisional;
  }
}

enum FirebasePushMessagingRuntimeAvailability {
  ready,
  unsupported,
  notConfigured,
  unavailable,
}

final class FirebasePushMessagingRuntimeState {
  const FirebasePushMessagingRuntimeState._({
    required this.availability,
    required this.notificationAuthorized,
  });

  const FirebasePushMessagingRuntimeState.ready({
    required bool notificationAuthorized,
  }) : this._(
         availability: FirebasePushMessagingRuntimeAvailability.ready,
         notificationAuthorized: notificationAuthorized,
       );

  const FirebasePushMessagingRuntimeState.unsupported()
    : this._(
        availability: FirebasePushMessagingRuntimeAvailability.unsupported,
        notificationAuthorized: false,
      );

  const FirebasePushMessagingRuntimeState.notConfigured()
    : this._(
        availability: FirebasePushMessagingRuntimeAvailability.notConfigured,
        notificationAuthorized: false,
      );

  const FirebasePushMessagingRuntimeState.unavailable()
    : this._(
        availability: FirebasePushMessagingRuntimeAvailability.unavailable,
        notificationAuthorized: false,
      );

  final FirebasePushMessagingRuntimeAvailability availability;
  final bool notificationAuthorized;

  bool get supported =>
      availability != FirebasePushMessagingRuntimeAvailability.unsupported;
  bool get configured =>
      availability == FirebasePushMessagingRuntimeAvailability.ready;
}

final class FirebasePushMessagingRuntime implements PushTapIntentSource {
  FirebasePushMessagingRuntime({
    required this.client,
    AppPlatform Function()? platformReader,
  }) : _platformReader = platformReader ?? (() => currentAppPlatform);

  final FirebasePushMessagingClient client;
  final AppPlatform Function() _platformReader;
  Future<FirebasePushMessagingRuntimeState>? _initializeInFlight;
  StreamSubscription<RemoteMessage>? _openedSubscription;

  Future<FirebasePushMessagingRuntimeState> initialize() {
    final active = _initializeInFlight;
    if (active != null) {
      return active;
    }
    final task = _initialize();
    _initializeInFlight = task;
    return task;
  }

  Future<FirebasePushMessagingRuntimeState> _initialize() async {
    if (_platformReader() != AppPlatform.android) {
      return const FirebasePushMessagingRuntimeState.unsupported();
    }
    try {
      await client.initialize();
      final notificationAuthorized = await client
          .readNotificationAuthorization();
      return FirebasePushMessagingRuntimeState.ready(
        notificationAuthorized: notificationAuthorized,
      );
    } on FirebaseException catch (error, stackTrace) {
      if (error.code == 'no-app' || error.code == 'missing-config') {
        return const FirebasePushMessagingRuntimeState.notConfigured();
      }
      developer.log(
        'Firebase push initialization unavailable',
        name: 'quwoquan.firebase_push',
        error: error,
        stackTrace: stackTrace,
      );
      return const FirebasePushMessagingRuntimeState.unavailable();
    } on PlatformException catch (error, stackTrace) {
      if (error.code.contains('missing') ||
          error.code.contains('not_configured')) {
        return const FirebasePushMessagingRuntimeState.notConfigured();
      }
      developer.log(
        'Firebase push platform initialization unavailable',
        name: 'quwoquan.firebase_push',
        error: error,
        stackTrace: stackTrace,
      );
      return const FirebasePushMessagingRuntimeState.unavailable();
    } on MissingPluginException catch (error, stackTrace) {
      developer.log(
        'Firebase push plugin unavailable',
        name: 'quwoquan.firebase_push',
        error: error,
        stackTrace: stackTrace,
      );
      return const FirebasePushMessagingRuntimeState.unavailable();
    }
  }

  @override
  Future<void> start(void Function(PushTapIntent intent) onIntent) async {
    final state = await initialize();
    if (!state.configured) {
      return;
    }
    await _openedSubscription?.cancel();
    try {
      _openedSubscription = client.openedMessages.listen(
        (message) => onIntent(PushTapIntent.fromData(message.data)),
      );
      final initial = await client.readInitialMessage();
      if (initial != null) {
        onIntent(PushTapIntent.fromData(initial.data));
      }
    } on FirebaseException catch (error, stackTrace) {
      await _cancelTapSubscription();
      developer.log(
        'Firebase push initial message unavailable',
        name: 'quwoquan.firebase_push',
        error: error,
        stackTrace: stackTrace,
      );
    } on PlatformException catch (error, stackTrace) {
      await _cancelTapSubscription();
      developer.log(
        'Firebase push initial message platform failure',
        name: 'quwoquan.firebase_push',
        error: error,
        stackTrace: stackTrace,
      );
    } on MissingPluginException catch (error, stackTrace) {
      await _cancelTapSubscription();
      developer.log(
        'Firebase push initial message plugin unavailable',
        name: 'quwoquan.firebase_push',
        error: error,
        stackTrace: stackTrace,
      );
    }
  }

  Future<void> _cancelTapSubscription() async {
    await _openedSubscription?.cancel();
    _openedSubscription = null;
  }

  @override
  Future<void> stop() => _cancelTapSubscription();
}

/// Android FCM token/source 生命周期。这里只探测并持久化，不在冷启动请求通知权限。
final class FirebaseIncomingCallRuntime {
  FirebaseIncomingCallRuntime({
    required this.pushEndpointGateway,
    required this.messagingRuntime,
  });

  final PushEndpointGateway pushEndpointGateway;
  final FirebasePushMessagingRuntime messagingRuntime;
  FirebasePushMessagingClient get _messagingClient => messagingRuntime.client;
  final _foregroundIncomingCalls =
      StreamController<IncomingCallEnvelope>.broadcast();
  final _foregroundCancellations =
      StreamController<IncomingCallPushEnvelope>.broadcast();

  StreamSubscription<String>? _tokenRefreshSubscription;
  StreamSubscription<RemoteMessage>? _foregroundMessageSubscription;
  Future<FirebasePushMessagingRuntimeState>? _startInFlight;

  Stream<IncomingCallEnvelope> get foregroundIncomingCalls =>
      _foregroundIncomingCalls.stream;

  Stream<IncomingCallPushEnvelope> get foregroundCancellations =>
      _foregroundCancellations.stream;

  Future<FirebasePushMessagingRuntimeState> start() {
    final active = _startInFlight;
    if (active != null) {
      return active;
    }
    final task = _start();
    _startInFlight = task;
    return task;
  }

  Future<FirebasePushMessagingRuntimeState> _start() async {
    final initialization = await messagingRuntime.initialize();
    if (!initialization.configured) {
      return initialization;
    }
    try {
      await _foregroundMessageSubscription?.cancel();
      _foregroundMessageSubscription = _messagingClient.foregroundMessages
          .listen((message) {
            try {
              final push = IncomingCallPushEnvelope.fromMap(message.data);
              final now = DateTime.now().toUtc();
              if (push.call.isExpiredAt(now) ||
                  push.occurredAt.isAfter(
                    now.add(const Duration(minutes: 5)),
                  )) {
                return;
              }
              if (push.action == IncomingCallPushAction.cancel) {
                _foregroundCancellations.add(push);
              } else {
                _foregroundIncomingCalls.add(push.call);
              }
            } on FormatException {
              return;
            }
          });
      final token = (await _messagingClient.readToken())?.trim() ?? '';
      if (token.isNotEmpty) {
        await pushEndpointGateway.recordUpsert(
          DevicePushEndpoint(kind: PushEndpointKind.fcm, token: token),
        );
      }
      await _tokenRefreshSubscription?.cancel();
      _tokenRefreshSubscription = _messagingClient.tokenRefreshes.listen((
        token,
      ) {
        final normalized = token.trim();
        if (normalized.isEmpty) {
          return;
        }
        unawaited(
          pushEndpointGateway.recordUpsert(
            DevicePushEndpoint(kind: PushEndpointKind.fcm, token: normalized),
          ),
        );
      });
      return initialization;
    } on FirebaseException catch (error, stackTrace) {
      await _cancelMessagingSubscriptions();
      developer.log(
        'Firebase incoming call runtime unavailable',
        name: 'quwoquan.firebase_push',
        error: error,
        stackTrace: stackTrace,
      );
      return const FirebasePushMessagingRuntimeState.unavailable();
    } on PlatformException catch (error, stackTrace) {
      await _cancelMessagingSubscriptions();
      developer.log(
        'Firebase incoming call platform runtime unavailable',
        name: 'quwoquan.firebase_push',
        error: error,
        stackTrace: stackTrace,
      );
      return const FirebasePushMessagingRuntimeState.unavailable();
    } on MissingPluginException catch (error, stackTrace) {
      await _cancelMessagingSubscriptions();
      developer.log(
        'Firebase incoming call plugin unavailable',
        name: 'quwoquan.firebase_push',
        error: error,
        stackTrace: stackTrace,
      );
      return const FirebasePushMessagingRuntimeState.unavailable();
    }
  }

  Future<void> stop() async {
    await _cancelMessagingSubscriptions();
    _startInFlight = null;
  }

  Future<void> _cancelMessagingSubscriptions() async {
    await _tokenRefreshSubscription?.cancel();
    _tokenRefreshSubscription = null;
    await _foregroundMessageSubscription?.cancel();
    _foregroundMessageSubscription = null;
  }
}

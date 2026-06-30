import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_callkit_incoming/entities/call_kit_params.dart';
import 'package:flutter_callkit_incoming/entities/android_params.dart';
import 'package:flutter_callkit_incoming/entities/ios_params.dart';
import 'package:flutter_callkit_incoming/entities/call_event.dart';
import 'package:flutter_callkit_incoming/flutter_callkit_incoming.dart';
import 'package:quwoquan_app/cloud/services/user/call_settings_repository.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';

enum CallKitAction { accept, decline, end, timeout }

class CallKitService {
  CallKitService({Stream<CallEvent?>? eventStream})
    : _eventStream = eventStream ?? FlutterCallkitIncoming.onEvent;

  final Stream<CallEvent?> _eventStream;
  StreamSubscription<CallEvent?>? _eventSub;
  final _actions = StreamController<CallKitAction>.broadcast();
  bool _nativeEventStreamAvailable = true;

  Stream<CallKitAction> get actions => _actions.stream;

  String? _activeCallId;
  String? get activeCallId => _activeCallId;
  @visibleForTesting
  bool get nativeEventStreamAvailable => _nativeEventStreamAvailable;

  Future<bool> showIncomingCall({
    required String callId,
    required String callerName,
    required bool isVideo,
    String? avatarUrl,
    String? ringtoneId,
  }) async {
    _activeCallId = callId;
    final ringtonePath = OfficialCallRingtoneCatalog.resolveCallkitPath(
      ringtoneId,
    );

    final params = CallKitParams(
      id: callId,
      nameCaller: callerName,
      appName: '趣我圈',
      avatar: avatarUrl,
      handle: callerName,
      type: isVideo ? 1 : 0,
      duration: 30000,
      // CallKitParams.extra / headers 类型由 flutter_callkit_incoming 固定为 Map<String, dynamic>?
      extra: <String, dynamic>{'callId': callId},
      headers: const <String, dynamic>{},
      android: AndroidParams(
        isCustomNotification: true,
        isShowLogo: false,
        ringtonePath: ringtonePath,
        backgroundColor: '#0955fa',
        actionColor: '#0955fa',
        isShowFullLockedScreen: true,
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
        ringtonePath: ringtonePath,
      ),
    );

    try {
      await FlutterCallkitIncoming.showCallkitIncoming(params);
      return true;
    } on MissingPluginException catch (error) {
      _activeCallId = null;
      _markNativeEventStreamUnavailable(error);
      return false;
    } on PlatformException catch (error) {
      _activeCallId = null;
      _markNativeEventStreamUnavailable(error);
      return false;
    }
  }

  void startListening() {
    _eventSub?.cancel();
    try {
      _eventSub = _eventStream.listen(
        _handleCallKitEvent,
        onError: (Object error, StackTrace stackTrace) {
          if (_markNativeEventStreamUnavailable(error)) {
            return;
          }
          FlutterError.reportError(
            FlutterErrorDetails(
              exception: error,
              stack: stackTrace,
              library: 'callkit_service',
              context: ErrorDescription('while listening to CallKit events'),
            ),
          );
        },
      );
      _nativeEventStreamAvailable = true;
    } on MissingPluginException catch (error) {
      _markNativeEventStreamUnavailable(error);
    } on PlatformException catch (error) {
      _markNativeEventStreamUnavailable(error);
    }
  }

  void stopListening() {
    _eventSub?.cancel();
    _eventSub = null;
  }

  void _handleCallKitEvent(CallEvent? event) {
    if (event == null) return;
    debugPrint('CallKit event: $event');

    switch (event) {
      case CallEventActionCallAccept():
        _actions.add(CallKitAction.accept);
      case CallEventActionCallDecline():
        _actions.add(CallKitAction.decline);
        _activeCallId = null;
      case CallEventActionCallEnded():
        _actions.add(CallKitAction.end);
        _activeCallId = null;
      case CallEventActionCallTimeout():
        _actions.add(CallKitAction.timeout);
        _activeCallId = null;
      default:
        break;
    }
  }

  bool _markNativeEventStreamUnavailable(Object error) {
    if (error is! MissingPluginException && error is! PlatformException) {
      return false;
    }
    _nativeEventStreamAvailable = false;
    _eventSub?.cancel();
    _eventSub = null;
    debugPrint(
      'CallKit native event stream unavailable; '
      'incoming call UI will use app-level fallback. error=$error',
    );
    return true;
  }

  Future<void> endCall() async {
    if (_activeCallId != null) {
      try {
        await FlutterCallkitIncoming.endCall(_activeCallId!);
      } on MissingPluginException catch (error) {
        _markNativeEventStreamUnavailable(error);
      } on PlatformException catch (error) {
        _markNativeEventStreamUnavailable(error);
      }
      _activeCallId = null;
    }
  }

  Future<void> endAllCalls() async {
    try {
      await FlutterCallkitIncoming.endAllCalls();
    } on MissingPluginException catch (error) {
      _markNativeEventStreamUnavailable(error);
    } on PlatformException catch (error) {
      _markNativeEventStreamUnavailable(error);
    }
    _activeCallId = null;
  }

  void dispose() {
    stopListening();
    _actions.close();
  }
}

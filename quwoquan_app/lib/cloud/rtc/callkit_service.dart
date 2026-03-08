import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_callkit_incoming/entities/call_kit_params.dart';
import 'package:flutter_callkit_incoming/entities/android_params.dart';
import 'package:flutter_callkit_incoming/entities/ios_params.dart';
import 'package:flutter_callkit_incoming/entities/notification_params.dart';
import 'package:flutter_callkit_incoming/entities/call_event.dart';
import 'package:flutter_callkit_incoming/flutter_callkit_incoming.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';

enum CallKitAction { accept, decline, end, timeout }

class CallKitService {
  StreamSubscription<dynamic>? _eventSub;
  final _actions = StreamController<CallKitAction>.broadcast();

  Stream<CallKitAction> get actions => _actions.stream;

  String? _activeCallId;
  String? get activeCallId => _activeCallId;

  Future<void> showIncomingCall({
    required String callId,
    required String callerName,
    required bool isVideo,
    String? avatarUrl,
  }) async {
    _activeCallId = callId;

    final params = CallKitParams(
      id: callId,
      nameCaller: callerName,
      appName: '趣我圈',
      avatar: avatarUrl,
      handle: callerName,
      type: isVideo ? 1 : 0,
      duration: 30000,
      textAccept: UITextConstants.callAccept,
      textDecline: UITextConstants.callReject,
      extra: <String, dynamic>{'callId': callId},
      headers: <String, dynamic>{},
      android: const AndroidParams(
        isCustomNotification: true,
        isShowLogo: false,
        ringtonePath: 'system_ringtone_default',
        backgroundColor: '#0955fa',
        actionColor: '#4CAF50',
        isShowFullLockedScreen: true,
      ),
      ios: const IOSParams(
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
        ringtonePath: 'system_ringtone_default',
      ),
    );

    await FlutterCallkitIncoming.showCallkitIncoming(params);
  }

  void startListening() {
    _eventSub?.cancel();
    _eventSub = FlutterCallkitIncoming.onEvent.listen((event) {
      if (event == null) return;
      debugPrint('CallKit event: ${event.event}');

      switch (event.event) {
        case Event.actionCallAccept:
          _actions.add(CallKitAction.accept);
          break;
        case Event.actionCallDecline:
          _actions.add(CallKitAction.decline);
          _activeCallId = null;
          break;
        case Event.actionCallEnded:
          _actions.add(CallKitAction.end);
          _activeCallId = null;
          break;
        case Event.actionCallTimeout:
          _actions.add(CallKitAction.timeout);
          _activeCallId = null;
          break;
        default:
          break;
      }
    });
  }

  Future<void> endCall() async {
    if (_activeCallId != null) {
      await FlutterCallkitIncoming.endCall(_activeCallId!);
      _activeCallId = null;
    }
  }

  Future<void> endAllCalls() async {
    await FlutterCallkitIncoming.endAllCalls();
    _activeCallId = null;
  }

  void dispose() {
    _eventSub?.cancel();
    _actions.close();
  }
}

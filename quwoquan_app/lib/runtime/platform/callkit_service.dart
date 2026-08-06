import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_callkit_incoming/entities/call_event.dart';
import 'package:flutter_callkit_incoming/flutter_callkit_incoming.dart';
import 'package:quwoquan_app/core/platform/incoming_call_envelope.dart';
import 'package:quwoquan_app/core/platform/incoming_call_native_bridge.dart';
import 'package:quwoquan_app/core/platform/incoming_call_native_presenter.dart';
import 'package:quwoquan_app/core/platform/official_call_ringtone_catalog.dart';

enum CallKitAction { accept, decline, end, timeout }

final class CallKitActionEvent {
  const CallKitActionEvent({required this.callId, required this.action});

  final String callId;
  final CallKitAction action;
}

/// `flutter_callkit_incoming` 的唯一平台防腐实现。
class CallKitService {
  CallKitService({
    Stream<CallEvent?>? eventStream,
    IncomingCallNativePresenter? presenter,
    IncomingCallNativeBridge? nativeBridge,
  }) : _eventStream = eventStream ?? FlutterCallkitIncoming.onEvent,
       _presenter = presenter ?? const CallKitIncomingNativePresenter(),
       _nativeBridge =
           nativeBridge ?? const MethodChannelIncomingCallNativeBridge();

  final Stream<CallEvent?> _eventStream;
  final IncomingCallNativePresenter _presenter;
  final IncomingCallNativeBridge _nativeBridge;
  StreamSubscription<CallEvent?>? _eventSub;
  final _actions = StreamController<CallKitActionEvent>.broadcast();
  bool _nativeEventStreamAvailable = true;

  Stream<CallKitActionEvent> get actions => _actions.stream;

  String? _activeCallId;
  String? get activeCallId => _activeCallId;
  @visibleForTesting
  bool get nativeEventStreamAvailable => _nativeEventStreamAvailable;

  Future<IncomingCallPresentationResult> showIncomingCall({
    required IncomingCallEnvelope envelope,
    String? ringtoneId,
  }) async {
    _activeCallId = envelope.callId;
    final ringtonePath = OfficialCallRingtoneCatalog.resolveCallkitPath(
      ringtoneId,
    );
    final capability = await _nativeBridge.readCapability();
    final result = await _presenter.present(
      envelope,
      fullScreenAllowed: capability.fullScreenPresentationAllowed,
      ringtonePath: ringtonePath,
    );
    if (!result.presented) {
      _activeCallId = null;
    }
    return result;
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

    switch (event) {
      case CallEventActionCallAccept(:final id):
        _actions.add(
          CallKitActionEvent(callId: id, action: CallKitAction.accept),
        );
      case CallEventActionCallDecline(:final id):
        _actions.add(
          CallKitActionEvent(callId: id, action: CallKitAction.decline),
        );
        _activeCallId = null;
      case CallEventActionCallEnded(:final id):
        _actions.add(CallKitActionEvent(callId: id, action: CallKitAction.end));
        _activeCallId = null;
      case CallEventActionCallTimeout(:final id):
        _actions.add(
          CallKitActionEvent(callId: id, action: CallKitAction.timeout),
        );
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
    return true;
  }

  Future<void> endCall(String callId) async {
    final normalized = callId.trim();
    if (normalized.isNotEmpty) {
      await _nativeBridge.endNativeCall(normalized);
    }
    if (_activeCallId == normalized) {
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

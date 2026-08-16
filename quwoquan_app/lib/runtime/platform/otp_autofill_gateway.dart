import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

typedef OtpAutofillCodeListener = void Function(String code);

abstract interface class OtpAutofillGateway {
  Future<void> start(OtpAutofillCodeListener onCode);
  void bindRequestRef(String requestRef);
  Future<void> stop();
}

OtpAutofillGateway createOtpAutofillGateway() {
  if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) {
    return MethodChannelSmsRetrieverOtpGateway();
  }
  // iOS uses the system oneTimeCode suggestion exposed by the text field.
  return const SystemOtpAutofillGateway();
}

final class SystemOtpAutofillGateway implements OtpAutofillGateway {
  const SystemOtpAutofillGateway();

  @override
  void bindRequestRef(String requestRef) {}

  @override
  Future<void> start(OtpAutofillCodeListener onCode) async {}

  @override
  Future<void> stop() async {}
}

final class MethodChannelSmsRetrieverOtpGateway implements OtpAutofillGateway {
  MethodChannelSmsRetrieverOtpGateway({
    this._channel = const MethodChannel('quwoquan/auth/sms_retriever'),
  });

  final MethodChannel _channel;
  OtpAutofillCodeListener? _onCode;
  String _requestRef = '';
  String _pendingMessage = '';
  String _lastAcceptedIdentity = '';

  @override
  Future<void> start(OtpAutofillCodeListener onCode) async {
    await stop();
    _onCode = onCode;
    _channel.setMethodCallHandler(_handleNativeCall);
    try {
      await _channel.invokeMethod<void>('start');
    } on MissingPluginException {
      // Manual input is the canonical fallback on devices without Retriever.
    } on PlatformException {
      // Retriever unavailability is intentionally silent to the user.
    }
  }

  @override
  void bindRequestRef(String requestRef) {
    _requestRef = requestRef.trim();
    _consume(_pendingMessage);
  }

  Future<void> _handleNativeCall(MethodCall call) async {
    if (call.method != 'smsRetrieved') return;
    final arguments = call.arguments;
    final message = arguments is Map
        ? arguments['message']?.toString() ?? ''
        : '';
    _pendingMessage = message;
    _consume(message);
  }

  void _consume(String message) {
    final parsed = parseSmsRetrieverOtp(
      message,
      expectedRequestRef: _requestRef,
    );
    if (parsed == null) return;
    final identity = '${parsed.requestRef}:${parsed.code}';
    if (identity == _lastAcceptedIdentity) return;
    _lastAcceptedIdentity = identity;
    _pendingMessage = '';
    _onCode?.call(parsed.code);
  }

  @override
  Future<void> stop() async {
    _onCode = null;
    _requestRef = '';
    _pendingMessage = '';
    _lastAcceptedIdentity = '';
    _channel.setMethodCallHandler(null);
    try {
      await _channel.invokeMethod<void>('stop');
    } on MissingPluginException {
      // No-op on unsupported test hosts.
    } on PlatformException {
      // Stopping is best-effort and never blocks manual entry.
    }
  }
}

class ParsedRetrieverOtp {
  const ParsedRetrieverOtp({required this.requestRef, required this.code});

  final String requestRef;
  final String code;
}

ParsedRetrieverOtp? parseSmsRetrieverOtp(
  String message, {
  required String expectedRequestRef,
}) {
  final expected = expectedRequestRef.trim();
  if (expected.isEmpty || message.isEmpty) return null;
  final requestMatch = RegExp(
    r'(?:requestRef|请求编号)\s*[:：]\s*([A-Za-z0-9_-]{8,96})',
  ).firstMatch(message);
  final requestRef = requestMatch?.group(1)?.trim() ?? '';
  if (requestRef != expected) return null;
  final codeMatches = RegExp(r'(^|\D)(\d{6})(?!\d)').allMatches(message);
  if (codeMatches.length != 1) return null;
  final code = codeMatches.single.group(2) ?? '';
  if (code.length != 6) return null;
  return ParsedRetrieverOtp(requestRef: requestRef, code: code);
}

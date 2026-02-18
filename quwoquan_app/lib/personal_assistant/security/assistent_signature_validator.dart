import 'dart:convert';

import 'package:crypto/crypto.dart';

enum AssistentSignatureMode {
  none,
  token,
  hmacSha256,
}

class AssistentSignaturePolicy {
  const AssistentSignaturePolicy({
    required this.mode,
    required this.secret,
    required this.signatureHeader,
    this.tokenHeader = '',
    this.timestampHeader = '',
    this.maxSkewSeconds = 300,
  });

  final AssistentSignatureMode mode;
  final String secret;
  final String signatureHeader;
  final String tokenHeader;
  final String timestampHeader;
  final int maxSkewSeconds;
}

class AssistentSignatureValidator {
  const AssistentSignatureValidator();

  bool validate({
    required AssistentSignaturePolicy policy,
    required Map<String, String> headers,
    required String rawBody,
  }) {
    switch (policy.mode) {
      case AssistentSignatureMode.none:
        return true;
      case AssistentSignatureMode.token:
        return _validateToken(policy: policy, headers: headers);
      case AssistentSignatureMode.hmacSha256:
        return _validateHmacSha256(
          policy: policy,
          headers: headers,
          rawBody: rawBody,
        );
    }
  }

  bool _validateToken({
    required AssistentSignaturePolicy policy,
    required Map<String, String> headers,
  }) {
    if (policy.secret.trim().isEmpty) return true;
    final headerName =
        policy.tokenHeader.trim().isEmpty ? policy.signatureHeader : policy.tokenHeader;
    final incoming = headers[headerName.toLowerCase()] ?? '';
    return _constantTimeEquals(incoming.trim(), policy.secret.trim());
  }

  bool _validateHmacSha256({
    required AssistentSignaturePolicy policy,
    required Map<String, String> headers,
    required String rawBody,
  }) {
    if (policy.secret.trim().isEmpty) return true;
    final incoming = headers[policy.signatureHeader.toLowerCase()] ?? '';
    if (incoming.trim().isEmpty) return false;
    var payload = rawBody;
    if (policy.timestampHeader.trim().isNotEmpty) {
      final ts = headers[policy.timestampHeader.toLowerCase()] ?? '';
      if (ts.isNotEmpty) {
        final tsInt = int.tryParse(ts);
        if (tsInt != null) {
          final nowSec = DateTime.now().millisecondsSinceEpoch ~/ 1000;
          final diff = (nowSec - tsInt).abs();
          if (diff > policy.maxSkewSeconds) return false;
        }
        payload = '$ts.$rawBody';
      }
    }
    final digest = Hmac(sha256, utf8.encode(policy.secret)).convert(utf8.encode(payload));
    final expected = digest.toString();
    return _constantTimeEquals(incoming.trim(), expected);
  }

  bool _constantTimeEquals(String a, String b) {
    final aa = utf8.encode(a);
    final bb = utf8.encode(b);
    if (aa.length != bb.length) return false;
    var result = 0;
    for (var i = 0; i < aa.length; i++) {
      result |= aa[i] ^ bb[i];
    }
    return result == 0;
  }
}


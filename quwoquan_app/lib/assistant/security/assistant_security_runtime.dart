import 'dart:convert';

import 'package:crypto/crypto.dart';

class AssistantAuditLog {
  const AssistantAuditLog({
    required this.event,
    required this.actor,
    required this.channel,
    required this.runId,
    required this.traceId,
    required this.statusCode,
    required this.timestamp,
    this.metadata = const <String, dynamic>{},
  });

  final String event;
  final String actor;
  final String channel;
  final String runId;
  final String traceId;
  final int statusCode;
  final DateTime timestamp;
  final Map<String, dynamic> metadata;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'event': event,
      'actor': actor,
      'channel': channel,
      'runId': runId,
      'traceId': traceId,
      'statusCode': statusCode,
      'timestamp': timestamp.toIso8601String(),
      'metadata': metadata,
    };
  }
}

class AssistantAuditLogger {
  final List<AssistantAuditLog> _logs = <AssistantAuditLog>[];

  Future<void> write(AssistantAuditLog log) async {
    _logs.add(log);
  }

  Future<List<AssistantAuditLog>> recent({int limit = 200}) async {
    if (_logs.length <= limit) {
      return List<AssistantAuditLog>.from(_logs.reversed);
    }
    final start = _logs.length - limit;
    return _logs.sublist(start).reversed.toList(growable: false);
  }
}

class AssistantAccessContext {
  const AssistantAccessContext({
    required this.channel,
    required this.actorId,
    required this.resource,
    required this.action,
  });

  final String channel;
  final String actorId;
  final String resource;
  final String action;
}

class AssistantAuthAcl {
  const AssistantAuthAcl();

  bool allow(AssistantAccessContext context) {
    if (context.actorId.trim().isEmpty) return false;
    if (context.resource.trim().isEmpty) return false;
    if (context.action.trim().isEmpty) return false;
    return true;
  }
}

enum AssistantSignatureMode {
  none,
  token,
  hmacSha256,
}

class AssistantSignaturePolicy {
  const AssistantSignaturePolicy({
    required this.mode,
    required this.secret,
    required this.signatureHeader,
    this.tokenHeader = '',
    this.timestampHeader = '',
    this.maxSkewSeconds = 300,
  });

  final AssistantSignatureMode mode;
  final String secret;
  final String signatureHeader;
  final String tokenHeader;
  final String timestampHeader;
  final int maxSkewSeconds;
}

class AssistantSignatureValidator {
  const AssistantSignatureValidator();

  bool validate({
    required AssistantSignaturePolicy policy,
    required Map<String, String> headers,
    required String rawBody,
  }) {
    switch (policy.mode) {
      case AssistantSignatureMode.none:
        return true;
      case AssistantSignatureMode.token:
        return _validateToken(policy: policy, headers: headers);
      case AssistantSignatureMode.hmacSha256:
        return _validateHmacSha256(
          policy: policy,
          headers: headers,
          rawBody: rawBody,
        );
    }
  }

  bool _validateToken({
    required AssistantSignaturePolicy policy,
    required Map<String, String> headers,
  }) {
    if (policy.secret.trim().isEmpty) return true;
    final headerName = policy.tokenHeader.trim().isEmpty
        ? policy.signatureHeader
        : policy.tokenHeader;
    final incoming = headers[headerName.toLowerCase()] ?? '';
    return _constantTimeEquals(incoming.trim(), policy.secret.trim());
  }

  bool _validateHmacSha256({
    required AssistantSignaturePolicy policy,
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
    final digest = Hmac(
      sha256,
      utf8.encode(policy.secret),
    ).convert(utf8.encode(payload));
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

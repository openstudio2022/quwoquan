import 'dart:convert';

import 'package:crypto/crypto.dart';

class DomainConfigGovernance {
  const DomainConfigGovernance({
    this.defaultSignKeyId = 'domain-config-key-1',
    this.signSecret = const String.fromEnvironment(
      'ASSISTANT_DOMAIN_CONFIG_SIGN_SECRET',
      defaultValue: '',
    ),
  });

  final String defaultSignKeyId;
  final String signSecret;

  bool verifyEnvelopeSignature(Map<String, dynamic> envelope) {
    if (signSecret.trim().isEmpty) return false;
    final signature = (envelope['signature'] as String?)?.trim() ?? '';
    if (signature.isEmpty) return false;
    final keyId = (envelope['keyId'] as String?)?.trim().isNotEmpty == true
        ? (envelope['keyId'] as String).trim()
        : defaultSignKeyId;
    String payload = (envelope['payload'] as String?)?.trim() ?? '';
    if (payload.isEmpty) {
      final catalog = envelope['catalog'];
      if (catalog is Map) {
        payload = jsonEncode(catalog);
      }
    }
    if (payload.isEmpty) return false;
    final expected = Hmac(
      sha256,
      utf8.encode(signSecret),
    ).convert(utf8.encode('$keyId|$payload'));
    return expected.toString() == signature;
  }

  bool allowByGrayRelease({
    required Map<String, dynamic> envelope,
    required Map<String, dynamic> contextScopeHint,
  }) {
    final gray =
        (envelope['grayRelease'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    if (gray['enabled'] != true) return true;
    final start = (gray['bucketStart'] as num?)?.toInt() ?? 0;
    final end = (gray['bucketEnd'] as num?)?.toInt() ?? 99;
    final bucketKeyName =
        (gray['bucketKey'] as String?)?.trim().isNotEmpty == true
        ? (gray['bucketKey'] as String).trim()
        : 'sessionId';
    final rawKey =
        (contextScopeHint[bucketKeyName] as String?)?.trim().isNotEmpty == true
        ? (contextScopeHint[bucketKeyName] as String).trim()
        : (contextScopeHint['sessionId'] as String?)?.trim() ?? 'default';
    final bucket = _computeBucket(rawKey);
    return bucket >= start && bucket <= end;
  }

  int _computeBucket(String rawKey) {
    final digest = sha256.convert(utf8.encode(rawKey));
    final hex = digest.toString();
    final prefix = hex.substring(0, 8);
    final numValue = int.tryParse(prefix, radix: 16) ?? 0;
    return numValue % 100;
  }
}

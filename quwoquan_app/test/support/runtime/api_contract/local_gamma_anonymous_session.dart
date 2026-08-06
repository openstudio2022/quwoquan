import 'dart:convert';

import 'package:http/http.dart' as http;

/// Short-lived, runtime-only identity for a local Gamma API contract run.
///
/// The session comes from the public anonymous-login boundary. Tests must not
/// inject account or persona headers because the gateway owns that derivation.
class LocalGammaAnonymousSession {
  const LocalGammaAnonymousSession({
    required this.accessToken,
    required this.refreshToken,
    required this.ownerId,
    required this.personaId,
  });

  final String accessToken;
  final String refreshToken;
  final String ownerId;
  final String personaId;

  String get authorizationHeader => 'Bearer $accessToken';

  static Future<LocalGammaAnonymousSession> login({
    required http.Client client,
    required String baseUrl,
    required String subject,
  }) async {
    final response = await client
        .post(
          Uri.parse(
            '${baseUrl.replaceFirst(RegExp(r'/$'), '')}/auth/login/anonymous',
          ),
          headers: const {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
          },
          body: jsonEncode({
            'installId': 'api-contract-$subject',
            'deviceFingerprintHash': 'api-contract-$subject',
            'platform': 'api-contract',
            'appVersion': 'local-e2e',
          }),
        )
        .timeout(const Duration(seconds: 10));
    if (response.statusCode != 200) {
      throw StateError(
        'anonymous login returned HTTP ${response.statusCode}: ${response.body}',
      );
    }
    final decoded = jsonDecode(response.body);
    if (decoded is! Map<String, Object?>) {
      throw StateError('anonymous login returned a non-object payload');
    }
    final activePersona = decoded['activePersona'];
    if (activePersona is! Map<String, Object?>) {
      throw StateError('anonymous login omitted activePersona');
    }
    return LocalGammaAnonymousSession(
      accessToken: _requiredString(decoded, 'accessToken'),
      refreshToken: _requiredString(decoded, 'refreshToken'),
      ownerId: _requiredString(decoded, 'ownerId'),
      personaId: _requiredString(activePersona, 'personaId'),
    );
  }

  static String _requiredString(Map<String, Object?> value, String field) {
    final raw = value[field];
    if (raw is! String || raw.trim().isEmpty) {
      throw StateError('anonymous login omitted $field');
    }
    return raw.trim();
  }
}

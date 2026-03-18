import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_request_page_ids.g.dart';
import 'package:shared_preferences/shared_preferences.dart';

const String kPersonalContentAccessSkillId = 'personal_content_access';

class AssistantSkillConsent {
  const AssistantSkillConsent({
    required this.skillId,
    required this.grantedScope,
    required this.granted,
    required this.updatedAt,
  });

  final String skillId;
  final String grantedScope;
  final bool granted;
  final DateTime updatedAt;

  factory AssistantSkillConsent.fromJson(Map<String, dynamic> json) {
    final revokedAt = (json['revokedAt'] ?? json['revoked_at'] ?? '')
        .toString()
        .trim();
    return AssistantSkillConsent(
      skillId: (json['skillId'] ?? json['skill_id'] ?? '').toString().trim(),
      grantedScope:
          (json['grantedScope'] ??
                  json['granted_scope'] ??
                  json['scope'] ??
                  kPersonalContentAccessSkillId)
              .toString()
              .trim(),
      granted: json['granted'] == true || revokedAt.isEmpty,
      updatedAt:
          DateTime.tryParse(
            (json['updatedAt'] ?? json['updated_at'] ?? json['grantedAt'] ?? '')
                .toString(),
          ) ??
          DateTime.now(),
    );
  }

  Map<String, dynamic> toJson() => <String, dynamic>{
    'skillId': skillId,
    'grantedScope': grantedScope,
    'granted': granted,
    'updatedAt': updatedAt.toIso8601String(),
  };
}

abstract class AssistantRepository {
  Future<List<AssistantSkillConsent>> listConsents();

  Future<AssistantSkillConsent> grantSkillConsent({
    required String skillId,
    String grantedScope = kPersonalContentAccessSkillId,
  });

  Future<void> revokeSkillConsent({required String skillId});
}

class MockAssistantRepository implements AssistantRepository {
  MockAssistantRepository({AssistantConsentStore? store})
    : _store = store ?? const AssistantConsentStore();

  final AssistantConsentStore _store;

  @override
  Future<List<AssistantSkillConsent>> listConsents() {
    return _store.load();
  }

  @override
  Future<AssistantSkillConsent> grantSkillConsent({
    required String skillId,
    String grantedScope = kPersonalContentAccessSkillId,
  }) async {
    final consent = AssistantSkillConsent(
      skillId: skillId,
      grantedScope: grantedScope,
      granted: true,
      updatedAt: DateTime.now(),
    );
    await _store.upsert(consent);
    return consent;
  }

  @override
  Future<void> revokeSkillConsent({required String skillId}) {
    return _store.revoke(skillId);
  }
}

class RemoteAssistantRepository implements AssistantRepository {
  RemoteAssistantRepository({
    http.Client? client,
    AssistantConsentStore? store,
  }) : _client = client ?? http.Client(),
       _store = store ?? const AssistantConsentStore();

  final http.Client _client;
  final AssistantConsentStore _store;

  @override
  Future<List<AssistantSkillConsent>> listConsents() async {
    final local = await _store.load();
    try {
      final uri = _assistantUri(AssistantApiMetadata.listConsentsPath);
      final response = await _client.get(
        uri,
        headers: CloudRequestHeaders.forPage(
          AssistantRequestPageIds.listConsents,
        ),
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        return local;
      }
      final decoded = jsonDecode(response.body);
      final object = decoded is List
          ? <String, dynamic>{'items': decoded}
          : CloudResponseDecoder.asObject(
              decoded,
              context: AssistantRequestPageIds.listConsents,
            );
      final rawItems =
          (object['items'] as List?)
              ?.whereType<Map>()
              .map((item) => item.cast<String, dynamic>())
              .toList(growable: false) ??
          const <Map<String, dynamic>>[];
      final consents = rawItems
          .map(AssistantSkillConsent.fromJson)
          .where((item) => item.skillId.isNotEmpty)
          .toList(growable: false);
      await _store.save(consents);
      return consents;
    } catch (_) {
      return local;
    }
  }

  @override
  Future<AssistantSkillConsent> grantSkillConsent({
    required String skillId,
    String grantedScope = kPersonalContentAccessSkillId,
  }) async {
    final fallback = AssistantSkillConsent(
      skillId: skillId,
      grantedScope: grantedScope,
      granted: true,
      updatedAt: DateTime.now(),
    );
    try {
      final uri = _assistantUri(
        AssistantApiMetadata.grantSkillConsentPath(skillId: skillId),
      );
      final response = await _client.post(
        uri,
        headers: <String, String>{
          ...CloudRequestHeaders.forPage(
            AssistantRequestPageIds.grantSkillConsent,
          ),
          'Content-Type': 'application/json',
        },
        body: jsonEncode(<String, dynamic>{'grantedScope': grantedScope}),
      );
      if (response.statusCode >= 200 && response.statusCode < 300) {
        final consent = _decodeConsentResponse(
          response.body,
          fallback: fallback,
          context: AssistantRequestPageIds.grantSkillConsent,
        );
        await _store.upsert(consent);
        return consent;
      }
    } catch (_) {
      // Fall back to local persistence when assistant-service is unavailable.
    }
    await _store.upsert(fallback);
    return fallback;
  }

  @override
  Future<void> revokeSkillConsent({required String skillId}) async {
    try {
      final uri = _assistantUri(
        AssistantApiMetadata.revokeSkillConsentPath(skillId: skillId),
      );
      await _client.delete(
        uri,
        headers: CloudRequestHeaders.forPage(
          AssistantRequestPageIds.revokeSkillConsent,
        ),
      );
    } catch (_) {
      // Local revoke still applies when assistant-service is unavailable.
    }
    await _store.revoke(skillId);
  }

  Uri _assistantUri(String path) {
    return Uri.parse('${CloudRuntimeConfig.gatewayBaseUrl}$path');
  }

  AssistantSkillConsent _decodeConsentResponse(
    String body, {
    required AssistantSkillConsent fallback,
    required String context,
  }) {
    if (body.trim().isEmpty) {
      return fallback;
    }
    final decoded = jsonDecode(body);
    final object = CloudResponseDecoder.asObject(decoded, context: context);
    final payload =
        (object['consent'] as Map?)?.cast<String, dynamic>() ?? object;
    final consent = AssistantSkillConsent.fromJson(payload);
    return consent.skillId.isEmpty ? fallback : consent;
  }
}

class AssistantConsentStore {
  const AssistantConsentStore();

  static const String _key = 'assistant_skill_consents_v1';

  Future<List<AssistantSkillConsent>> load() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_key);
    if (raw == null || raw.trim().isEmpty) {
      return const <AssistantSkillConsent>[];
    }
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! List) {
        return const <AssistantSkillConsent>[];
      }
      return decoded
          .whereType<Map>()
          .map(
            (item) =>
                AssistantSkillConsent.fromJson(item.cast<String, dynamic>()),
          )
          .where((item) => item.skillId.isNotEmpty)
          .toList(growable: false);
    } catch (_) {
      return const <AssistantSkillConsent>[];
    }
  }

  Future<void> save(List<AssistantSkillConsent> items) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      _key,
      jsonEncode(items.map((item) => item.toJson()).toList(growable: false)),
    );
  }

  Future<void> upsert(AssistantSkillConsent next) async {
    final current = await load();
    final merged = <AssistantSkillConsent>[
      for (final item in current)
        if (item.skillId != next.skillId) item,
      next,
    ];
    await save(merged);
  }

  Future<void> revoke(String skillId) async {
    final current = await load();
    final next = current
        .where((item) => item.skillId != skillId)
        .toList(growable: false);
    await save(next);
  }
}

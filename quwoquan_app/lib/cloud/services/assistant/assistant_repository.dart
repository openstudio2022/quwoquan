import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
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

class AssistantSearchCitationView {
  const AssistantSearchCitationView({
    required this.citationId,
    required this.objectType,
    required this.objectId,
    required this.title,
    this.contentType,
    this.snippet,
    this.coverUrl,
    this.badgeLabel,
    this.sourceDomain,
  });

  final String citationId;
  final String objectType;
  final String objectId;
  final String title;
  final String? contentType;
  final String? snippet;
  final String? coverUrl;
  final String? badgeLabel;
  final String? sourceDomain;

  factory AssistantSearchCitationView.fromJson(Map<String, dynamic> json) {
    return AssistantSearchCitationView(
      citationId: (json['citationId'] ?? '').toString().trim(),
      objectType: (json['objectType'] ?? '').toString().trim(),
      objectId: (json['objectId'] ?? '').toString().trim(),
      title: (json['title'] ?? '').toString().trim(),
      contentType: json['contentType']?.toString(),
      snippet: json['snippet']?.toString(),
      coverUrl: json['coverUrl']?.toString(),
      badgeLabel: json['badgeLabel']?.toString(),
      sourceDomain: json['sourceDomain']?.toString(),
    );
  }
}

class AssistantSearchResultView {
  const AssistantSearchResultView({
    required this.queryEcho,
    this.summary,
    this.searchIntensity,
    this.citations = const <AssistantSearchCitationView>[],
  });

  final String queryEcho;
  final String? summary;
  final String? searchIntensity;
  final List<AssistantSearchCitationView> citations;

  factory AssistantSearchResultView.fromJson(Map<String, dynamic> json) {
    final rawCitations =
        (json['citations'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    return AssistantSearchResultView(
      queryEcho: (json['queryEcho'] ?? json['userQuery'] ?? '')
          .toString()
          .trim(),
      summary: json['summary']?.toString(),
      searchIntensity: json['searchIntensity']?.toString(),
      citations: rawCitations
          .map(AssistantSearchCitationView.fromJson)
          .where((item) => item.citationId.isNotEmpty || item.title.isNotEmpty)
          .toList(growable: false),
    );
  }
}

AssistantSearchResultView _buildFallbackSearchResult({
  required String query,
  required String searchIntensity,
}) {
  final trimmedQuery = query.trim();
  final summary = trimmedQuery.isEmpty
      ? '小趣搜会结合圈子频道结果和已有公开内容，为你梳理当前最相关的线索。'
      : '小趣搜正在整理“$trimmedQuery”的公开线索，会优先总结当前最相关的话题、圈子频道与内容方向。';
  return AssistantSearchResultView(
    queryEcho: trimmedQuery,
    summary: summary,
    searchIntensity: searchIntensity,
    citations: const <AssistantSearchCitationView>[],
  );
}

abstract class AssistantRepository {
  Future<List<AssistantSkillConsent>> listConsents();

  Future<AssistantSkillConsent> grantSkillConsent({
    required String skillId,
    String grantedScope = kPersonalContentAccessSkillId,
  });

  Future<void> revokeSkillConsent({required String skillId});

  Future<AssistantSearchResultView> searchXiaoquResults({
    required String query,
    String searchIntensity = 'balanced',
  });
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

  @override
  Future<AssistantSearchResultView> searchXiaoquResults({
    required String query,
    String searchIntensity = 'balanced',
  }) async {
    return _buildFallbackSearchResult(
      query: query,
      searchIntensity: searchIntensity,
    );
  }
}

class RemoteAssistantRepository implements AssistantRepository {
  RemoteAssistantRepository({http.Client? client, AssistantConsentStore? store})
    : _client = client ?? http.Client(),
      _store = store ?? const AssistantConsentStore();

  final http.Client _client;
  final AssistantConsentStore _store;

  Map<String, String> _headersForSettings({
    required String operationId,
    required String legacyPageId,
  }) {
    return CloudRequestHeaders.forSurfaceOperation(
      surfaceId: AppUiSurfaces.assistantSettings.id,
      routeId: AppUiSurfaces.assistantSettings.routeId,
      operationId: operationId,
      legacyPageId: legacyPageId,
    );
  }

  String _settingsContext({required String operationId}) {
    return CloudRequestHeaders.contextForSurfaceOperation(
      surfaceId: AppUiSurfaces.assistantSettings.id,
      operationId: operationId,
    );
  }

  Map<String, String> _headersForNetworkResults({required String operationId}) {
    return CloudRequestHeaders.forSurfaceOperation(
      surfaceId: AppUiSurfaces.globalSearchNetworkResults.id,
      routeId: AppUiSurfaces.globalSearchNetworkResults.routeId,
      operationId: operationId,
      legacyPageId: AssistantRequestPageIds.searchXiaoquResults,
    );
  }

  String _networkResultsContext({required String operationId}) {
    return CloudRequestHeaders.contextForSurfaceOperation(
      surfaceId: AppUiSurfaces.globalSearchNetworkResults.id,
      operationId: operationId,
    );
  }

  @override
  Future<List<AssistantSkillConsent>> listConsents() async {
    final local = await _store.load();
    try {
      final uri = _assistantUri(AssistantApiMetadata.listConsentsPath);
      final response = await _client.get(
        uri,
        headers: _headersForSettings(
          operationId: AssistantApiMetadata.listConsentsOperation,
          legacyPageId: AssistantRequestPageIds.listConsents,
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
              context: _settingsContext(
                operationId: AssistantApiMetadata.listConsentsOperation,
              ),
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
          ..._headersForSettings(
            operationId: AssistantApiMetadata.grantSkillConsentOperation,
            legacyPageId: AssistantRequestPageIds.grantSkillConsent,
          ),
          'Content-Type': 'application/json',
        },
        body: jsonEncode(<String, dynamic>{'grantedScope': grantedScope}),
      );
      if (response.statusCode >= 200 && response.statusCode < 300) {
        final consent = _decodeConsentResponse(
          response.body,
          fallback: fallback,
          context: _settingsContext(
            operationId: AssistantApiMetadata.grantSkillConsentOperation,
          ),
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
        headers: _headersForSettings(
          operationId: AssistantApiMetadata.revokeSkillConsentOperation,
          legacyPageId: AssistantRequestPageIds.revokeSkillConsent,
        ),
      );
    } catch (_) {
      // Local revoke still applies when assistant-service is unavailable.
    }
    await _store.revoke(skillId);
  }

  @override
  Future<AssistantSearchResultView> searchXiaoquResults({
    required String query,
    String searchIntensity = 'balanced',
  }) async {
    final trimmedQuery = query.trim();
    if (trimmedQuery.isEmpty) {
      return _buildFallbackSearchResult(
        query: query,
        searchIntensity: searchIntensity,
      );
    }
    try {
      final uri = _assistantUri(AssistantApiMetadata.searchXiaoquResultsPath);
      final response = await _client.post(
        uri,
        headers: <String, String>{
          ..._headersForNetworkResults(
            operationId: AssistantApiMetadata.searchXiaoquResultsOperation,
          ),
          'Content-Type': 'application/json',
        },
        body: jsonEncode(<String, dynamic>{
          'userQuery': trimmedQuery,
          'searchIntensity': searchIntensity,
          'sourceSurfaceId': AppUiSurfaces.globalSearchNetworkResults.id,
          'fromGlobalSearch': true,
        }),
      );
      if (response.statusCode >= 200 && response.statusCode < 300) {
        final decoded = response.body.trim().isEmpty
            ? <String, dynamic>{}
            : CloudResponseDecoder.asObject(
                jsonDecode(response.body),
                context: _networkResultsContext(
                  operationId:
                      AssistantApiMetadata.searchXiaoquResultsOperation,
                ),
              );
        final result = AssistantSearchResultView.fromJson(decoded);
        if (result.queryEcho.isNotEmpty ||
            result.summary?.trim().isNotEmpty == true) {
          return result;
        }
      }
    } catch (_) {
      // Fall back to local synthesis when assistant-service is unavailable.
    }
    return _buildFallbackSearchResult(
      query: trimmedQuery,
      searchIntensity: searchIntensity,
    );
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

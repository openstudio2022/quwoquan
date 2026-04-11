import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_cloud_api_wire.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_request_page_ids.g.dart';
import 'package:quwoquan_app/core/models/app_content_prototype_models.dart';
import 'package:quwoquan_app/cloud/services/app_content/app_content_prototype_codec.dart';

export 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_cloud_api_wire.g.dart'
    show
        AssistantCreateRunRequestWire,
        AssistantInteractionReportBatchAck,
        AssistantPolicyView,
        AssistantReportPageContextRequestWire,
        AssistantScorecardReportBatchAck,
        AssistantSearchCitationView,
        AssistantSearchResultView,
        AssistantSearchXiaoquRequestWire,
        AssistantSkillCatalogItemView,
        AssistantUserMemoryView,
        AssistantUserTaskView,
        InteractionEvent,
        Scorecard;
import 'package:shared_preferences/shared_preferences.dart';

const String kPersonalContentAccessSkillId = 'personal_content_access';

/// Assistant 任务/记忆等列表接口单次拉取条数（与网关约定一致，非 [CloudApiDefaults.pageLimit]）。
const int _kAssistantListPageDefaultLimit = 32;

/// Assistant 技能目录单次拉取条数。
const int _kAssistantSkillCatalogDefaultLimit = 64;

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
  Future<AssistantPolicyView> getPolicySnapshot({
    String policyVersionHint = '',
  });

  Future<AssistantInteractionReportBatchAck> reportInteractionEvents({
    required List<InteractionEvent> events,
  });

  Future<AssistantScorecardReportBatchAck> reportScorecards({
    required List<Scorecard> scorecards,
  });

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

  /// GET /v1/assistant/tasks
  Future<List<AssistantUserTaskView>> listAssistantTasks({
    int limit = _kAssistantListPageDefaultLimit,
    String? status,
  });

  /// GET /v1/assistant/memories
  Future<List<AssistantUserMemoryView>> listAssistantMemories({
    int limit = _kAssistantListPageDefaultLimit,
  });

  /// GET /v1/assistant/skills
  Future<List<AssistantSkillCatalogItemView>> listSkillCatalog({
    int limit = _kAssistantSkillCatalogDefaultLimit,
  });
}

class MockAssistantRepository implements AssistantRepository {
  MockAssistantRepository({AssistantConsentStore? store})
    : _store = store ?? const AssistantConsentStore();

  final AssistantConsentStore _store;

  @override
  Future<AssistantPolicyView> getPolicySnapshot({
    String policyVersionHint = '',
  }) async {
    return AssistantPolicyView(
      version: policyVersionHint.trim().isEmpty
          ? 'assistant_policy_local_mock_v1'
          : policyVersionHint.trim(),
      values: <String, dynamic>{
        'learningSyncEnabled': false,
        'suggestedActionsEnabled': true,
        'pageContextTtlSeconds': 300,
        'searchFallbackMode': 'local_mock',
        'defaultSearchIntensity': 'balanced',
      },
    );
  }

  @override
  Future<AssistantInteractionReportBatchAck> reportInteractionEvents({
    required List<InteractionEvent> events,
  }) async {
    return AssistantInteractionReportBatchAck(
      accepted: true,
      count: events.length,
      resource: 'interaction_event_batch',
      mode: 'local_mock',
    );
  }

  @override
  Future<AssistantScorecardReportBatchAck> reportScorecards({
    required List<Scorecard> scorecards,
  }) async {
    return AssistantScorecardReportBatchAck(
      accepted: true,
      count: scorecards.length,
      resource: 'scorecard_batch',
      mode: 'local_mock',
    );
  }

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

  @override
  Future<List<AssistantUserTaskView>> listAssistantTasks({
    int limit = _kAssistantListPageDefaultLimit,
    String? status,
  }) async {
    final raw = AppContentPrototypeBundle.instance.assistantTasksData;
    Iterable<AssistantPrototypeTaskRow> rows = raw;
    if (status != null && status.trim().isNotEmpty) {
      rows = raw.where((row) => row.status == status.trim());
    }
    return rows
        .map((row) {
          final time = row.time ?? '';
          final category = row.category ?? '';
          final desc = <String>[
            if (time.isNotEmpty) time,
            if (category.isNotEmpty) category,
          ].join(' · ');
          return AssistantUserTaskView(
            taskId: row.taskKey,
            title: row.title,
            description: desc.isEmpty ? null : desc,
            status: row.status,
          );
        })
        .take(limit)
        .toList(growable: false);
  }

  @override
  Future<List<AssistantUserMemoryView>> listAssistantMemories({
    int limit = _kAssistantListPageDefaultLimit,
  }) async {
    return AppContentPrototypeBundle.instance.assistantMemoryData
        .map(
          (row) => AssistantUserMemoryView(
            memoryId: row.memoryKey,
            title: row.title,
            snippet: row.kind,
            sourceType: row.kind,
          ),
        )
        .take(limit)
        .toList(growable: false);
  }

  @override
  Future<List<AssistantSkillCatalogItemView>> listSkillCatalog({
    int limit = _kAssistantSkillCatalogDefaultLimit,
  }) async {
    return AppContentPrototypeBundle.instance.assistantSkillsData
        .map(
          (row) => AssistantSkillCatalogItemView(
            skillId: row.skillId,
            displayName: row.name,
            description: row.description,
            requiresConsent: false,
          ),
        )
        .take(limit)
        .toList(growable: false);
  }
}

class RemoteAssistantRepository implements AssistantRepository {
  RemoteAssistantRepository({http.Client? client, AssistantConsentStore? store})
    : _client = client ?? http.Client(),
      _store = store ?? const AssistantConsentStore();

  final http.Client _client;
  final AssistantConsentStore _store;

  @override
  Future<AssistantPolicyView> getPolicySnapshot({
    String policyVersionHint = '',
  }) async {
    try {
      final uri = _assistantGetUri(AssistantApiMetadata.getPolicyPath, {
        if (policyVersionHint.trim().isNotEmpty)
          'policyVersionHint': policyVersionHint.trim(),
      });
      final response = await _client.get(
        uri,
        headers: _headersForAssistantDialog(
          operationId: AssistantApiMetadata.getPolicyOperation,
          clientPageId: AssistantRequestPageIds.getPolicy,
        ),
      );
      if (response.statusCode >= 200 && response.statusCode < 300) {
        final decoded = response.body.trim().isEmpty
            ? <String, dynamic>{}
            : CloudResponseDecoder.asObject(
                jsonDecode(response.body),
                context: _assistantDialogContext(
                  operationId: AssistantApiMetadata.getPolicyOperation,
                ),
              );
        if (decoded.isNotEmpty) {
          return AssistantPolicyView.fromJson(decoded);
        }
      }
    } catch (_) {
      // Fall back to a safe default snapshot when assistant-service is unavailable.
    }
    return AssistantPolicyView(
      version: policyVersionHint.trim().isEmpty
          ? 'assistant_policy_remote_fallback_v1'
          : policyVersionHint.trim(),
      values: <String, dynamic>{
        'learningSyncEnabled': true,
        'suggestedActionsEnabled': true,
        'pageContextTtlSeconds': 300,
        'searchFallbackMode': 'summary_with_citations',
        'defaultSearchIntensity': 'balanced',
      },
    );
  }

  @override
  Future<AssistantInteractionReportBatchAck> reportInteractionEvents({
    required List<InteractionEvent> events,
  }) async {
    final accepted = <InteractionEvent>[];
    for (final event in events) {
      final eventId = event.eventId.trim();
      final runId = event.runId.trim();
      if (eventId.isEmpty || runId.isEmpty) {
        continue;
      }
      try {
        final uri = _assistantUri(
          AssistantApiMetadata.reportInteractionEventPath,
        );
        final response = await _client.post(
          uri,
          headers: <String, String>{
            ..._headersForAssistantDialog(
              operationId: AssistantApiMetadata.reportInteractionEventOperation,
              clientPageId: AssistantRequestPageIds.reportInteractionEvent,
            ),
            'Content-Type': 'application/json',
          },
          body: jsonEncode(event.toJson()),
        );
        if (response.statusCode >= 200 && response.statusCode < 300) {
          accepted.add(event);
        }
      } catch (_) {
        // Best effort: keep batch partial-success semantics.
      }
    }
    return AssistantInteractionReportBatchAck.fromJson(<String, dynamic>{
      'accepted': accepted.length == events.length,
      'acceptedCount': accepted.length,
      'count': events.length,
      'resource': 'interaction_event_batch',
    });
  }

  @override
  Future<AssistantScorecardReportBatchAck> reportScorecards({
    required List<Scorecard> scorecards,
  }) async {
    final accepted = <Scorecard>[];
    for (final scorecard in scorecards) {
      final scoreId = scorecard.scoreId.trim();
      final eventId = scorecard.eventId.trim();
      if (scoreId.isEmpty || eventId.isEmpty) {
        continue;
      }
      try {
        final uri = _assistantUri(AssistantApiMetadata.reportScorecardPath);
        final response = await _client.post(
          uri,
          headers: <String, String>{
            ..._headersForAssistantDialog(
              operationId: AssistantApiMetadata.reportScorecardOperation,
              clientPageId: AssistantRequestPageIds.reportScorecard,
            ),
            'Content-Type': 'application/json',
          },
          body: jsonEncode(scorecard.toJson()),
        );
        if (response.statusCode >= 200 && response.statusCode < 300) {
          accepted.add(scorecard);
        }
      } catch (_) {
        // Best effort: keep batch partial-success semantics.
      }
    }
    return AssistantScorecardReportBatchAck.fromJson(<String, dynamic>{
      'accepted': accepted.length == scorecards.length,
      'acceptedCount': accepted.length,
      'count': scorecards.length,
      'resource': 'scorecard_batch',
    });
  }

  Map<String, String> _headersForSettings({
    required String operationId,
    required String clientPageId,
  }) {
    return CloudRequestHeaders.forSurfaceOperation(
      surfaceId: AppUiSurfaces.assistantSettings.id,
      routeId: AppUiSurfaces.assistantSettings.routeId,
      operationId: operationId,
      clientPageId: clientPageId,
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
      clientPageId: AssistantRequestPageIds.searchXiaoquResults,
    );
  }

  String _networkResultsContext({required String operationId}) {
    return CloudRequestHeaders.contextForSurfaceOperation(
      surfaceId: AppUiSurfaces.globalSearchNetworkResults.id,
      operationId: operationId,
    );
  }

  Map<String, String> _headersForAssistantDialog({
    required String operationId,
    required String clientPageId,
  }) {
    return CloudRequestHeaders.forSurfaceOperation(
      surfaceId: AppUiSurfaces.assistantDialog.id,
      routeId: AppUiSurfaces.assistantDialog.routeId,
      operationId: operationId,
      clientPageId: clientPageId,
    );
  }

  String _assistantDialogContext({required String operationId}) {
    return CloudRequestHeaders.contextForSurfaceOperation(
      surfaceId: AppUiSurfaces.assistantDialog.id,
      operationId: operationId,
    );
  }

  Uri _assistantGetUri(String path, Map<String, String> query) {
    final base = Uri.parse('${CloudRuntimeConfig.gatewayBaseUrl}$path');
    if (query.isEmpty) {
      return base;
    }
    return base.replace(
      queryParameters: <String, String>{
        for (final e in query.entries)
          if (e.value.isNotEmpty) e.key: e.value,
      },
    );
  }

  List<Map<String, dynamic>> _decodeItemsMap(
    Object? decoded, {
    required String context,
  }) {
    if (decoded is List) {
      return decoded
          .whereType<Map>()
          .map((row) => row.cast<String, dynamic>())
          .toList(growable: false);
    }
    final object = CloudResponseDecoder.asObject(decoded, context: context);
    final raw =
        (object['items'] as List?)
            ?.whereType<Map>()
            .map((row) => row.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    return raw;
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
          clientPageId: AssistantRequestPageIds.listConsents,
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
            clientPageId: AssistantRequestPageIds.grantSkillConsent,
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
          clientPageId: AssistantRequestPageIds.revokeSkillConsent,
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
        body: jsonEncode(
          AssistantSearchXiaoquRequestWire(
            userQuery: trimmedQuery,
            searchIntensity: searchIntensity,
            sourceSurfaceId: AppUiSurfaces.globalSearchNetworkResults.id,
            fromGlobalSearch: true,
          ).toJson(),
        ),
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

  @override
  Future<List<AssistantUserTaskView>> listAssistantTasks({
    int limit = _kAssistantListPageDefaultLimit,
    String? status,
  }) async {
    try {
      final uri =
          _assistantGetUri(AssistantApiMetadata.listAssistantTasksPath, {
            'limit': '$limit',
            if (status != null && status.trim().isNotEmpty)
              'status': status.trim(),
          });
      final response = await _client.get(
        uri,
        headers: _headersForAssistantDialog(
          operationId: AssistantApiMetadata.listAssistantTasksOperation,
          clientPageId: AssistantRequestPageIds.listAssistantTasks,
        ),
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        return const <AssistantUserTaskView>[];
      }
      final decoded = response.body.trim().isEmpty
          ? <String, dynamic>{}
          : jsonDecode(response.body);
      final rows = _decodeItemsMap(
        decoded,
        context: _assistantDialogContext(
          operationId: AssistantApiMetadata.listAssistantTasksOperation,
        ),
      );
      return rows
          .map(AssistantUserTaskView.fromJson)
          .where((row) => row.taskId.isNotEmpty)
          .take(limit)
          .toList(growable: false);
    } catch (_) {
      return const <AssistantUserTaskView>[];
    }
  }

  @override
  Future<List<AssistantUserMemoryView>> listAssistantMemories({
    int limit = _kAssistantListPageDefaultLimit,
  }) async {
    try {
      final uri = _assistantGetUri(
        AssistantApiMetadata.listAssistantMemoriesPath,
        {'limit': '$limit'},
      );
      final response = await _client.get(
        uri,
        headers: _headersForAssistantDialog(
          operationId: AssistantApiMetadata.listAssistantMemoriesOperation,
          clientPageId: AssistantRequestPageIds.listAssistantMemories,
        ),
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        return const <AssistantUserMemoryView>[];
      }
      final decoded = response.body.trim().isEmpty
          ? <String, dynamic>{}
          : jsonDecode(response.body);
      final rows = _decodeItemsMap(
        decoded,
        context: _assistantDialogContext(
          operationId: AssistantApiMetadata.listAssistantMemoriesOperation,
        ),
      );
      return rows
          .map(AssistantUserMemoryView.fromJson)
          .where((row) => row.memoryId.isNotEmpty)
          .take(limit)
          .toList(growable: false);
    } catch (_) {
      return const <AssistantUserMemoryView>[];
    }
  }

  @override
  Future<List<AssistantSkillCatalogItemView>> listSkillCatalog({
    int limit = _kAssistantSkillCatalogDefaultLimit,
  }) async {
    try {
      final uri = _assistantGetUri(AssistantApiMetadata.listSkillsPath, {
        'limit': '$limit',
      });
      final response = await _client.get(
        uri,
        headers: _headersForAssistantDialog(
          operationId: AssistantApiMetadata.listSkillsOperation,
          clientPageId: AssistantRequestPageIds.listSkills,
        ),
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        return const <AssistantSkillCatalogItemView>[];
      }
      final decoded = response.body.trim().isEmpty
          ? <String, dynamic>{}
          : jsonDecode(response.body);
      final rows = _decodeItemsMap(
        decoded,
        context: _assistantDialogContext(
          operationId: AssistantApiMetadata.listSkillsOperation,
        ),
      );
      return rows
          .map(AssistantSkillCatalogItemView.fromJson)
          .where((row) => row.skillId.isNotEmpty)
          .take(limit)
          .toList(growable: false);
    } catch (_) {
      return const <AssistantSkillCatalogItemView>[];
    }
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

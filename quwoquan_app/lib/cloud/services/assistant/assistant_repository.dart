import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_cloud_api_wire.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_request_page_ids.g.dart';
import 'package:quwoquan_app/assistant/generated/contracts/assistant_conversation.g.dart';
import 'package:quwoquan_app/assistant/generated/contracts/assistant_stream_event.g.dart';
import 'package:quwoquan_app/assistant/generated/contracts/assistant_turn_envelope.g.dart';
import 'package:quwoquan_app/assistant/generated/contracts/skill_subscription.g.dart';
import 'package:quwoquan_app/assistant/generated/contracts/tool_use.g.dart';
import 'package:quwoquan_app/core/models/app_content_prototype_models.dart';
import 'package:quwoquan_app/cloud/services/app_content/app_content_prototype_codec.dart';

export 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_cloud_api_wire.g.dart'
    show
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
export 'package:quwoquan_app/assistant/generated/contracts/assistant_conversation.g.dart'
    show AssistantConversationWire;
export 'package:quwoquan_app/assistant/generated/contracts/assistant_stream_event.g.dart'
    show AssistantStreamEventWire;
export 'package:quwoquan_app/assistant/generated/contracts/assistant_turn_envelope.g.dart'
    show AssistantTurnEnvelopeWire;
export 'package:quwoquan_app/assistant/generated/contracts/skill_subscription.g.dart'
    show
        SkillSubscriptionDestinationWire,
        SkillSubscriptionSearchQueryPlanWire,
        SkillSubscriptionTriggerWire,
        SkillSubscriptionWire;
export 'package:quwoquan_app/assistant/generated/contracts/tool_use.g.dart'
    show ToolUseWire;
import 'package:shared_preferences/shared_preferences.dart';

const String kPersonalContentAccessSkillId = 'personal_content_access';

/// Assistant 任务/记忆等列表接口单次拉取条数（与网关约定一致，非 [CloudApiDefaults.pageLimit]）。
const int _kAssistantListPageDefaultLimit = 32;

/// Assistant 技能目录单次拉取条数。
const int _kAssistantSkillCatalogDefaultLimit = 64;

/// Assistant 技能订阅列表单次拉取条数。
const int _kAssistantSkillSubscriptionsDefaultLimit = 20;

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

  Future<List<SkillSubscriptionWire>> listSkillSubscriptions({
    int limit = _kAssistantSkillSubscriptionsDefaultLimit,
    String status = '',
  });

  Future<SkillSubscriptionWire> createSkillSubscription({
    required String skillId,
    String domainId = 'assistant',
    List<String> tagRefs = const <String>[],
    required String rawText,
    List<String> queries = const <String>[],
    String cron = '0 8 * * *',
  });

  Future<SkillSubscriptionWire> updateSkillSubscriptionStatus({
    required String subscriptionId,
    required String status,
  });

  Future<AssistantConversationWire> createAssistantConversation({
    String summary = '',
  }) {
    throw UnimplementedError('createAssistantConversation');
  }

  Future<AssistantConversationWire> getAssistantConversation({
    required String conversationId,
  }) {
    throw UnimplementedError('getAssistantConversation');
  }

  Future<AssistantTurnEnvelopeWire> createAssistantTurn({
    required String conversationId,
    required String text,
    String turnType = 'user',
    String skillId = '',
    String domainId = '',
  }) {
    throw UnimplementedError('createAssistantTurn');
  }

  Future<AssistantTurnEnvelopeWire> getAssistantTurn({required String turnId}) {
    throw UnimplementedError('getAssistantTurn');
  }

  Stream<AssistantStreamEventWire> streamAssistantTurn({
    required String turnId,
  }) {
    throw UnimplementedError('streamAssistantTurn');
  }
}

class MockAssistantRepository implements AssistantRepository {
  MockAssistantRepository({AssistantConsentStore? store})
    : _store = store ?? const AssistantConsentStore();

  final AssistantConsentStore _store;
  final List<SkillSubscriptionWire> _subscriptions = <SkillSubscriptionWire>[];

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
    final p0Skills = <AssistantSkillCatalogItemView>[
      const AssistantSkillCatalogItemView(
        skillId: 'daily_assistant',
        displayName: '每日助手',
        description: '管理待办、日历、会议、作息和学习计划。',
        category: 'life',
        requiresConsent: false,
        iconHint: 'checkmark',
      ),
      const AssistantSkillCatalogItemView(
        skillId: 'news_briefing',
        displayName: '新闻简报',
        description: '按关注话题定时生成新闻摘要。',
        category: 'content',
        requiresConsent: false,
        iconHint: 'news',
      ),
      const AssistantSkillCatalogItemView(
        skillId: 'stock_sentinel',
        displayName: '股票哨兵',
        description: '跟踪关注股票的重大消息面和行情变化。',
        category: 'finance',
        requiresConsent: false,
        iconHint: 'chart',
      ),
      const AssistantSkillCatalogItemView(
        skillId: 'travel_journey_manager',
        displayName: '出行旅程管家',
        description: '结合天气、路况和景点拥堵提醒行程风险。',
        category: 'travel',
        requiresConsent: false,
        iconHint: 'airplane',
      ),
    ];
    final prototypeSkills = AppContentPrototypeBundle
        .instance
        .assistantSkillsData
        .map(
          (row) => AssistantSkillCatalogItemView(
            skillId: row.skillId,
            displayName: row.name,
            description: row.description,
            requiresConsent: false,
          ),
        );
    return <AssistantSkillCatalogItemView>[
      ...p0Skills,
      ...prototypeSkills,
    ].take(limit).toList(growable: false);
  }

  @override
  Future<List<SkillSubscriptionWire>> listSkillSubscriptions({
    int limit = _kAssistantSkillSubscriptionsDefaultLimit,
    String status = '',
  }) async {
    final filtered = _subscriptions
        .where((item) {
          if (status.trim().isEmpty) {
            return item.status != 'archived';
          }
          return item.status == status.trim();
        })
        .toList(growable: false);
    return filtered.take(limit).toList(growable: false);
  }

  @override
  Future<SkillSubscriptionWire> createSkillSubscription({
    required String skillId,
    String domainId = 'assistant',
    List<String> tagRefs = const <String>[],
    required String rawText,
    List<String> queries = const <String>[],
    String cron = '0 8 * * *',
  }) async {
    final now = DateTime.now().toUtc().toIso8601String();
    final subscription = SkillSubscriptionWire(
      subscriptionId: 'sub_mock_${_subscriptions.length + 1}',
      createdByUserId: 'mock-user',
      skillId: skillId,
      domainId: domainId,
      tagRefs: tagRefs,
      searchQueryPlan: SkillSubscriptionSearchQueryPlanWire(
        rawText: rawText,
        queries: queries.isEmpty ? <String>[rawText] : queries,
      ),
      trigger: SkillSubscriptionTriggerWire(cron: cron),
      destination: const SkillSubscriptionDestinationWire(
        destinationType: 'user',
        destinationId: 'mock-user',
      ),
      createdAt: now,
      updatedAt: now,
    );
    _subscriptions.insert(0, subscription);
    return subscription;
  }

  @override
  Future<SkillSubscriptionWire> updateSkillSubscriptionStatus({
    required String subscriptionId,
    required String status,
  }) async {
    final idx = _subscriptions.indexWhere(
      (item) => item.subscriptionId == subscriptionId,
    );
    if (idx < 0) {
      throw StateError('skill subscription not found');
    }
    final current = _subscriptions[idx];
    final updated = SkillSubscriptionWire(
      subscriptionId: current.subscriptionId,
      owner: current.owner,
      createdByUserId: current.createdByUserId,
      skillId: current.skillId,
      domainId: current.domainId,
      tagRefs: current.tagRefs,
      status: status,
      searchQueryPlan: current.searchQueryPlan,
      trigger: current.trigger,
      destination: current.destination,
      createdAt: current.createdAt,
      updatedAt: DateTime.now().toUtc().toIso8601String(),
    );
    _subscriptions[idx] = updated;
    return updated;
  }

  @override
  Future<AssistantConversationWire> createAssistantConversation({
    String summary = '',
  }) async {
    final now = DateTime.now().toUtc().toIso8601String();
    return AssistantConversationWire(
      conversationId: 'acv_mock_personal_assistant',
      userId: 'mock-user',
      summary: summary,
      createdAt: now,
      updatedAt: now,
    );
  }

  @override
  Future<AssistantConversationWire> getAssistantConversation({
    required String conversationId,
  }) async {
    final now = DateTime.now().toUtc().toIso8601String();
    return AssistantConversationWire(
      conversationId: conversationId,
      userId: 'mock-user',
      createdAt: now,
      updatedAt: now,
    );
  }

  @override
  Future<AssistantTurnEnvelopeWire> createAssistantTurn({
    required String conversationId,
    required String text,
    String turnType = 'user',
    String skillId = '',
    String domainId = '',
  }) async {
    return AssistantTurnEnvelopeWire(
      turnId: 'atn_mock_personal_assistant',
      conversationId: conversationId,
      turnType: turnType,
      skillId: skillId,
      domainId: domainId,
      input: <String, dynamic>{'text': text},
      trigger: const <String, dynamic>{'type': 'user_message'},
      traceId: 'trace_mock_personal_assistant',
      createdAt: DateTime.now().toUtc().toIso8601String(),
    );
  }

  @override
  Future<AssistantTurnEnvelopeWire> getAssistantTurn({
    required String turnId,
  }) async {
    return AssistantTurnEnvelopeWire(
      turnId: turnId,
      conversationId: 'acv_mock_personal_assistant',
      traceId: 'trace_mock_personal_assistant',
      createdAt: DateTime.now().toUtc().toIso8601String(),
    );
  }

  @override
  Stream<AssistantStreamEventWire> streamAssistantTurn({
    required String turnId,
  }) async* {
    final createdAt = DateTime.now().toUtc().toIso8601String();
    final toolUse = ToolUseWire(
      toolUseId: 'tu_mock_personal_assistant',
      turnId: turnId,
      toolName: 'web_search',
      input: const <String, dynamic>{'query': '找私助 mock stream'},
      status: 'requested',
      createdAt: createdAt,
    );
    final completedToolUse = ToolUseWire(
      toolUseId: toolUse.toolUseId,
      turnId: turnId,
      toolName: toolUse.toolName,
      input: toolUse.input,
      status: 'completed',
      result: const <String, dynamic>{
        'provider': 'mock',
        'summary': '找私助 mock stream 已完成工具观察。',
        'references': <Map<String, dynamic>>[],
      },
      createdAt: createdAt,
      completedAt: createdAt,
    );
    yield AssistantStreamEventWire(
      eventId: '$turnId:assistant.turn.started',
      conversationId: 'acv_mock_personal_assistant',
      turnId: turnId,
      seq: 1,
      eventType: 'turn_started',
      payload: const <String, dynamic>{'status': 'running'},
      createdAt: createdAt,
    );
    yield AssistantStreamEventWire(
      eventId: '$turnId:assistant.tool.requested',
      conversationId: 'acv_mock_personal_assistant',
      turnId: turnId,
      seq: 2,
      eventType: 'tool_use_requested',
      payload: <String, dynamic>{'toolUse': toolUse.toJson()},
      createdAt: createdAt,
    );
    yield AssistantStreamEventWire(
      eventId: '$turnId:assistant.tool.completed',
      conversationId: 'acv_mock_personal_assistant',
      turnId: turnId,
      seq: 3,
      eventType: 'tool_result_received',
      payload: <String, dynamic>{'toolUse': completedToolUse.toJson()},
      createdAt: createdAt,
    );
    yield AssistantStreamEventWire(
      eventId: '$turnId:assistant.answer.final',
      conversationId: 'acv_mock_personal_assistant',
      turnId: turnId,
      seq: 4,
      eventType: 'final_answer',
      payload: const <String, dynamic>{'text': '找私助 mock stream 已接通。'},
      createdAt: createdAt,
    );
  }
}

class RemoteAssistantRepository implements AssistantRepository {
  RemoteAssistantRepository({
    CloudHttpClient? httpClient,
    AssistantConsentStore? store,
  }) : _httpClient = httpClient ?? CloudHttpClient(),
       _store = store ?? const AssistantConsentStore();

  final CloudHttpClient _httpClient;
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
      final response = await _httpClient.get(
        uri,
        headers: _headersForPersonalAssistantDialog(
          operationId: AssistantApiMetadata.getPolicyOperation,
          clientPageId: AssistantRequestPageIds.getPolicy,
        ),
      );
      if (response.statusCode >= 200 && response.statusCode < 300) {
        final decoded = response.body.trim().isEmpty
            ? <String, dynamic>{}
            : CloudResponseDecoder.asObject(
                jsonDecode(response.body),
                context: _personalAssistantDialogContext(
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
        final response = await _httpClient.post(
          uri,
          headers: <String, String>{
            ..._headersForPersonalAssistantDialog(
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
        final response = await _httpClient.post(
          uri,
          headers: <String, String>{
            ..._headersForPersonalAssistantDialog(
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

  Map<String, String> _headersForPersonalAssistantDialog({
    required String operationId,
    required String clientPageId,
  }) {
    return CloudRequestHeaders.forSurfaceOperation(
      surfaceId: AppUiSurfaces.personalAssistantDialog.id,
      routeId: AppUiSurfaces.personalAssistantDialog.routeId,
      operationId: operationId,
      clientPageId: clientPageId,
    );
  }

  String _personalAssistantDialogContext({required String operationId}) {
    return CloudRequestHeaders.contextForSurfaceOperation(
      surfaceId: AppUiSurfaces.personalAssistantDialog.id,
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
      final response = await _httpClient.get(
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
      final response = await _httpClient.post(
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
      await _httpClient.delete(
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
      final response = await _httpClient.post(
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
      final response = await _httpClient.get(
        uri,
        headers: _headersForPersonalAssistantDialog(
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
        context: _personalAssistantDialogContext(
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
      final response = await _httpClient.get(
        uri,
        headers: _headersForPersonalAssistantDialog(
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
        context: _personalAssistantDialogContext(
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
      final response = await _httpClient.get(
        uri,
        headers: _headersForPersonalAssistantDialog(
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
        context: _personalAssistantDialogContext(
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

  @override
  Future<List<SkillSubscriptionWire>> listSkillSubscriptions({
    int limit = _kAssistantSkillSubscriptionsDefaultLimit,
    String status = '',
  }) async {
    try {
      final uri = _assistantGetUri(
        AssistantApiMetadata.listSkillSubscriptionsPath,
        {
          'limit': '$limit',
          if (status.trim().isNotEmpty) 'status': status.trim(),
        },
      );
      final response = await _httpClient.get(
        uri,
        headers: _headersForPersonalAssistantDialog(
          operationId: AssistantApiMetadata.listSkillSubscriptionsOperation,
          clientPageId: AssistantRequestPageIds.listSkillSubscriptions,
        ),
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        return const <SkillSubscriptionWire>[];
      }
      final decoded = response.body.trim().isEmpty
          ? <String, dynamic>{}
          : jsonDecode(response.body);
      final rows = _decodeItemsMap(
        decoded,
        context: _personalAssistantDialogContext(
          operationId: AssistantApiMetadata.listSkillSubscriptionsOperation,
        ),
      );
      return rows
          .map(SkillSubscriptionWire.fromJson)
          .where((row) => row.subscriptionId.isNotEmpty)
          .take(limit)
          .toList(growable: false);
    } catch (_) {
      return const <SkillSubscriptionWire>[];
    }
  }

  @override
  Future<SkillSubscriptionWire> createSkillSubscription({
    required String skillId,
    String domainId = 'assistant',
    List<String> tagRefs = const <String>[],
    required String rawText,
    List<String> queries = const <String>[],
    String cron = '0 8 * * *',
  }) async {
    final response = await _httpClient.post(
      _assistantUri(AssistantApiMetadata.createSkillSubscriptionPath),
      headers: <String, String>{
        ..._headersForPersonalAssistantDialog(
          operationId: AssistantApiMetadata.createSkillSubscriptionOperation,
          clientPageId: AssistantRequestPageIds.createSkillSubscription,
        ),
        'Content-Type': 'application/json',
      },
      body: jsonEncode(<String, dynamic>{
        'skillId': skillId,
        'domainId': domainId,
        'tagRefs': tagRefs,
        'searchQueryPlan': <String, dynamic>{
          'rawText': rawText,
          'queries': queries.isEmpty ? <String>[rawText] : queries,
        },
        'trigger': <String, dynamic>{'type': 'cron', 'cron': cron},
        'destination': const <String, dynamic>{'destinationType': 'user'},
      }),
    );
    return SkillSubscriptionWire.fromJson(
      _decodeAssistantObject(
        response,
        operationId: AssistantApiMetadata.createSkillSubscriptionOperation,
      ),
    );
  }

  @override
  Future<SkillSubscriptionWire> updateSkillSubscriptionStatus({
    required String subscriptionId,
    required String status,
  }) async {
    final response = await _httpClient.patch(
      _assistantUri(
        AssistantApiMetadata.updateSkillSubscriptionStatusPath(
          subscriptionId: subscriptionId,
        ),
      ),
      headers: <String, String>{
        ..._headersForPersonalAssistantDialog(
          operationId:
              AssistantApiMetadata.updateSkillSubscriptionStatusOperation,
          clientPageId: AssistantRequestPageIds.updateSkillSubscriptionStatus,
        ),
        'Content-Type': 'application/json',
      },
      body: jsonEncode(<String, dynamic>{'status': status}),
    );
    return SkillSubscriptionWire.fromJson(
      _decodeAssistantObject(
        response,
        operationId:
            AssistantApiMetadata.updateSkillSubscriptionStatusOperation,
      ),
    );
  }

  @override
  Future<AssistantConversationWire> createAssistantConversation({
    String summary = '',
  }) async {
    final uri = _assistantUri(
      AssistantApiMetadata.createAssistantConversationPath,
    );
    _debugAssistantRepository(
      'POST $uri operation=${AssistantApiMetadata.createAssistantConversationOperation}',
    );
    final response = await _httpClient.post(
      uri,
      headers: <String, String>{
        ..._headersForPersonalAssistantDialog(
          operationId:
              AssistantApiMetadata.createAssistantConversationOperation,
          clientPageId: AssistantRequestPageIds.createAssistantConversation,
        ),
        'Content-Type': 'application/json',
      },
      body: jsonEncode(<String, dynamic>{'summary': summary}),
    );
    _debugAssistantRepository(
      'response status=${response.statusCode} operation=${AssistantApiMetadata.createAssistantConversationOperation}',
    );
    final conversation = AssistantConversationWire.fromJson(
      _decodeAssistantObject(
        response,
        operationId: AssistantApiMetadata.createAssistantConversationOperation,
      ),
    );
    _debugAssistantRepository(
      'conversation decoded id=${conversation.conversationId}',
    );
    return conversation;
  }

  @override
  Future<AssistantConversationWire> getAssistantConversation({
    required String conversationId,
  }) async {
    final response = await _httpClient.get(
      _assistantUri(
        AssistantApiMetadata.getAssistantConversationPath(
          conversationId: conversationId,
        ),
      ),
      headers: _headersForPersonalAssistantDialog(
        operationId: AssistantApiMetadata.getAssistantConversationOperation,
        clientPageId: AssistantRequestPageIds.getAssistantConversation,
      ),
    );
    return AssistantConversationWire.fromJson(
      _decodeAssistantObject(
        response,
        operationId: AssistantApiMetadata.getAssistantConversationOperation,
      ),
    );
  }

  @override
  Future<AssistantTurnEnvelopeWire> createAssistantTurn({
    required String conversationId,
    required String text,
    String turnType = 'user',
    String skillId = '',
    String domainId = '',
  }) async {
    final uri = _assistantUri(
      AssistantApiMetadata.createAssistantTurnPath(
        conversationId: conversationId,
      ),
    );
    _debugAssistantRepository(
      'POST $uri operation=${AssistantApiMetadata.createAssistantTurnOperation} '
      'conversationId=$conversationId text="${_assistantDebugSnippet(text)}"',
    );
    final response = await _httpClient.post(
      uri,
      headers: <String, String>{
        ..._headersForPersonalAssistantDialog(
          operationId: AssistantApiMetadata.createAssistantTurnOperation,
          clientPageId: AssistantRequestPageIds.createAssistantTurn,
        ),
        'Content-Type': 'application/json',
      },
      body: jsonEncode(<String, dynamic>{
        'turnType': turnType,
        'skillId': skillId,
        'domainId': domainId,
        'input': <String, dynamic>{'text': text},
        'trigger': const <String, dynamic>{'type': 'user_message'},
      }),
    );
    _debugAssistantRepository(
      'response status=${response.statusCode} operation=${AssistantApiMetadata.createAssistantTurnOperation}',
    );
    final turn = AssistantTurnEnvelopeWire.fromJson(
      _decodeAssistantObject(
        response,
        operationId: AssistantApiMetadata.createAssistantTurnOperation,
      ),
    );
    _debugAssistantRepository(
      'turn decoded conversationId=${turn.conversationId} turnId=${turn.turnId} traceId=${turn.traceId}',
    );
    return turn;
  }

  @override
  Future<AssistantTurnEnvelopeWire> getAssistantTurn({
    required String turnId,
  }) async {
    final response = await _httpClient.get(
      _assistantUri(AssistantApiMetadata.getAssistantTurnPath(turnId: turnId)),
      headers: _headersForPersonalAssistantDialog(
        operationId: AssistantApiMetadata.getAssistantTurnOperation,
        clientPageId: AssistantRequestPageIds.getAssistantTurn,
      ),
    );
    return AssistantTurnEnvelopeWire.fromJson(
      _decodeAssistantObject(
        response,
        operationId: AssistantApiMetadata.getAssistantTurnOperation,
      ),
    );
  }

  @override
  Stream<AssistantStreamEventWire> streamAssistantTurn({
    required String turnId,
  }) async* {
    final uri = _assistantUri(
      AssistantApiMetadata.streamAssistantTurnPath(turnId: turnId),
    );
    _debugAssistantRepository(
      'POST $uri operation=${AssistantApiMetadata.streamAssistantTurnOperation} turnId=$turnId',
    );
    final request = http.Request('POST', uri)
      ..headers.addAll(<String, String>{
        ..._headersForPersonalAssistantDialog(
          operationId: AssistantApiMetadata.streamAssistantTurnOperation,
          clientPageId: AssistantRequestPageIds.streamAssistantTurn,
        ),
        'Content-Type': 'application/json',
      })
      ..body = '{}';
    final response = await _httpClient.send(request);
    _debugAssistantRepository(
      'stream response status=${response.statusCode} turnId=$turnId',
    );
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw StateError('Assistant stream failed: ${response.statusCode}');
    }
    final buffer = StringBuffer();
    await for (final piece in response.stream.transform(utf8.decoder)) {
      buffer.write(piece);
      var current = buffer.toString();
      var splitIndex = current.indexOf('\n\n');
      while (splitIndex >= 0) {
        final frame = current.substring(0, splitIndex);
        final event = _decodeAssistantStreamFrame(frame);
        if (event != null) {
          _debugAssistantRepository(
            'sse event type=${event.eventType} seq=${event.seq} turnId=$turnId '
            'skill=${event.payload['skillId'] ?? ''} tool=${_assistantToolNameFromPayload(event.payload)}',
          );
          yield event;
        }
        current = current.substring(splitIndex + 2);
        splitIndex = current.indexOf('\n\n');
      }
      buffer
        ..clear()
        ..write(current);
    }
  }

  Uri _assistantUri(String path) {
    return Uri.parse('${CloudRuntimeConfig.gatewayBaseUrl}$path');
  }

  Map<String, dynamic> _decodeAssistantObject(
    http.Response response, {
    required String operationId,
  }) {
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw StateError('Assistant request failed: ${response.statusCode}');
    }
    final decoded = response.body.trim().isEmpty
        ? <String, dynamic>{}
        : jsonDecode(response.body);
    return CloudResponseDecoder.asObject(
      decoded,
      context: _personalAssistantDialogContext(operationId: operationId),
    );
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

AssistantStreamEventWire? _decodeAssistantStreamFrame(String frame) {
  final lines = const LineSplitter().convert(frame);
  final dataLines = <String>[];
  for (final rawLine in lines) {
    final line = rawLine.trimRight();
    if (line.startsWith('data:')) {
      dataLines.add(line.substring(5).trimLeft());
    }
  }
  if (dataLines.isEmpty) {
    return null;
  }
  final decoded = jsonDecode(dataLines.join('\n'));
  if (decoded is! Map) {
    return null;
  }
  final envelope = decoded.cast<String, dynamic>();
  final payload =
      (envelope['payload'] as Map?)?.cast<String, dynamic>() ??
      (envelope['data'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};
  final eventType = (envelope['eventType'] ?? envelope['event'] ?? '')
      .toString()
      .trim();
  final turnId = (payload['turnId'] ?? envelope['turnId'] ?? '')
      .toString()
      .trim();
  final conversationId =
      (payload['conversationId'] ?? envelope['conversationId'] ?? '')
          .toString()
          .trim();
  return AssistantStreamEventWire.fromJson(<String, dynamic>{
    'schemaVersion':
        (envelope['schemaVersion'] ?? payload['schemaVersion'] ?? '')
            .toString(),
    'eventId': (envelope['eventId'] ?? envelope['id'] ?? '$turnId:$eventType')
        .toString(),
    'conversationId': conversationId,
    'turnId': turnId,
    'seq': envelope['seq'],
    'eventType': eventType,
    'traceId': (envelope['traceId'] ?? payload['traceId'] ?? '').toString(),
    'payload': payload,
    'runtimeFailure': envelope['runtimeFailure'],
    'createdAt': (envelope['createdAt'] ?? '').toString(),
  });
}

void _debugAssistantRepository(String message) {
  if (!kDebugMode && !kProfileMode) {
    return;
  }
  debugPrint('[assistant-repository] $message');
}

String _assistantDebugSnippet(String value, {int maxLength = 120}) {
  final normalized = value.replaceAll(RegExp(r'\s+'), ' ').trim();
  if (normalized.length <= maxLength) {
    return normalized;
  }
  return '${normalized.substring(0, maxLength)}...';
}

String _assistantToolNameFromPayload(Map<String, dynamic> payload) {
  final raw = payload['toolUse'];
  if (raw is Map) {
    return (raw['toolName'] ?? raw['tool_name'] ?? '').toString().trim();
  }
  return '';
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

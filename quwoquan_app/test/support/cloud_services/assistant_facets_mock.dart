/// Assistant 域 alpha/test 替身（B8 批次阶段 3a 从 lib 物理迁出）。
///
/// production `lib/**` 不再包含任何 assistant Mock；本文件位于 test/support，
/// 仅测试与 alpha 场景经 provider override 注入（production 不可达）。
/// 落位依据：`quwoquan_cloud_mock` 只依赖 `quwoquan_cloud_contracts`，而
/// assistant Facet 与 wire 类型均在 quwoquan_app 包内，故 Mock 不能进 cloud_mock。
library;

import 'package:quwoquan_app/cloud/services/assistant/assistant_consent_store.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_facets.dart';
import 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_runtime_enums.g.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';

final class AssistantPrototypeTaskRow {
  const AssistantPrototypeTaskRow({
    required this.taskKey,
    required this.title,
    this.time,
    required this.status,
    this.category,
  });

  final String taskKey;
  final String title;
  final String? time;
  final String status;
  final String? category;
}

final class AssistantPrototypeSkillRow {
  const AssistantPrototypeSkillRow({
    required this.skillId,
    required this.name,
    this.description,
  });

  final String skillId;
  final String name;
  final String? description;
}

/// Assistant alpha fixture 的强类型边界；不聚合 Chat、Circle 或 Content 数据。
/// 数据源自已退役的助手内联测试数据（已随本次迁移从 lib 删除）。
final class AssistantPrototypeFixture {
  const AssistantPrototypeFixture._();

  static const AssistantPrototypeFixture instance =
      AssistantPrototypeFixture._();

  List<AssistantPrototypeTaskRow> get tasks =>
      const <AssistantPrototypeTaskRow>[
        AssistantPrototypeTaskRow(
          taskKey: '1',
          title: '完成《城市节奏》摄影集',
          time: '14:00',
          status: 'pending',
          category: '计划',
        ),
        AssistantPrototypeTaskRow(
          taskKey: '2',
          title: '回复圈子里的讨论',
          time: '16:30',
          status: 'completed',
          category: '待办',
        ),
        AssistantPrototypeTaskRow(
          taskKey: '3',
          title: '晚间灵感整理',
          time: '21:00',
          status: 'pending',
          category: '待办',
        ),
      ];

  List<AssistantPrototypeSkillRow> get skills =>
      const <AssistantPrototypeSkillRow>[
        AssistantPrototypeSkillRow(
          skillId: 'summary',
          name: '总结',
          description: '每日/每周创作与社交汇总',
        ),
        AssistantPrototypeSkillRow(
          skillId: 'travel',
          name: '旅行',
          description: '出行攻略与目的地推荐',
        ),
        AssistantPrototypeSkillRow(
          skillId: 'reminder',
          name: '提醒',
          description: '关键信息与节日纪念日',
        ),
        AssistantPrototypeSkillRow(
          skillId: 'organize',
          name: '整理',
          description: '自动清理冗余信息与照片',
        ),
      ];
}

/// alpha/test 替身：一个类实现 8 个 assistant Facet（逻辑逐字迁自旧
/// `MockAssistantRepository`；行为收口归阶段 3b）。
class AlphaAssistantFacets
    implements
        AssistantConversationRunFacet,
        AssistantSkillSubscriptionFacet,
        AssistantSkillConsentFacet,
        AssistantLearningFactAppendFacet,
        AssistantPersonalizationFacet,
        AssistantPersonalDataFacet,
        AssistantPreferenceFactFacet,
        AssistantXiaoquSearchFacet,
        AssistantCreationSuggestFacet {
  AlphaAssistantFacets({AssistantConsentStore? store})
    : _store =
          store ?? AssistantConsentStore(actorScope: 'alpha_mock_assistant');

  final AssistantConsentStore _store;
  final List<SkillSubscriptionWire> _subscriptions = <SkillSubscriptionWire>[];
  final List<AssistantPreferenceFact> _preferences =
      <AssistantPreferenceFact>[];

  @override
  Future<AssistantLearningFactReceipt> appendUserFact({
    required AppendAssistantLearningFactRequest request,
  }) async {
    return AssistantLearningFactReceipt(
      eventId: request.eventId,
      eventVersion: request.eventVersion,
      accepted: true,
      deduplicated: false,
      appendSequence: 1,
      payloadDigest: 'alpha_mock',
      recordedAt: DateTime.now().toUtc().toIso8601String(),
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
    AssistantContextSnapshot? contextSnapshot,
  }) async {
    // alpha/test 确定性 fixture（production Remote 失败一律抛 CloudException，
    // 不再存在共享 fallback 构造器）。
    final trimmedQuery = query.trim();
    return AssistantSearchResultView(
      queryEcho: trimmedQuery,
      summary: trimmedQuery.isEmpty
          ? '小趣搜会结合圈子讨论结果和已有公开内容，为你梳理当前最相关的线索。'
          : '小趣搜正在整理“$trimmedQuery”的公开线索，会优先总结当前最相关的话题、圈子讨论与内容方向。',
      searchIntensity: searchIntensity,
      citations: const <AssistantSearchCitationView>[],
    );
  }

  @override
  Future<PageContextAck> reportPageContext({
    required AssistantOpenContext context,
    String? userAction,
  }) async {
    return PageContextAck(
      accepted: true,
      contextKey: 'mock:${assistantPageTypeForSource(context.source).wireName}',
      expiresAt: DateTime.now()
          .toUtc()
          .add(const Duration(minutes: 5))
          .toIso8601String(),
    );
  }

  @override
  Future<AssistantEntryPersonalizationView> getEntryPersonalization({
    required AssistantOpenContext context,
  }) async {
    return _entryPersonalizationFixture(context);
  }

  @override
  Future<SuggestedActionListView> getSuggestedActions({
    required AssistantOpenContext context,
  }) async {
    final personalization = _entryPersonalizationFixture(context);
    return SuggestedActionListView(
      items: personalization.chips
          .map(
            (chip) => SuggestedAction(
              actionId: chip.chipId,
              type: chip.actionType,
              label: chip.label,
              payload: <String, dynamic>{'value': chip.value ?? ''},
            ),
          )
          .toList(growable: false),
    );
  }

  /// alpha/test 确定性个性化 fixture（原 lib 内 fallback 构造器已随
  /// B8 阶段 3b 删除；数据内联至此，production 不可达）。
  AssistantEntryPersonalizationView _entryPersonalizationFixture(
    AssistantOpenContext context,
  ) {
    final pageType = assistantPageTypeForSource(context.source);
    final welcome = switch (pageType) {
      AssistantPageContextType.chat => '我可以结合当前会话帮你整理话题、找资料或写回复。',
      AssistantPageContextType.search => '我可以把站内结果、网页线索和你的上下文串起来。',
      AssistantPageContextType.create => '我可以帮你找灵感、配文案或整理发布计划。',
      AssistantPageContextType.home => '我可以结合当前主页、关系和交集帮你解释信息。',
      _ => '有什么想让我帮忙的？',
    };
    return AssistantEntryPersonalizationView(
      welcomeMessage: welcome,
      suggestionLines: const <String>['说一句你想做的事，或选上面的推荐试试'],
      chips: const <AssistantEntryPersonalizationChipView>[
        AssistantEntryPersonalizationChipView(
          chipId: 'find',
          label: '帮我找',
          actionType: 'command',
          value: 'find',
        ),
        AssistantEntryPersonalizationChipView(
          chipId: 'remember',
          label: '帮我记',
          actionType: 'command',
          value: 'remember',
        ),
        AssistantEntryPersonalizationChipView(
          chipId: 'share',
          label: '帮我分享',
          actionType: 'command',
          value: 'share',
        ),
      ],
      personalized: false,
    );
  }

  @override
  Future<List<AssistantUserTaskView>> listAssistantTasks({
    int limit = kAssistantListPageDefaultLimit,
    String? status,
  }) async {
    final raw = AssistantPrototypeFixture.instance.tasks;
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
  Future<AssistantPreferenceFact> setAssistantPreference({
    required AssistantPreferenceScope scope,
    String conversationId = '',
    required AssistantPreferenceKind kind,
    required String value,
    required AssistantPreferenceSourceType sourceType,
  }) async {
    final now = DateTime.now().toUtc().toIso8601String();
    final index = _preferences.indexWhere(
      (fact) =>
          fact.scope == scope &&
          (fact.conversationId ?? '') == conversationId.trim() &&
          fact.kind == kind,
    );
    final existing = index < 0 ? null : _preferences[index];
    final fact = AssistantPreferenceFact(
      preferenceId:
          existing?.preferenceId ?? 'apf_alpha_${_preferences.length + 1}',
      userId: 'alpha_persona',
      scope: scope,
      conversationId: conversationId.trim().isEmpty
          ? null
          : conversationId.trim(),
      kind: kind,
      value: value.trim(),
      sourceType: sourceType,
      status: AssistantPreferenceStatus.active,
      createdAt: existing?.createdAt ?? now,
      updatedAt: now,
      version: (existing?.version ?? 0) + 1,
    );
    if (index < 0) {
      _preferences.add(fact);
    } else {
      _preferences[index] = fact;
    }
    return fact;
  }

  @override
  Future<List<AssistantPreferenceFact>> listAssistantPreferences({
    AssistantPreferenceScope? scope,
    String conversationId = '',
    AssistantPreferenceStatus status = AssistantPreferenceStatus.active,
  }) async {
    return _preferences
        .where(
          (fact) =>
              fact.status == status &&
              (scope == null || fact.scope == scope) &&
              (conversationId.trim().isEmpty ||
                  (fact.conversationId ?? '') == conversationId.trim()),
        )
        .toList(growable: false);
  }

  @override
  Future<AssistantPreferenceFact> revokeAssistantPreference({
    required String preferenceId,
  }) async {
    final index = _preferences.indexWhere(
      (fact) => fact.preferenceId == preferenceId.trim(),
    );
    if (index < 0) {
      throw StateError('assistant preference not found');
    }
    final current = _preferences[index];
    if (current.status == AssistantPreferenceStatus.revoked) {
      return current;
    }
    final now = DateTime.now().toUtc();
    final revoked = AssistantPreferenceFact(
      preferenceId: current.preferenceId,
      userId: current.userId,
      scope: current.scope,
      conversationId: current.conversationId,
      kind: current.kind,
      value: current.value,
      sourceType: current.sourceType,
      status: AssistantPreferenceStatus.revoked,
      revokedAt: now.toIso8601String(),
      revocationDeadline: now
          .add(const Duration(minutes: 10))
          .toIso8601String(),
      createdAt: current.createdAt,
      updatedAt: now.toIso8601String(),
      version: current.version + 1,
    );
    _preferences[index] = revoked;
    return revoked;
  }

  @override
  Future<AssistantPreferenceFact> restoreAssistantPreference({
    required String preferenceId,
  }) async {
    final index = _preferences.indexWhere(
      (fact) => fact.preferenceId == preferenceId.trim(),
    );
    if (index < 0) {
      throw StateError('assistant preference not found');
    }
    final current = _preferences[index];
    if (current.status == AssistantPreferenceStatus.active) {
      return current;
    }
    final deadline = DateTime.tryParse(current.revocationDeadline ?? '');
    final now = DateTime.now().toUtc();
    if (deadline == null || !now.isBefore(deadline)) {
      throw StateError('assistant preference restore expired');
    }
    final restored = AssistantPreferenceFact(
      preferenceId: current.preferenceId,
      userId: current.userId,
      scope: current.scope,
      conversationId: current.conversationId,
      kind: current.kind,
      value: current.value,
      sourceType: current.sourceType,
      status: AssistantPreferenceStatus.active,
      createdAt: current.createdAt,
      updatedAt: now.toIso8601String(),
      version: current.version + 1,
    );
    _preferences[index] = restored;
    return restored;
  }

  @override
  Future<List<AssistantSkillCatalogItemView>> listSkillCatalog({
    int limit = kAssistantSkillCatalogDefaultLimit,
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
      const AssistantSkillCatalogItemView(
        skillId: 'creation_assistant',
        displayName: '创作助手',
        description: '帮助整理草稿摘要、推荐标签和关联主页。',
        category: 'content_creation',
        requiresConsent: false,
        iconHint: 'sparkles',
      ),
    ];
    final prototypeSkills = AssistantPrototypeFixture.instance.skills.map(
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
  Future<AssistantCreationSuggestResponse> suggestCreationAssistance({
    required AssistantCreationSuggestRequest request,
  }) async {
    final enabled = _subscriptions.any(
      (item) =>
          item.skillId == 'creation_assistant' &&
          item.status == SkillSubscriptionStatus.active,
    );
    if (!enabled) {
      return const AssistantCreationSuggestResponse(
        suggestedTagRefs: <String>[],
        suggestedHomepages: <AssistantSuggestedHomepageView>[],
        available: false,
        unavailableReason: 'skill_not_enabled',
      );
    }
    final text = <String?>[
      request.draftTitle,
      request.draftSummary,
      request.bodyDigest,
    ].whereType<String>().join(' ');
    final tagRefs = <String>{
      if (text.contains('九寨') || text.contains('旅行')) 'Topic/旅行',
      if (text.contains('摄影') || text.contains('照片')) 'Topic/摄影',
    }.toList(growable: false);
    return AssistantCreationSuggestResponse(
      suggestedTagRefs: tagRefs,
      suggestedHomepages: <AssistantSuggestedHomepageView>[
        if ((request.primaryHomepageId ?? '').trim().isNotEmpty)
          AssistantSuggestedHomepageView(
            id: request.primaryHomepageId!.trim(),
            type: 'homepage',
            displayName: request.primaryHomepageId!.trim(),
            reason: '已作为主关联主页',
          ),
      ],
      suggestedTitle:
          (request.draftTitle ?? '').trim().isEmpty &&
              (request.primaryHomepageId ?? '').trim().isNotEmpty
          ? '我和${request.primaryHomepageId!.trim()}有关的一次发现'
          : null,
      suggestedSummary: (request.draftSummary ?? '').trim().isEmpty
          ? (request.bodyDigest ?? '').trim()
          : null,
      available: true,
    );
  }

  @override
  Future<List<SkillSubscriptionWire>> listSkillSubscriptions({
    int limit = kAssistantSkillSubscriptionsDefaultLimit,
    String status = '',
  }) async {
    final filtered = _subscriptions
        .where((item) {
          if (status.trim().isEmpty) {
            return item.status != SkillSubscriptionStatus.archived;
          }
          return item.status.wireName == status.trim();
        })
        .toList(growable: false);
    return filtered.take(limit).toList(growable: false);
  }

  @override
  Future<SkillSubscriptionWire> getSkillSubscription({
    required String subscriptionId,
  }) async {
    return _subscriptions.singleWhere(
      (item) => item.subscriptionId == subscriptionId.trim(),
      orElse: () => throw StateError('skill subscription not found'),
    );
  }

  @override
  Future<SkillSubscriptionWire> createSkillSubscription({
    required String skillId,
    String domainId = 'assistant',
    List<String> tagRefs = const <String>[],
    required String rawText,
    List<String> queries = const <String>[],
    String cron = '0 8 * * *',
    required String clientRequestId,
  }) async {
    if (clientRequestId.trim().isEmpty) {
      throw ArgumentError.value(clientRequestId, 'clientRequestId', 'required');
    }
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
    required String clientRequestId,
  }) async {
    if (clientRequestId.trim().isEmpty) {
      throw ArgumentError.value(clientRequestId, 'clientRequestId', 'required');
    }
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
      status: parseSkillSubscriptionStatusStrict(status),
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
    required String clientRequestId,
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
  Future<AssistantConversationListPage> listAssistantConversations({
    int limit = kAssistantListPageDefaultLimit,
    String cursor = '',
  }) async {
    return const AssistantConversationListPage(
      items: <AssistantConversationWire>[],
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
  Future<AssistantTurnListView> listConversationTurns({
    required String conversationId,
    int limit = kAssistantListPageDefaultLimit,
    String cursor = '',
  }) async {
    return const AssistantTurnListView(items: <AssistantTurnSummaryView>[]);
  }

  @override
  Future<AssistantTurnEnvelopeWire> startAssistantRun({
    required String conversationId,
    required String text,
    required String clientRequestId,
    String turnType = 'user',
    String skillId = '',
    String domainId = '',
    List<AssistantIntersectionEvidenceRef> intersectionEvidenceRefs =
        const <AssistantIntersectionEvidenceRef>[],
  }) async {
    return AssistantTurnEnvelopeWire(
      turnId: 'atn_mock_personal_assistant',
      conversationId: conversationId,
      turnType: turnType,
      skillId: skillId,
      domainId: domainId,
      input: AssistantTurnInputWire(text: text),
      trigger: const AssistantTurnTriggerWire(type: 'user_message'),
      traceId: 'trace_mock_personal_assistant',
      createdAt: DateTime.now().toUtc().toIso8601String(),
    );
  }

  @override
  Future<AssistantTurnEnvelopeWire> getAssistantRun({
    required String runId,
  }) async {
    return AssistantTurnEnvelopeWire(
      turnId: runId,
      conversationId: 'acv_mock_personal_assistant',
      traceId: 'trace_mock_personal_assistant',
      createdAt: DateTime.now().toUtc().toIso8601String(),
    );
  }

  @override
  Future<AssistantTurnEnvelopeWire> cancelAssistantRun({
    required String runId,
  }) {
    return getAssistantRun(runId: runId);
  }

  @override
  Stream<AssistantStreamEventWire> watchAssistantRunEvents({
    required String runId,
  }) async* {
    final createdAt = DateTime.now().toUtc().toIso8601String();
    yield AssistantStreamEventWire(
      schema: 'assistant_stream_event',
      eventId: '$runId:run_started',
      conversationId: 'acv_mock_personal_assistant',
      turnId: runId,
      seq: 1,
      eventType: AssistantStreamEventType.runStarted,
      payload: const <String, dynamic>{'status': 'running', 'restarted': false},
      createdAt: createdAt,
    );
    yield AssistantStreamEventWire(
      schema: 'assistant_stream_event',
      eventId: '$runId:process_replace',
      conversationId: 'acv_mock_personal_assistant',
      turnId: runId,
      seq: 2,
      eventType: AssistantStreamEventType.processReplace,
      payload: const <String, dynamic>{'processes': <Object?>[]},
      createdAt: createdAt,
    );
    yield AssistantStreamEventWire(
      schema: 'assistant_stream_event',
      eventId: '$runId:tool_execution',
      conversationId: 'acv_mock_personal_assistant',
      turnId: runId,
      seq: 3,
      eventType: AssistantStreamEventType.processAppend,
      payload: const <String, dynamic>{
        'process': <String, dynamic>{
          'processId': 'tool_execution',
          'scope': 'skill',
          'stage': 'tool_execution',
          'status': 'completed',
          'order': 1,
          'summary': '已完成可用信息的核对。',
          'toolName': 'web_search',
        },
      },
      createdAt: createdAt,
    );
    yield AssistantStreamEventWire(
      schema: 'assistant_stream_event',
      eventId: '$runId:answer_delta',
      conversationId: 'acv_mock_personal_assistant',
      turnId: runId,
      seq: 4,
      eventType: AssistantStreamEventType.answerDelta,
      payload: const <String, dynamic>{'text': '找私助 mock stream 已接通。'},
      createdAt: createdAt,
    );
    yield AssistantStreamEventWire(
      schema: 'assistant_stream_event',
      eventId: '$runId:completed',
      conversationId: 'acv_mock_personal_assistant',
      turnId: runId,
      seq: 5,
      eventType: AssistantStreamEventType.completed,
      payload: const <String, dynamic>{
        'status': 'completed',
        'finalAnswer': '找私助 mock stream 已接通。',
      },
      createdAt: createdAt,
    );
  }
}

/// Assistant 域 local_contract 替身（B8 批次阶段 3a 从 lib 物理迁出）。
///
/// production `lib/**` 不再包含任何 assistant Mock；本文件位于 test/support，
/// 仅对象级测试可注入，Patrol/UAT 与 production composition 不可达。
library;

import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:quwoquan_app/runtime/di/app_providers.dart';

import 'package:quwoquan_app/service/assistant_service/assistant/assistant_entry_view/application/assistant_personalization_facade.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_learning_fact/application/assistant_learning_fact_append_facet.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_preference/application/assistant_preference_facet.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/public/assistant_run_ports.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/public/assistant_session_run_facade.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_session/application/public/assistant_session_ports.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_task_view/application/assistant_task_query.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/assistant_turn_query.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/page_context/application/public/assistant_open_context.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_catalog/application/skill_catalog_facet.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_consent/application/skill_consent_facet.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_subscription/application/skill_subscription_facet.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_user_setting/application/skill_user_setting_facet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../runtime/codec/canonical_digest_fixture.dart';

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
class InMemoryAssistantFacets
    implements
        AssistantSessionRunFacade,
        AssistantRunControlFacet,
        AssistantSkillCatalogFacet,
        AssistantSkillSubscriptionFacet,
        AssistantSkillUserSettingFacet,
        AssistantSkillConsentFacet,
        AssistantLearningFactAppendFacet,
        AssistantPersonalizationFacade,
        AssistantTaskQuery,
        AssistantPreferenceFacet,
        AssistantSearchRunFacade,
        AssistantCreationRunProcessCommandWriter {
  InMemoryAssistantFacets();

  final List<SkillConsent> _consents = <SkillConsent>[];
  final List<SkillSubscriptionWire> _subscriptions = <SkillSubscriptionWire>[];
  final Map<String, SkillUserSetting> _settings = <String, SkillUserSetting>{};
  final List<AssistantPreference> _preferences = <AssistantPreference>[];

  @override
  Future<AssistantLearningFactReceipt> appendUserFact({
    required AssistantLearningFactAppendCommand request,
  }) async {
    return AssistantLearningFactReceipt(
      eventId: request.eventId,
      accepted: true,
      deduplicated: false,
      appendSequence: 1,
      payloadDigest:
          '0000000000000000000000000000000000000000000000000000000000000000',
      recordedAt: DateTime.now().toUtc().toIso8601String(),
    );
  }

  @override
  Future<List<SkillConsent>> listConsents() {
    return Future<List<SkillConsent>>.value(
      List<SkillConsent>.unmodifiable(_consents),
    );
  }

  @override
  Future<SkillConsent> grantSkillConsent({
    required String skillId,
    required List<String> grantedScopes,
    required String clientRequestId,
  }) async {
    final now = DateTime.now().toUtc().toIso8601String();
    final consent = SkillConsent(
      id: 'consent:$skillId',
      accountId: 'fixture_assistant',
      skillId: skillId,
      grantedScopes: List<String>.unmodifiable(grantedScopes),
      grantedAt: now,
      revokedAt: null,
      granted: true,
    );
    _consents
      ..removeWhere((item) => item.skillId == skillId)
      ..add(consent);
    return consent;
  }

  @override
  Future<void> revokeSkillConsent({
    required String skillId,
    required String clientRequestId,
  }) {
    _consents.removeWhere((item) => item.skillId == skillId);
    return Future<void>.value();
  }

  @override
  Future<AssistantRunTerminalSnapshotView> executeAssistantSearch({
    required String query,
    required String sessionClientRequestId,
    required String runClientRequestId,
    SearchIntensity searchIntensity = SearchIntensity.medium,
    AssistantContextSnapshot? contextSnapshot,
  }) async {
    final trimmedQuery = query.trim();
    return AssistantRunTerminalSnapshotView(
      answerText: trimmedQuery.isEmpty
          ? '小趣搜会结合圈子讨论结果和已有公开内容，为你梳理当前最相关的线索。'
          : '小趣搜正在整理“$trimmedQuery”的公开线索，会优先总结当前最相关的话题、圈子讨论与内容方向。',
      processes: const <AssistantRunVisibleProcessView>[],
    );
  }

  @override
  Future<PageContextReceipt> reportPageContext({
    required AssistantOpenContext context,
    String? userAction,
  }) async {
    return PageContextReceipt(
      accepted: true,
      contextKey: 'mock:${assistantPageTypeForSource(context.source).wireName}',
      expiresAt: DateTime.now()
          .toUtc()
          .add(const Duration(minutes: 5))
          .toIso8601String(),
    );
  }

  @override
  Future<AssistantEntryResponse> getAssistantEntry({
    required AssistantOpenContext context,
  }) async {
    final pageType = assistantPageTypeForSource(context.source);
    final welcome = switch (pageType) {
      AssistantPageContextType.chat => '我可以结合当前会话帮你整理话题、找资料或写回复。',
      AssistantPageContextType.search => '我可以把站内结果、网页线索和你的上下文串起来。',
      AssistantPageContextType.create => '我可以帮你找灵感、配文案或整理发布计划。',
      AssistantPageContextType.home => '我可以结合当前主页、关系和交集帮你解释信息。',
      _ => '有什么想让我帮忙的？',
    };
    return AssistantEntryResponse(
      welcomeMessage: welcome,
      suggestionLines: const <String>['说一句你想做的事，或选上面的推荐试试'],
      chips: const <AssistantEntryChip>[
        AssistantEntryChip(
          chipId: 'find',
          label: '帮我找',
          actionType: 'command',
          value: 'find',
        ),
        AssistantEntryChip(
          chipId: 'remember',
          label: '帮我记',
          actionType: 'command',
          value: 'remember',
        ),
        AssistantEntryChip(
          chipId: 'share',
          label: '帮我分享',
          actionType: 'command',
          value: 'share',
        ),
      ],
      actions: const <AssistantEntryAction>[],
      personalized: false,
    );
  }

  @override
  Future<List<AssistantTaskItemView>> listAssistantTasks({
    int limit = kAssistantTaskListDefaultLimit,
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
          return AssistantTaskItemView(
            taskId: row.taskKey,
            title: row.title,
            description: desc.isEmpty ? null : desc,
            status: row.status,
            updatedAt: DateTime.now().toUtc().toIso8601String(),
          );
        })
        .take(limit)
        .toList(growable: false);
  }

  @override
  Future<AssistantPreference> setAssistantPreference({
    required AssistantPreferenceScope scope,
    String sessionId = '',
    required AssistantPreferenceKind kind,
    required String value,
    required AssistantPreferenceSourceType sourceType,
    String sourceSessionId = '',
    bool confirmed = false,
  }) async {
    final now = DateTime.now().toUtc().toIso8601String();
    final index = _preferences.indexWhere(
      (preference) =>
          preference.scope == scope &&
          (preference.sessionId ?? '') == sessionId.trim() &&
          preference.kind == kind,
    );
    final existing = index < 0 ? null : _preferences[index];
    final preference = AssistantPreference(
      preferenceId:
          existing?.preferenceId ?? 'apf_alpha_${_preferences.length + 1}',
      userId: 'fixture_persona',
      scope: scope,
      sessionId: sessionId.trim().isEmpty ? null : sessionId.trim(),
      kind: kind,
      value: value.trim(),
      sourceType: sourceType,
      sourceSessionId: sourceSessionId.trim().isEmpty
          ? null
          : sourceSessionId.trim(),
      confirmedAt: confirmed ? now : null,
      status: AssistantPreferenceStatus.active,
      createdAt: existing?.createdAt ?? now,
      updatedAt: now,
      version: (existing?.version ?? 0) + 1,
    );
    if (index < 0) {
      _preferences.add(preference);
    } else {
      _preferences[index] = preference;
    }
    return preference;
  }

  @override
  Future<List<AssistantPreference>> listAssistantPreferences({
    AssistantPreferenceScope? scope,
    String sessionId = '',
    AssistantPreferenceStatus status = AssistantPreferenceStatus.active,
  }) async {
    return _preferences
        .where(
          (preference) =>
              preference.status == status &&
              (scope == null || preference.scope == scope) &&
              (sessionId.trim().isEmpty ||
                  (preference.sessionId ?? '') == sessionId.trim()),
        )
        .toList(growable: false);
  }

  @override
  Future<AssistantPreference> revokeAssistantPreference({
    required String preferenceId,
  }) async {
    final index = _preferences.indexWhere(
      (preference) => preference.preferenceId == preferenceId.trim(),
    );
    if (index < 0) {
      throw StateError('assistant preference not found');
    }
    final current = _preferences[index];
    if (current.status == AssistantPreferenceStatus.revoked) {
      return current;
    }
    final now = DateTime.now().toUtc();
    final revoked = AssistantPreference(
      preferenceId: current.preferenceId,
      userId: current.userId,
      scope: current.scope,
      sessionId: current.sessionId,
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
  Future<AssistantPreference> restoreAssistantPreference({
    required String preferenceId,
  }) async {
    final index = _preferences.indexWhere(
      (preference) => preference.preferenceId == preferenceId.trim(),
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
    final restored = AssistantPreference(
      preferenceId: current.preferenceId,
      userId: current.userId,
      scope: current.scope,
      sessionId: current.sessionId,
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
    AssistantSkillCatalogItemView item({
      required String skillId,
      required String displayName,
      required String description,
      String? category,
      String? iconHint,
      String domainId = 'assistant',
      List<String> requiredConsentScopes = const <String>[],
      String activationMode = 'hybrid',
    }) {
      return AssistantSkillCatalogItemView(
        packageId: 'quwoquan.official.$skillId',
        releaseDigest: canonicalFixtureSha256(<String, Object?>{
          'packageId': 'quwoquan.official.$skillId',
          'skillId': skillId,
        }),
        skillId: skillId,
        domainId: domainId,
        displayName: displayName,
        description: description,
        catalogGroup: _fixtureSemanticLabel(category ?? 'general'),
        requiresConsent: requiredConsentScopes.isNotEmpty,
        requiredConsentScopes: requiredConsentScopes,
        consentScopeLabels: requiredConsentScopes
            .map(_fixtureSemanticLabel)
            .toList(growable: false),
        iconHint: iconHint,
        targetAudiences: <SkillCatalogSemanticLabel>[
          _fixtureSemanticLabel('trip_organizer'),
        ],
        dataUseSummary: requiredConsentScopes.isEmpty
            ? '仅使用当前对话与公开信息'
            : '仅在明确授权后读取所列数据',
        examples: const <ResolvedSkillExample>[],
        activationMode: activationMode,
        surfaceKinds: <SkillCatalogSemanticLabel>[
          _fixtureSemanticLabel('personal'),
        ],
        configurationSchemaDigest: canonicalFixtureSha256(<String, Object?>{
          'skillId': skillId,
          'configurationRequiredFields': const <String>[],
        }),
        setupTemplateRef: 'assistant.setup.$skillId',
        configurationRequiredFields: const <String>[],
      );
    }

    final p0Skills = <AssistantSkillCatalogItemView>[
      item(
        skillId: 'daily_assistant',
        displayName: '每日助手',
        description: '管理待办、日历、会议、作息和学习计划。',
        category: 'life',
        iconHint: 'checkmark',
      ),
      item(
        skillId: 'news_briefing',
        displayName: '新闻简报',
        description: '按关注话题定时生成新闻摘要。',
        category: 'content',
        iconHint: 'news',
      ),
      item(
        skillId: 'stock_sentinel',
        displayName: '股票哨兵',
        description: '跟踪关注股票的重大消息面和行情变化。',
        category: 'finance',
        iconHint: 'chart',
      ),
      item(
        skillId: 'travel_companion',
        displayName: '出行旅程管家',
        description: '结合天气、路况和景点拥堵提醒行程风险。',
        category: 'travel',
        iconHint: 'airplane',
        domainId: 'travel',
        requiredConsentScopes: const <String>[
          'assistant.learning.feedback_context.read',
          'assistant.memory.preferences.read',
        ],
      ),
      item(
        skillId: 'creation_assistant',
        displayName: '创作助手',
        description: '帮助整理草稿摘要、推荐标签和关联主页。',
        category: 'content_creation',
        iconHint: 'sparkles',
      ),
    ];
    final prototypeSkills = AssistantPrototypeFixture.instance.skills.map(
      (row) => item(
        skillId: row.skillId,
        displayName: row.name,
        description: row.description ?? '',
      ),
    );
    return <AssistantSkillCatalogItemView>[
      ...p0Skills,
      ...prototypeSkills,
    ].take(limit).toList(growable: false);
  }

  @override
  Future<AssistantSkillCatalogItemDetailView> getSkillCatalogItem({
    required String skillId,
  }) async {
    final item = (await listSkillCatalog()).singleWhere(
      (candidate) => candidate.skillId == skillId,
      orElse: () => throw StateError('skill catalog item not found'),
    );
    final configurationSchema = skillId == 'travel_companion'
        ? <String, Object?>{
            'title': '旅行偏好',
            'description': '用于组合吃玩住行与提醒节奏。',
            'type': 'object',
            'additionalProperties': false,
            'properties': <String, Object?>{
              'travelPace': <String, Object?>{
                'type': 'string',
                'title': '旅行节奏',
                'enum': <String>['relaxed', 'balanced', 'intensive'],
                'x-enum-labels': <String, String>{
                  'relaxed': '轻松',
                  'balanced': '均衡',
                  'intensive': '紧凑',
                },
              },
              'reminderLeadMinutes': <String, Object?>{
                'type': 'integer',
                'title': '默认提前提醒',
                'minimum': 5,
                'maximum': 1440,
              },
            },
          }
        : <String, Object?>{
            'type': 'object',
            'additionalProperties': false,
            'properties': <String, Object?>{},
          };
    return AssistantSkillCatalogItemDetailView(
      item: item,
      configurationSchema: configurationSchema,
    );
  }

  @override
  Future<List<SkillUserSetting>> listSkillUserSettings({
    int limit = kAssistantSkillUserSettingsDefaultLimit,
  }) async {
    return _settings.values.take(limit).toList(growable: false);
  }

  @override
  Future<SkillUserSetting> getSkillUserSetting({
    required String skillId,
  }) async {
    final setting = _settings[skillId];
    if (setting == null) {
      throw StateError('skill user setting not found');
    }
    return setting;
  }

  @override
  Future<PutSkillUserSettingReceipt> putSkillUserSetting({
    required String skillId,
    required SkillUserSettingStatus status,
    required Map<String, Object?> configurationData,
    required String configurationSchemaDigest,
    required SkillMemoryPolicy memoryPolicy,
    required List<String> connectorConnectionRefs,
    required int expectedRevision,
    required String clientRequestId,
  }) async {
    final current = _settings[skillId];
    if ((current?.revision ?? 0) != expectedRevision) {
      throw StateError('skill user setting revision conflict');
    }
    final now = DateTime.now().toUtc().toIso8601String();
    final next = SkillUserSetting(
      id: 'setting:$skillId',
      accountId: 'fixture_assistant',
      skillId: skillId,
      status: status,
      configurationData: Map<String, Object?>.unmodifiable(configurationData),
      configurationSchemaDigest: configurationSchemaDigest,
      memoryPolicy: memoryPolicy,
      connectorConnectionRefs: List<String>.unmodifiable(
        connectorConnectionRefs,
      ),
      revision: expectedRevision + 1,
      createdAt: current?.createdAt ?? now,
      updatedAt: now,
    );
    final changed = current?.status != next.status;
    _settings[skillId] = next;
    return PutSkillUserSettingReceipt(
      setting: next,
      changed: changed,
      replayed: false,
    );
  }

  @override
  Future<AssistantRunEnvelopeWire> startCreationRun({
    required String sessionId,
    required String clientRequestId,
    required AssistantCreationRunIntent intent,
    AssistantContextSnapshot? contextSnapshot,
  }) async {
    return AssistantRunEnvelopeWire(
      runId: 'arn_mock_creation_${clientRequestId.trim()}',
      sessionId: sessionId,
      goal: <String?>[
        intent.draftTitle,
        intent.draftSummary,
        intent.bodyDigest,
      ].whereType<String>().join(' ').trim(),
      traceId: 'trace_mock_creation_${clientRequestId.trim()}',
      createdAt: DateTime.now().toUtc().toIso8601String(),
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
    String timezone = 'Asia/Shanghai',
    required String clientRequestId,
  }) async {
    if (clientRequestId.trim().isEmpty) {
      throw ArgumentError.value(clientRequestId, 'clientRequestId', 'required');
    }
    final now = DateTime.now().toUtc().toIso8601String();
    final subscription = SkillSubscriptionWire(
      subscriptionId: 'sub_mock_${_subscriptions.length + 1}',
      version: 1,
      createdByUserId: 'mock-user',
      skillId: skillId,
      domainId: domainId,
      tagRefs: tagRefs,
      searchQueryPlan: SkillSubscriptionSearchQueryPlanWire(
        rawText: rawText,
        queries: queries.isEmpty ? <String>[rawText] : queries,
      ),
      trigger: SkillSubscriptionTriggerWire(cron: cron, timezone: timezone),
      destination: const SkillSubscriptionDestinationWire(
        destinationType: SkillSubscriptionDestinationType.user,
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
      version: current.version + 1,
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
  Future<AssistantSessionWire> createAssistantSession({
    String summary = '',
    required String clientRequestId,
  }) async {
    final now = DateTime.now().toUtc().toIso8601String();
    return AssistantSessionWire(
      sessionId: 'asn_mock_personal_assistant',
      userId: 'mock-user',
      summary: summary,
      createdAt: now,
      updatedAt: now,
    );
  }

  @override
  Future<AssistantSessionListView> listAssistantSessions({
    int limit = kAssistantSessionListDefaultLimit,
    String cursor = '',
  }) async {
    return const AssistantSessionListView(items: <AssistantSessionWire>[]);
  }

  @override
  Future<AssistantSessionWire> getAssistantSession({
    required String sessionId,
  }) async {
    final now = DateTime.now().toUtc().toIso8601String();
    return AssistantSessionWire(
      sessionId: sessionId,
      userId: 'mock-user',
      createdAt: now,
      updatedAt: now,
    );
  }

  @override
  Future<AssistantTurnListView> listSessionTurns({
    required String sessionId,
    int limit = kAssistantTurnListDefaultLimit,
    String cursor = '',
  }) async {
    return const AssistantTurnListView(items: <AssistantTurnSummaryView>[]);
  }

  @override
  Future<AssistantRunEnvelopeWire> startAssistantRun({
    required String sessionId,
    required String text,
    required String clientRequestId,
    String turnType = 'user',
    String skillId = '',
    String domainId = '',
    List<AssistantIntersectionEvidenceRef> intersectionEvidenceRefs =
        const <AssistantIntersectionEvidenceRef>[],
  }) async {
    return AssistantRunEnvelopeWire(
      runId: 'arn_mock_personal_assistant',
      sessionId: sessionId,
      goal: text,
      traceId: 'trace_mock_personal_assistant',
      createdAt: DateTime.now().toUtc().toIso8601String(),
    );
  }

  @override
  Future<AssistantRunEnvelopeWire> getAssistantRun({
    required String runId,
  }) async {
    return AssistantRunEnvelopeWire(
      runId: runId,
      sessionId: 'asn_mock_personal_assistant',
      traceId: 'trace_mock_personal_assistant',
      createdAt: DateTime.now().toUtc().toIso8601String(),
    );
  }

  @override
  Future<AssistantRunEnvelopeWire> cancelAssistantRun({
    required String runId,
    required String commandRequestId,
  }) {
    return getAssistantRun(runId: runId);
  }

  @override
  Future<AssistantRunEnvelopeWire> pauseAssistantRun({
    required String runId,
    required String commandRequestId,
    String reason = '',
  }) {
    return getAssistantRun(runId: runId);
  }

  @override
  Future<AssistantRunEnvelopeWire> resumeAssistantRun({
    required String runId,
    required String commandRequestId,
  }) {
    return getAssistantRun(runId: runId);
  }

  @override
  Future<AssistantRunEnvelopeWire> steerAssistantRun({
    required String runId,
    required String commandRequestId,
    required String instruction,
  }) {
    return getAssistantRun(runId: runId);
  }

  @override
  Future<AssistantToolApprovalResult> approveAssistantToolUse({
    required String runId,
    required String toolInvocationId,
    required String commandRequestId,
    required String decision,
    required String approvalPermit,
    String? installationId,
    String? deviceId,
  }) async => AssistantToolApprovalResult(
    runId: runId,
    state: decision == 'approved' ? 'executing' : 'cancelled',
  );

  @override
  Future<AssistantRunEnvelopeWire> submitDeviceActionReceipt({
    required String runId,
    required String toolInvocationId,
    required String commandRequestId,
    required AssistantDeviceActionExecutionReceipt receipt,
  }) => getAssistantRun(runId: runId);

  @override
  Stream<AssistantStreamEventWire> watchAssistantRunEvents({
    required String runId,
    String lastEventId = '',
  }) async* {
    final createdAt = DateTime.now().toUtc().toIso8601String();
    yield AssistantStreamEventWire(
      schema: 'assistant_stream_event',
      eventId: '$runId:run_started',
      sessionId: 'asn_mock_personal_assistant',
      runId: runId,
      seq: 1,
      eventType: AssistantStreamEventType.runStarted,
      payload: const <String, dynamic>{'status': 'running', 'restarted': false},
      createdAt: createdAt,
    );
    yield AssistantStreamEventWire(
      schema: 'assistant_stream_event',
      eventId: '$runId:process_replace',
      sessionId: 'asn_mock_personal_assistant',
      runId: runId,
      seq: 2,
      eventType: AssistantStreamEventType.processReplace,
      payload: const <String, dynamic>{'processes': <Object?>[]},
      createdAt: createdAt,
    );
    yield AssistantStreamEventWire(
      schema: 'assistant_stream_event',
      eventId: '$runId:searching',
      sessionId: 'asn_mock_personal_assistant',
      runId: runId,
      seq: 3,
      eventType: AssistantStreamEventType.processAppend,
      payload: const <String, dynamic>{
        'process': <String, dynamic>{
          'processId': 'searching',
          'scope': 'skill',
          'stage': 'searching',
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
      sessionId: 'asn_mock_personal_assistant',
      runId: runId,
      seq: 4,
      eventType: AssistantStreamEventType.answerDelta,
      payload: const <String, dynamic>{'text': '找私助 mock stream 已接通。'},
      createdAt: createdAt,
    );
    yield AssistantStreamEventWire(
      schema: 'assistant_stream_event',
      eventId: '$runId:completed',
      sessionId: 'asn_mock_personal_assistant',
      runId: runId,
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

/// 真实云侧 semantic label 的 `displayText` 是人类可读文案，绝不回传 wire id。
/// fixture 必须保持同一契约，否则页面会把 id 当文案展示而测不出泄漏。
const Map<String, String> _fixtureSemanticLabelTexts = <String, String>{
  'general': '通用',
  'life': '生活',
  'content': '内容',
  'finance': '财经',
  'travel': '旅行',
  'content_creation': '创作',
  'personal': '个人助理',
  'conversation': '会话',
  'circle': '圈子',
  'trip_organizer': '旅行组织者',
  'assistant.memory.preferences.read': '读取助手偏好',
  'assistant.learning.feedback_context.read': '使用脱敏的助手反馈摘要',
};

SkillCatalogSemanticLabel _fixtureSemanticLabel(String id) =>
    SkillCatalogSemanticLabel(
      id: id,
      displayText: _fixtureSemanticLabelTexts[id] ?? '标签·$id',
    );

/// 把同一个替身实例绑定到全部 assistant Facet provider。
/// 对应旧 `assistantRepositoryProvider.overrideWithValue(...)` 的等价语义。
///
/// 这是测试容器 wiring，不是业务 Repository 聚合或 App 运行时 Provider。
List<Override> assistantFacetOverrides(InMemoryAssistantFacets facets) {
  return <Override>[
    assistantSessionRunFacetProvider.overrideWithValue(facets),
    assistantRunControlFacetProvider.overrideWithValue(facets),
    assistantSkillCatalogFacetProvider.overrideWithValue(facets),
    assistantSkillSubscriptionFacetProvider.overrideWithValue(facets),
    assistantSkillUserSettingFacetProvider.overrideWithValue(facets),
    assistantSkillConsentFacetProvider.overrideWithValue(facets),
    assistantLearningFactAppendFacetProvider.overrideWithValue(facets),
    assistantPersonalizationFacetProvider.overrideWithValue(facets),
    assistantTaskQueryProvider.overrideWithValue(facets),
    assistantPreferenceFacetProvider.overrideWithValue(facets),
    assistantSearchRunFacetProvider.overrideWithValue(facets),
    assistantCreationRunFacetProvider.overrideWithValue(facets),
  ];
}

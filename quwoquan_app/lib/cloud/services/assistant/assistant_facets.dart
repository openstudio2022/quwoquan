/// Assistant 对象级 Facet 接口与共享类型（B8 批次阶段 3a 拆分产物）。
///
/// 本文件是 assistant 域端侧接口的唯一真相源：
/// - 8 个对象级窄接口（每个 ≤10 方法），替代旧聚合 `AssistantRepository`；
/// - 顶层共享类型（generated Skill/Consent/Setting、context snapshot、常量）。
///
/// B8 阶段 3b：Remote 失败一律抛结构化 `CloudException`，本文件不再提供
/// 任何"服务不可用时本地合成结果"的 fallback 构造器。
///
/// 消费者只依赖所需的窄 Facet；production 装配见
/// `lib/core/providers/app_providers_client_sync.dart`（Remote-only）。
library;

import 'package:quwoquan_app/assistant/assistant/page_context/domain/assistant_open_context.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

export 'package:quwoquan_app/application/assistant/skill_activity/skill_activity_query.dart';
export 'package:quwoquan_app/application/assistant/skill_data_control/skill_data_control_facet.dart';

export 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        AssistantAnswerRunIntent,
        AssistantCreationRunIntent,
        AssistantContextSnapshot,
        AssistantCreateSessionRequest,
        AssistantConsentMatrix,
        AssistantDeviceActionExecutionReceipt,
        AssistantEntryAction,
        AssistantEntryChip,
        AssistantEntryResponse,
        AssistantIntersectionEvidenceRef,
        AssistantLearningFactType,
        AssistantLearningFactTypeX,
        AssistantLearningFactAppendCommand,
        AssistantLearningFactReceipt,
        AssistantObjectGroundingView,
        AssistantPageContextType,
        AssistantPreference,
        AssistantPreferenceKind,
        AssistantPreferenceScope,
        AssistantPreferenceSourceType,
        AssistantPreferenceStatus,
        AssistantRunEnvelopeWire,
        AssistantRunIntent,
        AssistantRunStreamStateWire,
        AssistantReferralSource,
        AssistantReferralSourceX,
        AssistantRunTerminalFailureView,
        AssistantRunTerminalSnapshotView,
        AssistantRunVisibleProcessView,
        AssistantRunVisibleReferenceView,
        AssistantSearchRunIntent,
        AssistantSelectedPolicyRefView,
        AssistantSessionWire,
        AssistantSkillCatalogItemDetailView,
        AssistantSkillCatalogItemView,
        AssistantStartRunRequest,
        AssistantStreamEventType,
        AssistantStreamEventTypeX,
        AssistantStreamEventWire,
        AssistantTaskItemView,
        AssistantTaskSlice,
        AssistantTurnListView,
        AssistantTurnSummaryView,
        AssistantUserActionGroundingView,
        CitationDestination,
        FeedbackType,
        FeedbackTypeX,
        InteractionEventType,
        InteractionEventTypeX,
        PageContextAction,
        PageContextObjectRef,
        PageContextReceipt,
        PageContextSnapshot,
        PutSkillUserSettingReceipt,
        ReportPageContextCommand,
        SearchIntensity,
        SearchIntensityX,
        SkillSubscriptionDeliveryStateWire,
        SkillSubscriptionDestinationWire,
        SkillSubscriptionDestinationType,
        SkillSubscriptionDestinationTypeX,
        SkillSubscriptionOwnerWire,
        SkillSubscriptionSearchQueryPlanWire,
        SkillSubscriptionStatus,
        SkillSubscriptionStatusX,
        SkillSubscriptionTriggerWire,
        SkillSubscriptionWire,
        SkillConsent,
        SkillConsentListSlice,
        SkillActivityDisplayKey,
        SkillActivityDisplayKeyX,
        SkillActivityKind,
        SkillActivityKindX,
        SkillActivityRecoveryAction,
        SkillActivityRecoveryActionX,
        SkillActivitySlice,
        SkillActivityView,
        SkillDataControlAction,
        SkillDataControlActionX,
        SkillDataControlMutationReceipt,
        SkillDataControlRequest,
        SkillDataControlRequestStatus,
        SkillDataControlRequestStatusX,
        SkillUserSetting,
        SkillUserSettingListSlice,
        SkillUserSettingStatus,
        SkillUserSettingStatusX,
        SkillMemoryPolicy,
        SkillMemoryPolicyX,
        parseAssistantLearningFactTypeStrict,
        parseAssistantReferralSourceStrict,
        parseAssistantStreamEventTypeStrict,
        parseFeedbackTypeStrict,
        parseInteractionEventTypeStrict,
        parseSkillSubscriptionDestinationTypeStrict,
        parseSkillSubscriptionStatusStrict,
        parseSkillActivityDisplayKeyStrict,
        parseSkillActivityKindStrict,
        parseSkillActivityRecoveryActionStrict,
        parseSkillDataControlActionStrict,
        parseSkillDataControlRequestStatusStrict;
export 'package:quwoquan_app/assistant/generated/contracts/tool_use.g.dart'
    show ToolUseWire;

/// Assistant 任务/记忆等列表接口单次拉取条数（与网关约定一致，非 [CloudApiDefaults.pageLimit]）。
const int kAssistantListPageDefaultLimit = 32;

/// Assistant 技能目录单次拉取条数。
const int kAssistantSkillCatalogDefaultLimit = 64;

/// Assistant 技能订阅列表单次拉取条数。
const int kAssistantSkillSubscriptionsDefaultLimit = 20;

AssistantContextSnapshot assistantContextSnapshotFromOpenContext(
  AssistantOpenContext context, {
  String? userAction,
}) {
  final now = DateTime.now().toUtc();
  final pageType = assistantPageTypeForSource(context.source);
  final objectType = context.objectType?.trim() ?? '';
  final objectId = context.entityId?.trim() ?? '';
  final normalizedAction = userAction?.trim() ?? '';
  return AssistantContextSnapshot(
    capturedAt: now,
    pageType: pageType,
    pageObjects: <AssistantObjectGroundingView>[
      if (objectType.isNotEmpty && objectId.isNotEmpty)
        AssistantObjectGroundingView(
          objectTypeRef: objectType,
          objectId: objectId,
        ),
    ],
    userActions: <AssistantUserActionGroundingView>[
      if (normalizedAction.isNotEmpty)
        AssistantUserActionGroundingView(
          action: normalizedAction,
          objectTypeRef: objectType.isEmpty ? null : objectType,
          objectId: objectId.isEmpty ? null : objectId,
          occurredAt: now,
        ),
    ],
    consentMatrix: const AssistantConsentMatrix(canReadCurrentPage: true),
  );
}

/// 将端侧页面上下文映射到 [PageContext] 对象的唯一 generated wire。
PageContextSnapshot pageContextSnapshotFromOpenContext(
  AssistantOpenContext context, {
  String? userAction,
}) {
  final now = DateTime.now().toUtc();
  final objectType = context.objectType?.trim() ?? '';
  final objectId = context.entityId?.trim() ?? '';
  final normalizedAction = userAction?.trim() ?? '';
  return PageContextSnapshot(
    capturedAt: now,
    pageType: assistantPageTypeForSource(context.source),
    pageObjects: <PageContextObjectRef>[
      if (objectType.isNotEmpty && objectId.isNotEmpty)
        PageContextObjectRef(objectTypeRef: objectType, objectId: objectId),
    ],
    userActions: <PageContextAction>[
      if (normalizedAction.isNotEmpty)
        PageContextAction(
          actionType: normalizedAction,
          objectTypeRef: objectType.isEmpty ? null : objectType,
          objectId: objectId.isEmpty ? null : objectId,
        ),
    ],
    consentGranted: true,
  );
}

/// ListAssistantSessions 响应切片（items + 不透明 keyset nextCursor）。
///
/// items 复用 generated [AssistantSessionWire]，信封字段与
/// `assistant_session/fields.yaml` 的 `AssistantSessionListView`
/// 契约逐字对齐；本类只做薄解码，不承载第二套业务字段。
class AssistantSessionListPage {
  const AssistantSessionListPage({required this.items, this.nextCursor = ''});

  final List<AssistantSessionWire> items;

  /// 空字符串表示无更多数据。
  final String nextCursor;

  factory AssistantSessionListPage.fromJson(Map<String, dynamic> json) {
    return AssistantSessionListPage(
      items: ((json['items'] as List?) ?? const <dynamic>[])
          .whereType<Map>()
          .map(
            (item) =>
                AssistantSessionWire.fromJson(item.cast<String, dynamic>()),
          )
          .toList(growable: false),
      nextCursor: (json['nextCursor'] as String?)?.trim() ?? '',
    );
  }
}

/// 私助会话与 run 生命周期（含 SSE 事件流、历史查询面与取消）。
abstract class AssistantSessionRunFacet {
  /// [clientRequestId] 与 HTTP `Idempotency-Key` 必须是同一稳定 intent；
  /// 网络重试必须复用它，禁止由 Remote 或服务端随机补齐。
  Future<AssistantSessionWire> createAssistantSession({
    String summary = '',
    required String clientRequestId,
  });

  /// GET /assistant/sessions：owner 助手会话列表（updatedAt desc keyset 分页）。
  /// 历史抽屉与最近会话的唯一数据源；本地不得维护第二套会话存储。
  Future<AssistantSessionListPage> listAssistantSessions({
    int limit = kAssistantListPageDefaultLimit,
    String cursor = '',
  });

  Future<AssistantSessionWire> getAssistantSession({required String sessionId});

  /// GET /assistant/sessions/{sessionId}/turns：终态轮次摘要
  /// （createdAt desc keyset 分页），transcript 恢复与续聊的唯一数据源。
  Future<AssistantTurnListView> listSessionTurns({
    required String sessionId,
    int limit = kAssistantListPageDefaultLimit,
    String cursor = '',
  });

  Future<AssistantRunEnvelopeWire> startAssistantRun({
    required String sessionId,
    required String text,
    required String clientRequestId,
    List<AssistantIntersectionEvidenceRef> intersectionEvidenceRefs =
        const <AssistantIntersectionEvidenceRef>[],
  });

  Future<AssistantRunEnvelopeWire> getAssistantRun({required String runId});

  /// POST /assistant/runs/{runId}/cancel：取消运行中的 run；
  /// 已终态取消幂等返回当前信封。
  Future<AssistantRunEnvelopeWire> cancelAssistantRun({
    required String runId,
    required String commandRequestId,
  });

  Stream<AssistantStreamEventWire> watchAssistantRunEvents({
    required String runId,
    String lastEventId = '',
  });
}

abstract class AssistantRunControlFacet {
  Future<AssistantRunEnvelopeWire> pauseAssistantRun({
    required String runId,
    required String commandRequestId,
    String reason = '',
  });

  Future<AssistantRunEnvelopeWire> resumeAssistantRun({
    required String runId,
    required String commandRequestId,
  });

  Future<AssistantRunEnvelopeWire> steerAssistantRun({
    required String runId,
    required String commandRequestId,
    required String instruction,
  });

  Future<AssistantRunEnvelopeWire> continueAssistantToolUse({
    required String runId,
    required String toolUseId,
    required String commandRequestId,
    required String decision,
    required String continuationToken,
    AssistantDeviceActionExecutionReceipt? executionReceipt,
  });
}

/// 技能订阅（创建/列表/状态流转）。
abstract class AssistantSkillSubscriptionFacet {
  Future<List<SkillSubscriptionWire>> listSkillSubscriptions({
    int limit = kAssistantSkillSubscriptionsDefaultLimit,
    String status = '',
  });

  Future<SkillSubscriptionWire> getSkillSubscription({
    required String subscriptionId,
  });

  Future<SkillSubscriptionWire> createSkillSubscription({
    required String skillId,
    String domainId = 'assistant',
    List<String> tagRefs = const <String>[],
    required String rawText,
    List<String> queries = const <String>[],
    String cron = '0 8 * * *',
    String timezone = 'Asia/Shanghai',
    required String clientRequestId,
  });

  Future<SkillSubscriptionWire> updateSkillSubscriptionStatus({
    required String subscriptionId,
    required String status,
    required String clientRequestId,
  });
}

/// 当前 active SkillPackageRelease 的用户目录投影。
abstract class AssistantSkillCatalogFacet {
  Future<List<AssistantSkillCatalogItemView>> listSkillCatalog({
    int limit = kAssistantSkillCatalogDefaultLimit,
  });

  Future<AssistantSkillCatalogItemDetailView> getSkillCatalogItem({
    required String skillId,
  });
}

/// 用户对 Skill 的显式启用状态与配置；缺少记录表示 package default。
abstract class AssistantSkillUserSettingFacet {
  Future<List<SkillUserSetting>> listSkillUserSettings({
    int limit = kAssistantSkillCatalogDefaultLimit,
  });

  Future<SkillUserSetting> getSkillUserSetting({required String skillId});

  Future<PutSkillUserSettingReceipt> putSkillUserSetting({
    required String skillId,
    required SkillUserSettingStatus status,
    required Map<String, Object?> configurationData,
    required String configurationSchemaDigest,
    required SkillMemoryPolicy memoryPolicy,
    required List<String> connectorConnectionRefs,
    required int expectedRevision,
    required String clientRequestId,
  });
}

/// 技能授权（consent 查询/授予/撤回）。
abstract class AssistantSkillConsentFacet {
  Future<List<SkillConsent>> listConsents();

  Future<SkillConsent> grantSkillConsent({
    required String skillId,
    required List<String> grantedScopes,
    required String clientRequestId,
  });

  Future<void> revokeSkillConsent({
    required String skillId,
    required String clientRequestId,
  });
}

/// 用户学习事实的单轨 append command。
abstract class AssistantLearningFactAppendFacet {
  Future<AssistantLearningFactReceipt> appendUserFact({
    required AssistantLearningFactAppendCommand request,
  });
}

/// 入口个性化（页面上下文上报、欢迎语与建议动作）。
abstract class AssistantPersonalizationFacet {
  Future<PageContextReceipt> reportPageContext({
    required AssistantOpenContext context,
    String? userAction,
  });

  Future<AssistantEntryResponse> getAssistantEntry({
    required AssistantOpenContext context,
  });
}

/// 私助个人任务只读列表。
abstract class AssistantPersonalDataFacet {
  /// GET /assistant/tasks
  Future<List<AssistantTaskItemView>> listAssistantTasks({
    int limit = kAssistantListPageDefaultLimit,
    String? status,
  });
}

/// 用户显式助手偏好（即时设置、可见、遗忘与撤销恢复）。
abstract class AssistantPreferenceFacet {
  Future<AssistantPreference> setAssistantPreference({
    required AssistantPreferenceScope scope,
    String sessionId = '',
    required AssistantPreferenceKind kind,
    required String value,
    required AssistantPreferenceSourceType sourceType,
    String sourceSessionId = '',
    bool confirmed = false,
  });

  Future<List<AssistantPreference>> listAssistantPreferences({
    AssistantPreferenceScope? scope,
    String sessionId = '',
    AssistantPreferenceStatus status = AssistantPreferenceStatus.active,
  });

  Future<AssistantPreference> revokeAssistantPreference({
    required String preferenceId,
  });

  Future<AssistantPreference> restoreAssistantPreference({
    required String preferenceId,
  });
}

/// 小趣搜（全网结果综合）。
abstract class AssistantSearchRunFacet {
  Future<AssistantRunTerminalSnapshotView> executeAssistantSearch({
    required String query,
    required String sessionClientRequestId,
    required String runClientRequestId,
    SearchIntensity searchIntensity = SearchIntensity.medium,
    AssistantContextSnapshot? contextSnapshot,
  });
}

/// 创作辅助同样只创建 [AssistantRun]，不拥有独立模型执行路由。
abstract class AssistantCreationRunFacet {
  Future<AssistantRunEnvelopeWire> startCreationRun({
    required String sessionId,
    required String clientRequestId,
    required AssistantCreationRunIntent intent,
    AssistantContextSnapshot? contextSnapshot,
  });
}

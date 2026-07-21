/// Assistant 对象级 Facet 接口与共享类型（B8 批次阶段 3a 拆分产物）。
///
/// 本文件是 assistant 域端侧接口的唯一真相源：
/// - 8 个对象级窄接口（每个 ≤10 方法），替代旧聚合 `AssistantRepository`；
/// - 顶层共享类型（[AssistantSkillConsent]、context snapshot、常量）。
///
/// B8 阶段 3b：Remote 失败一律抛结构化 `CloudException`，本文件不再提供
/// 任何"服务不可用时本地合成结果"的 fallback 构造器。
///
/// 消费者只依赖所需的窄 Facet；production 装配见
/// `lib/core/providers/app_providers_client_sync.dart`（Remote-only）。
library;

import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/assistant/generated/contracts/assistant_conversation.g.dart';
import 'package:quwoquan_app/assistant/generated/contracts/assistant_stream_event.g.dart';
import 'package:quwoquan_app/assistant/generated/contracts/assistant_turn_envelope.g.dart';
import 'package:quwoquan_app/assistant/generated/contracts/skill_subscription.g.dart';
import 'package:quwoquan_app/assistant/generated/enums/assistant_runtime_enums.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_cloud_api_wire.g.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';

export 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_cloud_api_wire.g.dart'
    show
        AssistantInteractionReportBatchAck,
        AssistantIntersectionEvidenceRef,
        AssistantPolicyView,
        AssistantPreferenceFact,
        AssistantPreferenceFactListView,
        AssistantEntryPersonalizationChipView,
        AssistantEntryPersonalizationView,
        AssistantCreationSuggestRequest,
        AssistantCreationSuggestResponse,
        AssistantReportPageContextRequestWire,
        AssistantScorecardReportBatchAck,
        AssistantSearchCitationView,
        AssistantSearchResultView,
        AssistantSearchXiaoquRequestWire,
        AssistantSuggestedHomepageView,
        AssistantSkillCatalogItemView,
        AssistantTurnListView,
        AssistantTurnSummaryView,
        AssistantUserTaskView,
        InteractionEvent,
        PageContextAck,
        SuggestedAction,
        SuggestedActionListView,
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
export 'package:quwoquan_app/assistant/generated/enums/assistant_runtime_enums.g.dart'
    show
        AssistantPreferenceKind,
        AssistantPreferenceKindX,
        AssistantPreferenceScope,
        AssistantPreferenceScopeX,
        AssistantPreferenceSourceType,
        AssistantPreferenceSourceTypeX,
        AssistantPreferenceStatus,
        AssistantPreferenceStatusX;

const String kPersonalContentAccessSkillId = 'personal_content_access';

/// Assistant 任务/记忆等列表接口单次拉取条数（与网关约定一致，非 [CloudApiDefaults.pageLimit]）。
const int kAssistantListPageDefaultLimit = 32;

/// Assistant 技能目录单次拉取条数。
const int kAssistantSkillCatalogDefaultLimit = 64;

/// Assistant 技能订阅列表单次拉取条数。
const int kAssistantSkillSubscriptionsDefaultLimit = 20;

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
    final revokedAt = (json['revokedAt'] ?? '').toString().trim();
    return AssistantSkillConsent(
      skillId: (json['skillId'] ?? '').toString().trim(),
      grantedScope: (json['grantedScope'] ?? kPersonalContentAccessSkillId)
          .toString()
          .trim(),
      // 服务端必须显式确认 granted=true；字段缺失、false 或已有撤回时间均失败关闭。
      granted: json['granted'] == true && revokedAt.isEmpty,
      updatedAt:
          DateTime.tryParse((json['grantedAt'] ?? '').toString()) ??
          DateTime.now(),
    );
  }

  Map<String, dynamic> toJson() => <String, dynamic>{
    'skillId': skillId,
    'grantedScope': grantedScope,
    'granted': granted,
    'grantedAt': updatedAt.toIso8601String(),
  };
}

Map<String, dynamic> assistantContextSnapshotFromOpenContext(
  AssistantOpenContext context, {
  String? operationId,
}) {
  final now = DateTime.now().toUtc().toIso8601String();
  final pageType = assistantPageTypeForSource(context.source);
  final objectType = context.objectType?.trim() ?? '';
  final objectId = context.entityId?.trim() ?? '';
  return <String, dynamic>{
    'snapshotVersion': 'assistant_context_v1',
    'capturedAt': now,
    'routeId': AppUiSurfaces.personalAssistantDialog.routeId,
    'surfaceId': AppUiSurfaces.personalAssistantDialog.id,
    if (operationId != null && operationId.trim().isNotEmpty)
      'operationId': operationId.trim(),
    'pageType': pageType,
    'sourceSurfaceId': context.source.name,
    'experienceLevel': context.experienceLevel.name,
    'visitTarget': context.visitTarget.targetKey,
    if (objectType.isNotEmpty && objectId.isNotEmpty)
      'pageObjects': <Map<String, dynamic>>[
        <String, dynamic>{
          'objectTypeRef': objectType,
          'objectId': objectId,
          if ((context.hints['title'] ?? '').toString().trim().isNotEmpty)
            'title': context.hints['title'].toString().trim(),
          if ((context.hints['snippet'] ?? '').toString().trim().isNotEmpty)
            'snippet': context.hints['snippet'].toString().trim(),
        },
      ],
    if (context.intersectionEvidenceRefs.isNotEmpty)
      'intersectionEvidenceRefs': context.intersectionEvidenceRefs
          .map((ref) => ref.toJson())
          .toList(growable: false),
    if ((context.tab ?? '').trim().isNotEmpty)
      'matchedSegments': <String>[context.tab!.trim()],
    if ((context.dimension ?? '').trim().isNotEmpty)
      'matchedInterestTags': <String>[context.dimension!.trim()],
    'consentMatrix': const <String, dynamic>{
      'canReadCurrentPage': true,
      'canReadConversation': false,
      'canUseProfile': true,
      'canUseRelationshipGraph': true,
      'canUseTags': true,
      'canDeliverProactively': false,
      'consentSource': 'app_open_context',
      'consentVersion': 'assistant_context_v1',
    },
  };
}

/// ListAssistantConversations 响应切片（items + 不透明 keyset nextCursor）。
///
/// items 复用 generated [AssistantConversationWire]，信封字段与
/// `assistant_conversation/fields.yaml` 的 `AssistantConversationListView`
/// 契约逐字对齐；本类只做薄解码，不承载第二套业务字段。
class AssistantConversationListPage {
  const AssistantConversationListPage({
    required this.items,
    this.nextCursor = '',
  });

  final List<AssistantConversationWire> items;

  /// 空字符串表示无更多数据。
  final String nextCursor;

  factory AssistantConversationListPage.fromJson(Map<String, dynamic> json) {
    return AssistantConversationListPage(
      items: ((json['items'] as List?) ?? const <dynamic>[])
          .whereType<Map>()
          .map(
            (item) => AssistantConversationWire.fromJson(
              item.cast<String, dynamic>(),
            ),
          )
          .toList(growable: false),
      nextCursor: (json['nextCursor'] as String?)?.trim() ?? '',
    );
  }
}

/// 私助会话与 run 生命周期（含 SSE 事件流、历史查询面与取消）。
abstract class AssistantConversationRunFacet {
  Future<AssistantConversationWire> createAssistantConversation({
    String summary = '',
  });

  /// GET /assistant/conversations：owner 会话列表（updatedAt desc keyset 分页）。
  /// 历史抽屉与最近会话的唯一数据源；本地不得维护第二套会话存储。
  Future<AssistantConversationListPage> listAssistantConversations({
    int limit = kAssistantListPageDefaultLimit,
    String cursor = '',
  });

  Future<AssistantConversationWire> getAssistantConversation({
    required String conversationId,
  });

  /// GET /assistant/conversations/{conversationId}/turns：终态轮次摘要
  /// （createdAt desc keyset 分页），transcript 恢复与续聊的唯一数据源。
  Future<AssistantTurnListView> listConversationTurns({
    required String conversationId,
    int limit = kAssistantListPageDefaultLimit,
    String cursor = '',
  });

  Future<AssistantTurnEnvelopeWire> startAssistantRun({
    required String conversationId,
    required String text,
    String turnType = 'user',
    String skillId = '',
    String domainId = '',
    List<AssistantIntersectionEvidenceRef> intersectionEvidenceRefs =
        const <AssistantIntersectionEvidenceRef>[],
  });

  Future<AssistantTurnEnvelopeWire> getAssistantRun({required String runId});

  /// POST /assistant/runs/{runId}/cancel：取消运行中的 run；
  /// 已终态取消幂等返回当前信封。
  Future<AssistantTurnEnvelopeWire> cancelAssistantRun({required String runId});

  Stream<AssistantStreamEventWire> watchAssistantRunEvents({
    required String runId,
  });
}

/// 技能订阅（创建/列表/状态流转）。
abstract class AssistantSkillSubscriptionFacet {
  Future<List<SkillSubscriptionWire>> listSkillSubscriptions({
    int limit = kAssistantSkillSubscriptionsDefaultLimit,
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
}

/// 技能授权（consent 查询/授予/撤回）。
abstract class AssistantSkillConsentFacet {
  Future<List<AssistantSkillConsent>> listConsents();

  Future<AssistantSkillConsent> grantSkillConsent({
    required String skillId,
    String grantedScope = kPersonalContentAccessSkillId,
  });

  Future<void> revokeSkillConsent({required String skillId});
}

/// 学习信号 append-only 上报（交互事件与评分卡）。
abstract class AssistantLearningAppendFacet {
  Future<AssistantInteractionReportBatchAck> reportInteractionEvents({
    required List<InteractionEvent> events,
  });

  Future<AssistantScorecardReportBatchAck> reportScorecards({
    required List<Scorecard> scorecards,
  });
}

/// 入口个性化（policy、页面上下文上报、欢迎语与建议动作）。
abstract class AssistantPersonalizationFacet {
  Future<AssistantPolicyView> getPolicySnapshot({
    String policyVersionHint = '',
  });

  Future<PageContextAck> reportPageContext({
    required AssistantOpenContext context,
    String? userAction,
    List<Map<String, dynamic>> userActions = const <Map<String, dynamic>>[],
  });

  Future<AssistantEntryPersonalizationView> getEntryPersonalization({
    required AssistantOpenContext context,
  });

  Future<SuggestedActionListView> getSuggestedActions({
    required AssistantOpenContext context,
  });
}

/// 私助个人数据只读列表（任务/记忆/技能目录）。
abstract class AssistantPersonalDataFacet {
  /// GET /assistant/tasks
  Future<List<AssistantUserTaskView>> listAssistantTasks({
    int limit = kAssistantListPageDefaultLimit,
    String? status,
  });

  /// GET /assistant/skills
  Future<List<AssistantSkillCatalogItemView>> listSkillCatalog({
    int limit = kAssistantSkillCatalogDefaultLimit,
  });
}

/// 用户显式偏好事实（即时设置、可见、遗忘与撤销恢复）。
abstract class AssistantPreferenceFactFacet {
  Future<AssistantPreferenceFact> setAssistantPreference({
    required AssistantPreferenceScope scope,
    String conversationId = '',
    required AssistantPreferenceKind kind,
    required String value,
    required AssistantPreferenceSourceType sourceType,
  });

  Future<List<AssistantPreferenceFact>> listAssistantPreferences({
    AssistantPreferenceScope? scope,
    String conversationId = '',
    AssistantPreferenceStatus status = AssistantPreferenceStatus.active,
  });

  Future<AssistantPreferenceFact> revokeAssistantPreference({
    required String preferenceId,
  });

  Future<AssistantPreferenceFact> restoreAssistantPreference({
    required String preferenceId,
  });
}

/// 小趣搜（全网结果综合）。
abstract class AssistantXiaoquSearchFacet {
  Future<AssistantSearchResultView> searchXiaoquResults({
    required String query,
    String searchIntensity = 'balanced',
    Map<String, dynamic>? contextSnapshot,
  });
}

/// 创作助手建议（标签/主页/标题摘要）。
abstract class AssistantCreationSuggestFacet {
  Future<AssistantCreationSuggestResponse> suggestCreationAssistance({
    required AssistantCreationSuggestRequest request,
  });
}

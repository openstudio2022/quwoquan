import 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_cloud_api_wire.g.dart'
    show AssistantIntersectionEvidenceRef;
import 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_runtime_enums.g.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';

/// 打开私助时的来源。
enum AssistantSource {
  home,
  discovery,
  circles,
  article,
  profile,
  chat,
  create,
  search,
}

AssistantPageContextType assistantPageTypeForSource(AssistantSource? source) {
  switch (source) {
    case AssistantSource.home:
      return AssistantPageContextType.home;
    case AssistantSource.discovery:
      return AssistantPageContextType.discovery;
    case AssistantSource.circles:
      return AssistantPageContextType.circles;
    case AssistantSource.article:
      return AssistantPageContextType.article;
    case AssistantSource.profile:
      return AssistantPageContextType.profile;
    case AssistantSource.chat:
      return AssistantPageContextType.chat;
    case AssistantSource.create:
      return AssistantPageContextType.create;
    case AssistantSource.search:
      return AssistantPageContextType.search;
    case null:
      return AssistantPageContextType.home;
  }
}

/// 将页面入口显式投影为 Assistant 服务契约的转介来源。
///
/// 没有入口上下文时，来源为独立助手会话，不能伪造为首页入口。
AssistantReferralSource assistantReferralSourceForOpenContext(
  AssistantOpenContext? context,
) {
  return switch (context?.source) {
    AssistantSource.home => AssistantReferralSource.home,
    AssistantSource.discovery => AssistantReferralSource.discovery,
    AssistantSource.circles => AssistantReferralSource.circles,
    AssistantSource.article => AssistantReferralSource.article,
    AssistantSource.profile => AssistantReferralSource.profile,
    AssistantSource.chat => AssistantReferralSource.chat,
    AssistantSource.create => AssistantReferralSource.create,
    AssistantSource.search => AssistantReferralSource.search,
    null => AssistantReferralSource.assistantSession,
  };
}

/// 打开私助时的上下文，供半弹窗与会话页共用。
class AssistantOpenContext {
  const AssistantOpenContext({
    required this.source,
    required this.visitTarget,
    required this.experienceLevel,
    this.tab,
    this.dimension,
    this.entityId,
    this.objectType,
    this.sessionId = '',
    this.intersectionEvidenceRefs = const <AssistantIntersectionEvidenceRef>[],
    this.hints = const {},
  });

  final AssistantSource source;

  /// 发现页 tab id、创作子步骤等。
  final String? tab;

  /// 圈子页维度 id。
  final String? dimension;

  /// 作者/圈子等实体 id。
  final String? entityId;

  /// 被打开对象的类型：post / circle / entity / user（B2 上下文透传，供小趣按需解释）。
  final String? objectType;

  /// 指定恢复的云端会话；空表示由页面按最近会话恢复（历史抽屉/最近会话入口）。
  final String sessionId;

  /// 交集入口的最小引用；服务端必须以当前 actor 回查后才能写入 grounding。
  final List<AssistantIntersectionEvidenceRef> intersectionEvidenceRefs;

  final VisitTarget visitTarget;
  final ExperienceLevel experienceLevel;

  /// 可选提示，如 hasAddedMedia、channelCount。
  final Map<String, dynamic> hints;

  AssistantOpenContext copyWith({
    AssistantSource? source,
    String? tab,
    String? dimension,
    String? entityId,
    String? objectType,
    String? sessionId,
    List<AssistantIntersectionEvidenceRef>? intersectionEvidenceRefs,
    VisitTarget? visitTarget,
    ExperienceLevel? experienceLevel,
    Map<String, dynamic>? hints,
  }) {
    return AssistantOpenContext(
      source: source ?? this.source,
      tab: tab ?? this.tab,
      dimension: dimension ?? this.dimension,
      entityId: entityId ?? this.entityId,
      objectType: objectType ?? this.objectType,
      sessionId: sessionId ?? this.sessionId,
      intersectionEvidenceRefs:
          intersectionEvidenceRefs ?? this.intersectionEvidenceRefs,
      visitTarget: visitTarget ?? this.visitTarget,
      experienceLevel: experienceLevel ?? this.experienceLevel,
      hints: hints ?? this.hints,
    );
  }
}

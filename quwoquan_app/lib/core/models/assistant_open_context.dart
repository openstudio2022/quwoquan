import 'package:quwoquan_app/core/models/visit_models.dart';

/// 打开私助时的来源。
enum AssistantSource {
  discovery,
  circles,
  article,
  profile,
  chat,
  create,
  search,
}

String assistantPageTypeForSource(AssistantSource? source) {
  switch (source) {
    case AssistantSource.discovery:
      return 'discovery';
    case AssistantSource.circles:
      return 'circles';
    case AssistantSource.article:
    case AssistantSource.profile:
      return 'home';
    case AssistantSource.chat:
      return 'chat';
    case AssistantSource.create:
      return 'create';
    case AssistantSource.search:
      return 'search';
    case null:
      return 'chat';
  }
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
    this.conversationId = '',
    this.intersectionRefs = const [],
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
  final String conversationId;

  /// 交集来源引用（路径制 tagRef 或 relation:{kind}:{objectId}），
  /// 供小趣按需深度解释时只引用真实来源，禁止编造（全局验收 G2）。
  final List<String> intersectionRefs;

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
    String? conversationId,
    List<String>? intersectionRefs,
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
      conversationId: conversationId ?? this.conversationId,
      intersectionRefs: intersectionRefs ?? this.intersectionRefs,
      visitTarget: visitTarget ?? this.visitTarget,
      experienceLevel: experienceLevel ?? this.experienceLevel,
      hints: hints ?? this.hints,
    );
  }
}

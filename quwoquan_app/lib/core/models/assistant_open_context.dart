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
    this.hints = const {},
  });

  final AssistantSource source;

  /// 发现页 tab id、创作子步骤等。
  final String? tab;

  /// 圈子页维度 id。
  final String? dimension;

  /// 作者/圈子等实体 id。
  final String? entityId;
  final VisitTarget visitTarget;
  final ExperienceLevel experienceLevel;

  /// 可选提示，如 hasAddedMedia、channelCount。
  final Map<String, dynamic> hints;

  AssistantOpenContext copyWith({
    AssistantSource? source,
    String? tab,
    String? dimension,
    String? entityId,
    VisitTarget? visitTarget,
    ExperienceLevel? experienceLevel,
    Map<String, dynamic>? hints,
  }) {
    return AssistantOpenContext(
      source: source ?? this.source,
      tab: tab ?? this.tab,
      dimension: dimension ?? this.dimension,
      entityId: entityId ?? this.entityId,
      visitTarget: visitTarget ?? this.visitTarget,
      experienceLevel: experienceLevel ?? this.experienceLevel,
      hints: hints ?? this.hints,
    );
  }
}

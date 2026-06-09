import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';

/// 创作者影响力分类（双向可解释性·生产端）。
///
/// stats 来源仅作为降级；优先消费服务端 `rm_author_impact` 真实反向聚合。
enum CreatorImpactCategory {
  relationship,
  appreciation,
  contribution,
  community,
  decision,
  knowledge,
  spread,
  audience,
}

/// 单条影响力事实：分类 + 真实计数 + 标签 + 自然语言叙事。
class CreatorImpactFact {
  const CreatorImpactFact({
    required this.category,
    required this.count,
    required this.label,
    required this.narrative,
  });

  final CreatorImpactCategory category;
  final int count;
  final String label;
  final String narrative;
}

/// 创作者影响力摘要：把真实聚合翻译为「你帮到了谁/促成了什么」叙事。
///
/// 约束（与发布军规一致）：
/// - [fromReadModel] 计数来自 `rm_author_impact`。
/// - [fromStats] 仅作为读模型不可用时的降级。
/// - count == 0 的维度直接隐藏（未打通/无数据不展示，禁止占位）。
class CreatorImpactSummary {
  const CreatorImpactSummary({required this.facts});

  final List<CreatorImpactFact> facts;

  bool get isEmpty => facts.isEmpty;

  /// 头条叙事：取计数最高的事实作为一句话总结（无数据时为空）。
  String get headline => facts.isEmpty ? '' : facts.first.narrative;

  factory CreatorImpactSummary.fromReadModel(CreatorImpactReadModel model) {
    final byCategory = <CreatorImpactCategory, int>{};
    for (final item in model.items) {
      final category = _categoryForHelpType(item.helpType);
      if (category == null || item.count <= 0) continue;
      byCategory[category] = (byCategory[category] ?? 0) + item.count;
    }
    final facts =
        byCategory.entries
            .map(
              (entry) => CreatorImpactFact(
                category: entry.key,
                count: entry.value,
                label: _impactLabel(entry.key),
                narrative: _impactNarrative(entry.key, entry.value),
              ),
            )
            .where((fact) => fact.count > 0)
            .toList()
          ..sort((a, b) => b.count.compareTo(a.count));
    return CreatorImpactSummary(facts: facts);
  }

  factory CreatorImpactSummary.fromStats(UserProfileStatsViewData stats) {
    final candidates = <CreatorImpactFact>[
      CreatorImpactFact(
        category: CreatorImpactCategory.relationship,
        count: stats.followerCount,
        label: UITextConstants.creatorImpactRelationshipLabel,
        narrative: UITextConstants.creatorImpactRelationshipNarrative(
          stats.followerCount,
        ),
      ),
      CreatorImpactFact(
        category: CreatorImpactCategory.appreciation,
        count: stats.likeCount,
        label: UITextConstants.creatorImpactAppreciationLabel,
        narrative: UITextConstants.creatorImpactAppreciationNarrative(
          stats.likeCount,
        ),
      ),
      CreatorImpactFact(
        category: CreatorImpactCategory.contribution,
        count: stats.postCount,
        label: UITextConstants.creatorImpactContributionLabel,
        narrative: UITextConstants.creatorImpactContributionNarrative(
          stats.postCount,
        ),
      ),
      CreatorImpactFact(
        category: CreatorImpactCategory.community,
        count: stats.circleCount,
        label: UITextConstants.creatorImpactCommunityLabel,
        narrative: UITextConstants.creatorImpactCommunityNarrative(
          stats.circleCount,
        ),
      ),
    ];

    final facts = candidates.where((f) => f.count > 0).toList()
      ..sort((a, b) => b.count.compareTo(a.count));

    return CreatorImpactSummary(facts: facts);
  }
}

CreatorImpactCategory? _categoryForHelpType(String helpType) {
  switch (helpType) {
    case 'relationship_help':
      return CreatorImpactCategory.relationship;
    case 'community_help':
      return CreatorImpactCategory.community;
    case 'decision_help':
      return CreatorImpactCategory.decision;
    case 'knowledge_help':
      return CreatorImpactCategory.knowledge;
    case 'spread_help':
      return CreatorImpactCategory.spread;
    case 'audience_help':
      return CreatorImpactCategory.audience;
    default:
      return null;
  }
}

String _impactLabel(CreatorImpactCategory category) {
  switch (category) {
    case CreatorImpactCategory.relationship:
      return UITextConstants.creatorImpactRelationshipLabel;
    case CreatorImpactCategory.appreciation:
      return UITextConstants.creatorImpactAppreciationLabel;
    case CreatorImpactCategory.contribution:
      return UITextConstants.creatorImpactContributionLabel;
    case CreatorImpactCategory.community:
      return UITextConstants.creatorImpactCommunityHelpLabel;
    case CreatorImpactCategory.decision:
      return UITextConstants.creatorImpactDecisionLabel;
    case CreatorImpactCategory.knowledge:
      return UITextConstants.creatorImpactKnowledgeLabel;
    case CreatorImpactCategory.spread:
      return UITextConstants.creatorImpactSpreadLabel;
    case CreatorImpactCategory.audience:
      return UITextConstants.creatorImpactAudienceLabel;
  }
}

String _impactNarrative(CreatorImpactCategory category, int count) {
  switch (category) {
    case CreatorImpactCategory.relationship:
      return UITextConstants.creatorImpactRelationshipNarrative(count);
    case CreatorImpactCategory.appreciation:
      return UITextConstants.creatorImpactAppreciationNarrative(count);
    case CreatorImpactCategory.contribution:
      return UITextConstants.creatorImpactContributionNarrative(count);
    case CreatorImpactCategory.community:
      return UITextConstants.creatorImpactCommunityHelpNarrative(count);
    case CreatorImpactCategory.decision:
      return UITextConstants.creatorImpactDecisionNarrative(count);
    case CreatorImpactCategory.knowledge:
      return UITextConstants.creatorImpactKnowledgeNarrative(count);
    case CreatorImpactCategory.spread:
      return UITextConstants.creatorImpactSpreadNarrative(count);
    case CreatorImpactCategory.audience:
      return UITextConstants.creatorImpactAudienceNarrative(count);
  }
}

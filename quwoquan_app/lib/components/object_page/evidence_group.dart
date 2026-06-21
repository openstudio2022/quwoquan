import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_point.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';

/// 交集证据组语义层（端侧唯一展示口径）。
///
/// 设计约束（必读要求 1 / 全局验收 G2）：
/// - 维度 / 证据组类型 [kind] 是开放字符串，端不写死闭集；未来云侧新增维度
///   （时间 coCohort、地点 coVisitedEntity 等）端侧零改动，未知 kind 走优雅降级。
/// - 展示文案、数字、实例全部来自云侧 [IntersectionPoint]，端不本地拼装事实。
/// - 数字 single-source（必读要求 2 事实清晰）：可见证据组数字之和 = 列表条数，
///   端禁止二次推导出与列表不一致的总数。
class EvidenceGroup {
  const EvidenceGroup._({
    required this.kind,
    required this.label,
    required this.count,
    required this.sampleText,
    required this.sampleAvatarUrls,
    required this.isRecommended,
  });

  /// 开放字符串：dimension 或证据组 kind（如 sharedFollowees / coVisitedEntity）。
  final String kind;

  /// 用户语言短句名词（如「共同关注」），云侧 displayText/label 真相源。
  final String label;

  /// 该证据组聚合的事实条数（如「共同关注 4」中的 4）。
  final int count;

  /// 实例化样本（某联系人名 / 某地点名 / 某篇内容标题），让交集可感知。
  final String sampleText;

  /// 头像簇（≤3），真实的人/对象信号，视觉锚。
  final List<String> sampleAvatarUrls;

  /// 推荐类（概率），必带「推荐」标识且排在事实之后，不伪装事实。
  final bool isRecommended;

  /// 展示降级排序。只用于 UI 排序，不用于拼装事实文案。
  int get rank => isRecommended ? 900 : evidenceKindRank(kind);

  /// 是否有可展示的有价值事实（必读要求 2 简洁：无价值不展示）。
  bool get hasMeaning =>
      label.trim().isNotEmpty || sampleText.trim().isNotEmpty;

  /// 从单个交集点投影为证据组。count 透传云侧值（0 表示无可量化条数，
  /// 展示侧 count>0 才显示数字，避免「0」空数字）；不在端侧编造计数。
  static EvidenceGroup fromPoint(IntersectionPoint p) {
    final label = p.displayText.trim().isNotEmpty
        ? p.displayText.trim()
        : p.label.trim();
    final sourceRef = p.sourceRef.trim();
    return EvidenceGroup._(
      kind: sourceRef.isNotEmpty ? sourceRef : p.dimension.trim(),
      label: label,
      count: p.count < 0 ? 0 : p.count,
      sampleText: p.sampleText.trim(),
      sampleAvatarUrls: p.sampleAvatarUrls,
      isRecommended: p.pointClass == 'recommended',
    );
  }

  /// 解析一条 reason 下的可见证据组，事实在前、推荐在后（挖掘强度排序）。
  static List<EvidenceGroup> fromReason(IntersectionReason reason) {
    final resolved = reason.intersectionPoints
        .where((p) => p.visibility != 'hidden')
        .map(EvidenceGroup.fromPoint)
        .where((g) => g.hasMeaning)
        .toList(growable: true);
    if (resolved.isEmpty) {
      final fallbackLabel = reason.primaryText.trim().isNotEmpty
          ? reason.primaryText.trim()
          : reason.connectionSummary.trim();
      if (fallbackLabel.isEmpty) {
        return const <EvidenceGroup>[];
      }
      resolved.add(
        EvidenceGroup._(
          kind: reason.dimension.trim(),
          label: fallbackLabel,
          count: reason.totalPointCount < 0 ? 0 : reason.totalPointCount,
          sampleText: reason.secondaryText.trim(),
          sampleAvatarUrls: const <String>[],
          isRecommended: reason.intersectionClass == 'recommended',
        ),
      );
    }
    final indexed = resolved.asMap().entries.toList(growable: false)
      ..sort((a, b) {
        final byRank = a.value.rank.compareTo(b.value.rank);
        if (byRank != 0) return byRank;
        // 同 rank 内保留云侧返回顺序，避免端侧重排语义事实。
        return a.key.compareTo(b.key);
      });
    return indexed.map((entry) => entry.value).toList(growable: false);
  }

  /// 数字 single-source：可见证据组 count 之和（端展示总数唯一来源）。
  static int totalCount(List<EvidenceGroup> groups) =>
      groups.fold<int>(0, (sum, g) => sum + g.count);

  static int evidenceKindRank(String kind) {
    switch (kind.trim()) {
      case 'sharedFollowees':
      case 'commonFollower':
      case 'commonContact':
      case 'followeeInObject':
      case 'followeeVisited':
      case 'followeeViewing':
      case 'followeeDiscussedThis':
        return 10;
      case 'coMemberCircle':
      case 'sharedCircle':
      case 'sameCompany':
      case 'sameTeam':
      case 'sameIndustry':
      case 'sharedEntityAttention':
      case 'coWishlistedEntity':
        return 20;
      case 'coVisitedEntity':
        return 30;
      case 'coCommented':
      case 'coSharedContent':
      case 'coCreatedContent':
      case 'sharedDiscussion':
        return 40;
      case 'sameSchool':
      case 'sameDepartment':
      case 'sameMajor':
      case 'sameCohort':
      case 'alumni':
      case 'alumniHere':
      case 'colleagueHere':
        return 50;
      case 'sharedTagSample':
        return 60;
      default:
        return 500;
    }
  }

}

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

  /// 开放字符串：dimension 或证据组 kind（如 mutualFriend / coVisitedEntity）。
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

  /// 是否有可展示的有价值事实（必读要求 2 简洁：无价值不展示）。
  bool get hasMeaning => label.trim().isNotEmpty || sampleText.trim().isNotEmpty;

  /// 从单个交集点投影为证据组。count 透传云侧值（0 表示无可量化条数，
  /// 展示侧 count>0 才显示数字，避免「0」空数字）；不在端侧编造计数。
  static EvidenceGroup fromPoint(IntersectionPoint p) {
    final label = p.displayText.trim().isNotEmpty
        ? p.displayText.trim()
        : p.label.trim();
    return EvidenceGroup._(
      kind: p.dimension.trim(),
      label: label,
      count: p.count < 0 ? 0 : p.count,
      sampleText: p.sampleText.trim(),
      sampleAvatarUrls: p.sampleAvatarUrls,
      isRecommended: p.pointClass == 'recommended',
    );
  }

  /// 解析一条 reason 下的可见证据组，事实在前、推荐在后（挖掘强度排序）。
  ///
  /// 交集点是首选真相源；当云侧暂未下发结构化 intersectionPoints（过渡期 / 仅
  /// displayText 的 reason）时，回落为单个证据组（label=displayText、count=sharedCount），
  /// 保证旧契约不掉链；维度仍取 reason.dimension 开放字符串。
  static List<EvidenceGroup> fromReason(IntersectionReason reason) {
    final groups = reason.intersectionPoints
        .where((p) => p.visibility != 'hidden')
        .map(EvidenceGroup.fromPoint)
        .where((g) => g.hasMeaning)
        .toList(growable: false);
    final resolved = groups.isNotEmpty
        ? groups
        : _fallbackFromReason(reason);
    final ordered = [...resolved]
      ..sort((a, b) {
        if (a.isRecommended != b.isRecommended) {
          return a.isRecommended ? 1 : -1;
        }
        return b.count.compareTo(a.count);
      });
    return ordered;
  }

  static List<EvidenceGroup> _fallbackFromReason(IntersectionReason reason) {
    final label = reason.displayText.trim().isNotEmpty
        ? reason.displayText.trim()
        : reason.label.trim();
    if (label.isEmpty) return const <EvidenceGroup>[];
    return <EvidenceGroup>[
      EvidenceGroup._(
        kind: reason.dimension.trim(),
        label: label,
        count: reason.sharedCount < 0 ? 0 : reason.sharedCount,
        sampleText: reason.displayName.trim(),
        sampleAvatarUrls: reason.avatarUrl.trim().isNotEmpty
            ? <String>[reason.avatarUrl.trim()]
            : const <String>[],
        isRecommended: reason.intersectionClass == 'affinity',
      ),
    ];
  }

  /// 数字 single-source：可见证据组 count 之和（端展示总数唯一来源）。
  static int totalCount(List<EvidenceGroup> groups) =>
      groups.fold<int>(0, (sum, g) => sum + g.count);
}

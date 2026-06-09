import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_dimension_tally.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_point.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/services/tag/tag_repository.dart';

/// 把 tag-service shared-tags 结果（[SharedTagView]）映射为对象页交集卡消费的
/// [IntersectionReason]，作为「对象对直打」交集来源的端侧规范化通路。
///
/// 约束（全局验收 G2 / 军规 R27）：
/// - `displayText` 透传单标签 `label`（数据锚点，非端本地拼装的交集句）；
/// - `dimension` 按路径制 tagRef 首段分组映射到 5 源闭集（identity/location/content/interest/relationship）；
/// - 过滤 tagRef / label 为空的脏数据。
List<IntersectionReason> sharedTagsToReasons(List<SharedTagView> shared) {
  return shared
      .where((s) => s.tagRef.trim().isNotEmpty && s.label.trim().isNotEmpty)
      .map((s) {
        final dimension = dimensionForTagRef(s.tagRef);
        final point = IntersectionPoint(
          pointId: s.tagRef,
          pointClass: 'fact',
          dimension: dimension,
          label: s.label,
          displayText: s.label,
          sourceRef: s.source.isNotEmpty ? s.source : 'tagRef',
        );
        return IntersectionReason(
          dimension: dimension,
          tagRefs: <String>[s.tagRef],
          label: s.label,
          strength: s.strength,
          source: s.source.isNotEmpty ? s.source : 'tagRef',
          displayText: s.label,
          intersectionPoints: <IntersectionPoint>[point],
          pointSummarySnapshotId: s.tagRef,
          factPointCount: 1,
          totalPointCount: 1,
          dimensionPointSummary: <IntersectionDimensionTally>[
            IntersectionDimensionTally(
              dimension: dimension,
              label: s.label,
              count: 1,
            ),
          ],
          pointClassLabel: '事实交集',
        );
      })
      .toList();
}

/// 按 tagRef 路径首段（数据工程四分组）映射到交集维度闭集。
String dimensionForTagRef(String tagRef) {
  final group = tagRef.split('/').first;
  switch (group) {
    case 'Topic':
      return 'interest';
    case 'Entity':
      return 'identity';
    case 'Format':
      return 'content';
    case 'Audience':
      return 'identity';
    default:
      return 'interest';
  }
}

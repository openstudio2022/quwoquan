import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_action_hint.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_dimension_tally.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_kind_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_point.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_representative_actor.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_kind_mapping.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_statement_synthesizer.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';

// Barrel re-export：消费者继续 import 本文件即可访问 kind 映射与句式合成公开 API；
// 拆分（R03 体量收敛）对 intersection_repository / T1 合约测试零改动。
export 'package:quwoquan_app/cloud/services/content/intersection_kind_mapping.dart';
export 'package:quwoquan_app/cloud/services/content/intersection_statement_synthesizer.dart';

List<IntersectionReason> rankAndDedupeIntersections(
  List<IntersectionReason> items,
) {
  final chosen = <String, IntersectionReason>{};
  for (final item in items) {
    final key = dedupeKeyForIntersection(item);
    final existing = chosen[key];
    if (existing == null || compareIntersectionRank(item, existing) < 0) {
      chosen[key] = item;
    }
  }
  final ranked = chosen.values.toList(growable: false);
  ranked.sort(compareIntersectionRank);
  return ranked;
}

/// §22.3 默认交集 inbox 的生命周期显隐规则（端侧单一真相源）：
/// - `expired` 永不进 UI；
/// - `archived` 不进默认列表（仅在历史筛选下展示）。
/// mock 与 remote 列表路径共用本过滤，保证端云显隐一致。
const Set<String> defaultInboxHiddenLifecycleStates = {'expired', 'archived'};

List<IntersectionReason> filterDefaultInboxLifecycle(
  List<IntersectionReason> items,
) {
  return items
      .where(
        (item) => !defaultInboxHiddenLifecycleStates.contains(
          item.lifecycleState.trim(),
        ),
      )
      .toList(growable: false);
}

String dedupeKeyForIntersection(IntersectionReason item) {
  final explicit = item.dedupeKey.trim();
  if (explicit.isNotEmpty) return explicit;
  final objectId = item.actionTargetId.trim().isNotEmpty
      ? item.actionTargetId.trim()
      : item.relationObjectId.trim().isNotEmpty
      ? item.relationObjectId.trim()
      : item.intersectionId.trim();
  final objectType = item.objectKind.trim();
  return 'viewer:$objectId:$objectType';
}

int compareIntersectionRank(IntersectionReason a, IntersectionReason b) {
  final byStrength = b.strength.compareTo(a.strength);
  if (byStrength != 0) return byStrength;
  final byBucket = timeBucketPriority(
    timeBucketForIntersection(a),
  ).compareTo(timeBucketPriority(timeBucketForIntersection(b)));
  if (byBucket != 0) return byBucket;
  final byAnchor = b.anchorUserWeight.compareTo(a.anchorUserWeight);
  if (byAnchor != 0) return byAnchor;
  final byCount = _mutualCountFor(b).compareTo(_mutualCountFor(a));
  if (byCount != 0) return byCount;
  final byType = _objectTypePriority(
    b.objectKind,
  ).compareTo(_objectTypePriority(a.objectKind));
  if (byType != 0) return byType;
  return dedupeKeyForIntersection(a).compareTo(dedupeKeyForIntersection(b));
}

String timeBucketForIntersection(IntersectionReason item) {
  final explicit = item.timeBucket.trim();
  if (explicit.isNotEmpty) return explicit;
  final freshAt = DateTime.tryParse(item.freshAt);
  if (freshAt == null) return 'lastMonth';
  final diff = DateTime.now().toUtc().difference(freshAt.toUtc());
  if (diff.inHours < 24) return 'today';
  if (diff.inHours < 48) return 'yesterday';
  if (diff.inDays < 7) return 'last7Days';
  if (diff.inDays < 31) return 'thisMonth';
  return 'lastMonth';
}

int timeBucketPriority(String bucket) {
  switch (bucket) {
    case 'today':
      return 0;
    case 'yesterday':
      return 1;
    case 'last7Days':
      return 2;
    case 'thisMonth':
      return 3;
    case 'lastMonth':
      return 4;
    default:
      return 5;
  }
}

List<IntersectionReason> fallbackInboxReasons() {
  return _withDefaultPointSummaries(<IntersectionReason>[
    IntersectionReason(
      dimension: 'relationship',
      intersectionId: 'ix_rel_1',
      intersectionClass: 'fact',
      displayName: '林清越',
      objectKind: 'person',
      primaryText: '4位关注对象正在讨论黄金投资',
      secondaryText: '都在黄金投资圈',
      weightTier: 'heavy',
      avatarUrl:
          'media/avatar/s/mock/seed/u_1494790108377-be9c29b29330/v1/avatar.jpg',
      totalPointCount: 4,
      strength: 0.9,
      kind: 'sharedFollowees',
      actionType: 'view',
      actionTargetId: 'u_lin',
      source: 'sharedFollowees',
      lifecycleState: 'new',
      freshAt: _isoMinusHours(3),
    ),
    IntersectionReason(
      dimension: 'relationship',
      intersectionId: 'ix_rel_2',
      intersectionClass: 'fact',
      displayName: '周屿',
      objectKind: 'person',
      primaryText: '你关注的2人也关注了周屿',
      weightTier: 'light',
      avatarUrl:
          'media/avatar/s/mock/seed/u_1500648767791-00dcc994a43e/v1/avatar.jpg',
      totalPointCount: 2,
      strength: 0.7,
      kind: 'sharedFollowees',
      actionType: 'view',
      actionTargetId: 'u_zhou',
      source: 'sharedFollowees',
      lifecycleState: 'stable',
      freshAt: _isoMinusHours(96),
    ),
    IntersectionReason(
      dimension: 'identity',
      intersectionId: 'ix_id_1',
      intersectionClass: 'fact',
      displayName: '新东方',
      objectKind: 'school',
      primaryText: '你和3位校友都来自新东方',
      secondaryText: '3位校友最近活跃',
      weightTier: 'light',
      avatarUrl:
          'media/avatar/s/mock/seed/u_1523050854058-8df90110c9f1/v1/avatar.jpg',
      totalPointCount: 3,
      strength: 0.82,
      kind: 'sameSchool',
      actionType: 'view',
      actionTargetId: 'fixture_homepage_school_neworiental',
      source: 'sameSchool',
      freshAt: _isoMinusHours(10),
    ),
    IntersectionReason(
      dimension: 'content',
      intersectionId: 'ix_ct_1',
      intersectionClass: 'fact',
      displayName: '黄金投资圈',
      objectKind: 'circle',
      primaryText: '你和8人都讨论过黄金投资圈',
      weightTier: 'heavy',
      avatarUrl:
          'media/avatar/s/mock/seed/u_1611974789855-9c2a0a7236a3/v1/avatar.jpg',
      totalPointCount: 8,
      strength: 0.88,
      kind: 'coCommented',
      actionType: 'join',
      actionTargetId: 'fixture_circle_gold_invest',
      source: 'coCommented',
      lifecycleState: 'reactivated',
      freshAt: _isoMinusHours(30),
    ),
    IntersectionReason(
      dimension: 'location',
      intersectionId: 'ix_loc_1',
      intersectionClass: 'fact',
      displayName: '西湖',
      objectKind: 'place',
      primaryText: '你和5人都去过西湖',
      weightTier: 'light',
      avatarUrl:
          'media/avatar/s/mock/seed/u_1606767341197-3d8e6f0a2a9b/v1/avatar.jpg',
      totalPointCount: 5,
      strength: 0.76,
      kind: 'coVisitedEntity',
      actionType: 'view',
      actionTargetId: 'homepage_sight_west_lake',
      source: 'coVisitedEntity',
      freshAt: _isoMinusHours(2),
    ),
    IntersectionReason(
      dimension: 'interest',
      intersectionId: 'ix_int_1',
      intersectionClass: 'affinity',
      displayName: '陆衡',
      objectKind: 'person',
      primaryText: '你可能和陆衡兴趣相投',
      secondaryText: '兴趣相似',
      weightTier: 'light',
      avatarUrl:
          'media/avatar/s/mock/seed/u_1507003211169-0a1dd7228f2d/v1/avatar.jpg',
      totalPointCount: 0,
      strength: 0.61,
      confidenceLabel: '推荐',
      modelReasonBucket: 'friend_suggestion',
      kind: 'affinity',
      actionType: 'view',
      actionTargetId: 'u_lu',
      source: 'affinity',
      freshAt: _isoMinusHours(20),
    ),
  ]).map(normalizeInboxReason).toList(growable: false);
}

/// 我的交集行归一（云侧 G2 模拟）：把 fixture/fallback 的紧凑事实补全为
/// 「代表人在数字前」的结构化富文本 + 可辨识 iconKey + 行动建议 + 去重键。
///
/// 单一真相源：已携带 [IntersectionReason.primarySpans] 的（云侧/fixture 直出富文本）
/// 不二次合成，只补 iconKey/dedupe/action 缺省；否则按 [kind] 闭集模板生成。
/// 代表人恒为句中蓝色可点名字（纯文本，无头像），数字片段进同维度下钻。
IntersectionReason normalizeInboxReason(IntersectionReason reason) {
  final kind = _resolveReasonKind(reason);
  if (reason.primarySpans.isNotEmpty) {
    return _ensureInboxDisplayMeta(reason, kind);
  }
  if (kind.isEmpty) {
    return _ensureInboxDisplayMeta(reason, kind);
  }
  final spans = buildInboxStatementSpans(reason, kind);
  if (spans.isEmpty) {
    return _ensureInboxDisplayMeta(reason, kind);
  }
  return _ensureInboxDisplayMeta(
    reason.copyWith(
      primaryText: spans.map((span) => span.text).join(),
      secondaryText: '',
      primarySpans: spans,
    ),
    kind,
  );
}

/// 补全展示元数据：iconKey / dedupeKey / actionHints / mutualCount 缺省回填，
/// 不覆盖 fixture/云侧已显式提供的值。
IntersectionReason _ensureInboxDisplayMeta(
  IntersectionReason reason,
  String kind,
) {
  final meta = IntersectionKindMetadata.of(kind);
  final objectKind = reason.objectKind.trim().isNotEmpty
      ? reason.objectKind.trim()
      : (meta?.objectKind ?? '');
  final objectId = reason.actionTargetId.trim();
  final mutualCount = reason.mutualCount > 0
      ? reason.mutualCount
      : intersectionMutualCountOf(reason);
  final hasCountSpan = reason.primarySpans.any(
    (span) => span.role.trim() == 'count',
  );
  final actorEvidenceTotalCount = reason.actorEvidenceTotalCount > 0
      ? reason.actorEvidenceTotalCount
      : mutualCount > 0
      ? mutualCount
      : hasCountSpan
      ? 1
      : 0;
  final representativeActor = _hydrateRepresentativeActor(reason, kind);
  // iconKey 回填降级链（与端 IntersectionIconResolver 同源）：reason.iconKey（云侧直出）→
  // 注册表 kind.iconKey（codegen）→ dimension 末级回退（codegen intersectionIconKeyByDimension，
  // 覆盖 affinity 等未登记 kind，保证不空图标）。
  final resolvedIconKey = reason.iconKey.trim().isNotEmpty
      ? reason.iconKey.trim()
      : (meta?.iconKey.trim().isNotEmpty ?? false)
      ? meta!.iconKey.trim()
      : (intersectionIconKeyByDimension[reason.dimension.trim()] ?? '');
  return reason.copyWith(
    iconKey: resolvedIconKey,
    dedupeKey: reason.dedupeKey.trim().isNotEmpty
        ? reason.dedupeKey
        : 'viewer:$objectId:$objectKind',
    mutualCount: mutualCount,
    actorEvidenceTotalCount: actorEvidenceTotalCount,
    actorEvidenceCompleteness:
        hasCountSpan && reason.actorEvidenceCompleteness.trim() != 'complete'
        ? 'complete'
        : reason.actorEvidenceCompleteness,
    representativeActor: representativeActor,
    actionHints: reason.actionHints.isNotEmpty
        ? reason.actionHints.map(_hydrateActionHint).toList(growable: false)
        : _genericActionHints(reason, kind),
  );
}

IntersectionRepresentativeActor? _hydrateRepresentativeActor(
  IntersectionReason reason,
  String kind,
) {
  final existing = reason.representativeActor;
  if (existing != null) {
    final target = _representativeTarget(
      existing.target,
      existing.actorId.trim(),
    );
    return existing.copyWith(
      actorId: existing.actorId.trim().isNotEmpty
          ? existing.actorId.trim()
          : (target?.objectId ?? ''),
      relationLabel: existing.relationLabel.trim().isNotEmpty
          ? existing.relationLabel
          : _representativeRelationLabel(kind),
      target: target,
    );
  }
  final name = _representativeDisplayName(reason, kind);
  if (name.isEmpty) return null;
  final actorId = reason.objectKind.trim() == 'person'
      ? reason.actionTargetId.trim()
      : 'mock_intersection_rep';
  if (actorId.isEmpty) return null;
  return IntersectionRepresentativeActor(
    actorId: actorId,
    displayName: name,
    relationLabel: _representativeRelationLabel(kind),
    privacyState: 'visible',
    target: IntersectionTarget(
      objectType: 'user',
      objectId: actorId,
      objectKind: 'person',
      routeId: 'userProfile',
    ),
    snapshotVersion: reason.intersectionId,
  );
}

IntersectionTarget? _representativeTarget(
  IntersectionTarget? target,
  String actorId,
) {
  final objectId = (target?.objectId.trim().isNotEmpty ?? false)
      ? target!.objectId.trim()
      : actorId;
  if (objectId.isEmpty) return target;
  return IntersectionTarget(
    objectType: 'user',
    objectId: objectId,
    objectKind: 'person',
    routeId: 'userProfile',
  );
}

String _representativeDisplayName(IntersectionReason reason, String kind) {
  if (reason.objectKind.trim() == 'person') {
    return reason.displayName.trim();
  }
  switch (kind.trim()) {
    case 'coCommented':
    case 'coLiked':
    case 'sharedDiscussion':
    case 'coSharedContent':
    case 'coCreatedContent':
      return '王然';
    case 'coVisitedEntity':
    case 'coWishlistedEntity':
      return '张可';
    case 'sameSchool':
    case 'sameDepartment':
    case 'sameMajor':
    case 'sameCohort':
    case 'alumni':
    case 'alumniHere':
      return '陈默';
    case 'sharedCircle':
    case 'coMemberCircle':
      return '周屿';
    default:
      return '林清越';
  }
}

String _representativeRelationLabel(String kind) {
  switch (kind.trim()) {
    case 'sharedFollowees':
    case 'followeeInObject':
    case 'followeeVisited':
    case 'followeeViewing':
    case 'followeeDiscussedThis':
      return '你关注的人';
    case 'sameSchool':
    case 'sameDepartment':
    case 'sameMajor':
    case 'sameCohort':
    case 'alumni':
    case 'alumniHere':
      return '校友';
    case 'sameCompany':
    case 'sameTeam':
      return '同事';
    case 'sameIndustry':
      return '同行';
    case 'sharedCircle':
    case 'coMemberCircle':
      return '同圈成员';
    case 'coVisitedEntity':
    case 'coWishlistedEntity':
      return '同游伙伴';
    default:
      return '联系人';
  }
}

List<IntersectionActionHint> _genericActionHints(
  IntersectionReason reason,
  String kind,
) {
  final meta = IntersectionKindMetadata.of(kind);
  final actionKey = meta?.primaryActionKey ?? 'ask_assistant';
  final actionMeta = IntersectionActionKeyMeta.of(actionKey);
  final objectKind = reason.objectKind.trim().isNotEmpty
      ? reason.objectKind.trim()
      : (meta?.objectKind ?? '');
  final objectId = reason.actionTargetId.trim();
  return <IntersectionActionHint>[
    IntersectionActionHint(
      actionKey: actionKey,
      label: DiscoveryFeedText.intersectionActionLabel(actionKey),
      target: objectId.isEmpty
          ? null
          : IntersectionTarget(
              objectId: objectId,
              objectKind: objectKind,
              routeId: intersectionRouteIdForObjectKind(objectKind),
            ),
      isPrimary: true,
      priority: 1,
      actionTier: actionMeta?.tier ?? 'light',
      requiredGates: actionMeta?.requiredGates ?? const <String>[],
      targetAvailability: actionMeta?.targetAvailability ?? 'available',
      dispatch: actionMeta?.dispatch ?? 'assistant',
    ),
  ];
}

IntersectionActionHint _hydrateActionHint(IntersectionActionHint hint) {
  final meta = IntersectionActionKeyMeta.of(hint.actionKey);
  if (meta == null) return hint;
  return hint.copyWith(
    actionTier: meta.tier,
    requiredGates: meta.requiredGates,
    targetAvailability: meta.targetAvailability,
    dispatch: meta.dispatch,
  );
}

/// 解析 reason 的标准 kind（一等字段 [IntersectionReason.kind] 为真相源）。
///
/// 候选优先级：reason.kind（codegen 解码自 kind/sourceRef 别名）→ 首个 point.sourceRef
/// （point 级 kind 真相源）→ reason.source（旧 fixture 兼容）。
/// 解析顺序：
/// 1. 先取命中 codegen [intersectionKindMetadata] 的注册表标准 kind；
/// 2. 退而取「非维度名」的非空候选——如 `affinity` 概率推荐类，注册表未登记 kind 但有
///    合成模板与降级展示语义；维度名（codegen [intersectionDimensionKeys] 闭集）不得被
///    误当 kind（避免把 source='relationship' 这类维度标签当成 kind）。
String _resolveReasonKind(IntersectionReason reason) {
  final candidates = <String>[
    reason.kind.trim(),
    for (final point in reason.intersectionPoints) point.sourceRef.trim(),
    reason.source.trim(),
  ];
  for (final candidate in candidates) {
    if (IntersectionKindMetadata.of(candidate) != null) return candidate;
  }
  for (final candidate in candidates) {
    if (candidate.isNotEmpty &&
        !intersectionDimensionKeys.contains(candidate)) {
      return candidate;
    }
  }
  return '';
}

IntersectionPoint _point({
  required String id,
  required String pointClass,
  required String dimension,
  required String label,
  required String displayText,
  String sourceRef = '',
  int count = 0,
  String sampleText = '',
  List<String> sampleAvatarUrls = const <String>[],
}) {
  return IntersectionPoint(
    pointId: id,
    pointClass: pointClass,
    dimension: dimension,
    label: label,
    displayText: displayText,
    sourceRef: sourceRef,
    visibility: 'public',
    count: count,
    sampleText: sampleText,
    sampleAvatarUrls: sampleAvatarUrls,
  );
}

IntersectionReason _withPoints(
  IntersectionReason reason,
  List<IntersectionPoint> points,
) {
  final visible = points
      .where((point) => point.visibility != 'hidden')
      .toList();
  final factCount = visible
      .where((point) => point.pointClass != 'recommended')
      .length;
  final recommendedCount = visible.length - factCount;
  final byDimension = <String, int>{};
  for (final point in visible) {
    byDimension[point.dimension] = (byDimension[point.dimension] ?? 0) + 1;
  }
  return reason.copyWith(
    intersectionPoints: visible,
    pointSummarySnapshotId: reason.intersectionId,
    factPointCount: factCount,
    recommendedPointCount: recommendedCount,
    totalPointCount: visible.length,
    dimensionPointSummary: byDimension.entries
        .map(
          (entry) => IntersectionDimensionTally(
            dimension: entry.key,
            count: entry.value,
          ),
        )
        .toList(growable: false),
    pointClassLabel: recommendedCount > 0 && factCount == 0 ? '推荐交集' : '事实交集',
    rankState: 'fresh',
  );
}

IntersectionReason _withDefaultPointSummary(IntersectionReason reason) {
  final pointClass = reason.intersectionClass == 'affinity'
      ? 'recommended'
      : 'fact';
  final shortLabel = reason.primaryText.trim().isNotEmpty
      ? reason.primaryText.trim()
      : reason.connectionSummary.trim();
  return _withPoints(reason, <IntersectionPoint>[
    _point(
      id: '${reason.intersectionId}_point',
      pointClass: pointClass,
      dimension: reason.dimension,
      label: shortLabel,
      displayText: shortLabel,
      sourceRef: reason.source,
      count: reason.totalPointCount,
      sampleText: reason.displayName,
      sampleAvatarUrls: reason.avatarUrl.trim().isNotEmpty
          ? <String>[reason.avatarUrl.trim()]
          : const <String>[],
    ),
  ]);
}

List<IntersectionReason> _withDefaultPointSummaries(
  List<IntersectionReason> reasons,
) {
  return reasons.map(_withDefaultPointSummary).toList(growable: false);
}

String _isoMinusHours(int hours) =>
    DateTime.now().toUtc().subtract(Duration(hours: hours)).toIso8601String();

int _mutualCountFor(IntersectionReason item) {
  if (item.mutualCount > 0) return item.mutualCount;
  for (final point in item.intersectionPoints) {
    if (point.count > 0) return point.count;
  }
  if (item.totalPointCount > 0) return item.totalPointCount;
  return 0;
}

int _objectTypePriority(String objectKind) {
  switch (objectKind.trim()) {
    case 'circle':
      return 5;
    case 'place':
      return 4;
    case 'content':
      return 3;
    case 'tag':
    case 'interest':
      return 2;
    case 'school':
      return 1;
    default:
      return 0;
  }
}

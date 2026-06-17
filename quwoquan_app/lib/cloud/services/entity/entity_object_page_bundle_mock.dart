part of 'entity_repository.dart';

ObjectPageBundle _objectPageBundleFromHomepage(
  HomepageDetail homepage, {
  required String referralSource,
  required String feedRequestId,
  required String recommendationTraceId,
  required String experimentBucket,
  required String rolloutCohort,
}) {
  final canonicalEntityId = _canonicalEntityId(homepage);
  final relationEdges = _mockRelationEdges(homepage, canonicalEntityId);
  final relationEdgeIds = relationEdges.map((edge) => edge.edgeId).toList();
  final relatedGroups = homepage.relatedGroups.isNotEmpty
      ? homepage.relatedGroups
      : _mockDefaultRelatedGroups(homepage);
  final highlights = homepage.contentPreview.isNotEmpty
      ? homepage.contentPreview
      : _mockDefaultContentPreview(homepage);
  return ObjectPageBundle(
    objectType: 'homepage',
    objectId: homepage.id,
    canonicalEntityId: canonicalEntityId,
    title: homepage.title,
    subtitle: homepage.subtitle,
    coverUrl: homepage.coverUrl,
    objectPageTemplate: _objectPageTemplate(homepage),
    tagRefs: homepage.categoryTags,
    stats: <String, dynamic>{
      'ratingCount': homepage.ratingCount,
      'relatedGroupCount': relatedGroups.length,
      'highlightCount': highlights.length,
    },
    intersectionReasons: _mockIntersectionReasons(homepage, relationEdges),
    highlightItems: highlights,
    contentSections: <String, dynamic>{
      'home': highlights.map((item) => item.toMap()).toList(growable: false),
      if (homepage.reviewSummary != null)
        'reviews': homepage.reviewSummary!.toMap(),
      'related': relatedGroups
          .map((item) => item.toMap())
          .toList(growable: false),
    },
    relatedObjects: relatedGroups,
    relationEdges: relationEdges,
    assistantContext: ObjectPageContext(
      objectType: 'homepage',
      objectId: homepage.id,
      canonicalEntityId: canonicalEntityId,
      tagRefs: homepage.categoryTags,
      entityRefs: <String>[canonicalEntityId],
      relationEdgeIds: relationEdgeIds,
      referralSource: referralSource,
      feedRequestId: feedRequestId,
      recommendationTraceId: recommendationTraceId,
      experimentBucket: experimentBucket,
      rolloutCohort: rolloutCohort,
    ),
    rolloutContext: ObjectPageRolloutContext(
      enabled: true,
      cohort: rolloutCohort.isEmpty ? 'object-homepage-alpha' : rolloutCohort,
      city: homepage.city ?? '',
      campus: homepage.homepageType == 'university' ? homepage.title : '',
      experimentBucket: experimentBucket,
      objectType: homepage.homepageType,
      assistantProactiveEnabled: true,
      relationEvidenceEnabled: true,
    ),
  );
}

List<ObjectRelationEdge> _mockRelationEdges(
  HomepageDetail homepage,
  String canonicalEntityId,
) {
  final relatedGroups = homepage.relatedGroups.isNotEmpty
      ? homepage.relatedGroups
      : _mockDefaultRelatedGroups(homepage);
  if (relatedGroups.isEmpty) {
    return <ObjectRelationEdge>[
      ObjectRelationEdge(
        edgeId: '${homepage.id}_co_tagged',
        edgeType: 'co_tagged',
        sourceObjectType: 'homepage',
        sourceObjectId: homepage.id,
        targetObjectType: 'homepage',
        targetObjectId: homepage.id,
        canonicalEntityId: canonicalEntityId,
        tagRefs: homepage.categoryTags,
        evidenceRefs: <String>[homepage.id],
        confidence: 0.72,
        createdAt: homepage.updatedAt,
      ),
    ];
  }
  return <ObjectRelationEdge>[
    for (final group in relatedGroups)
      ObjectRelationEdge(
        edgeId: '${homepage.id}_${group.circleId}_edge',
        edgeType: 'circle_under_entity',
        sourceObjectType: 'circle',
        sourceObjectId: group.circleId,
        targetObjectType: 'homepage',
        targetObjectId: homepage.id,
        canonicalEntityId: canonicalEntityId,
        tagRefs: homepage.categoryTags,
        evidenceRefs: <String>[group.circleId, homepage.id],
        confidence: 0.92,
        createdAt: homepage.updatedAt,
      ),
  ];
}

List<IntersectionReason> _mockIntersectionReasons(
  HomepageDetail homepage,
  List<ObjectRelationEdge> relationEdges,
) {
  final interestLabel = switch (homepage.homepageType) {
    'university' => '校园交集',
    'travel_photo' || 'sight' => '共同足迹',
    _ => '共同关注',
  };
  final firstEdge = relationEdges.isNotEmpty ? relationEdges.first : null;
  return <IntersectionReason>[
    _mockReasonWithPoint(
      IntersectionReason(
        dimension: 'interest',
        tagRefs: homepage.categoryTags,
        relationKind: 'mutual',
        relationObjectId: homepage.id,
        totalPointCount: homepage.categoryTags.length,
        strength: 0.86,
        primaryText: interestLabel,
        actionType: 'view_object',
        actionTargetId: homepage.id,
        source: 'tagRef',
      ),
      pointClass: 'recommended',
    ),
    _mockReasonWithPoint(
      IntersectionReason(
        dimension: 'relationship',
        tagRefs: homepage.categoryTags,
        relationKind: 'mutual',
        relationObjectId: firstEdge?.sourceObjectId ?? '',
        totalPointCount: relationEdges.length,
        strength: 0.78,
        primaryText: '相关圈子',
        actionType: 'join',
        actionTargetId: firstEdge?.sourceObjectId ?? '',
        source: 'followEdge',
      ),
      pointClass: 'fact',
    ),
  ];
}

IntersectionReason _mockReasonWithPoint(
  IntersectionReason reason, {
  required String pointClass,
}) {
  final point = IntersectionPoint(
    pointId: '${reason.actionTargetId}_${reason.dimension}',
    pointClass: pointClass,
    dimension: reason.dimension,
    label: reason.primaryText,
    displayText: reason.primaryText,
    sourceRef: reason.source,
    count: reason.totalPointCount,
    sampleText: reason.displayName,
    sampleAvatarUrls: reason.avatarUrl.trim().isNotEmpty
        ? <String>[reason.avatarUrl.trim()]
        : const <String>[],
  );
  final isRecommended = pointClass == 'recommended';
  return reason.copyWith(
    intersectionClass: isRecommended ? 'affinity' : 'fact',
    intersectionPoints: <IntersectionPoint>[point],
    pointSummarySnapshotId: reason.actionTargetId,
    factPointCount: isRecommended ? 0 : 1,
    recommendedPointCount: isRecommended ? 1 : 0,
    totalPointCount: 1,
    dimensionPointSummary: <IntersectionDimensionTally>[
      IntersectionDimensionTally(
        dimension: reason.dimension,
        label: reason.primaryText,
        count: 1,
      ),
    ],
    pointClassLabel: isRecommended ? '推荐交集' : '事实交集',
    recommendationTraceId: reason.actionTargetId,
    rankState: 'fresh',
  );
}

String _canonicalEntityId(HomepageDetail homepage) {
  final explicit = homepage.canonicalEntityId?.trim() ?? '';
  if (explicit.isNotEmpty) {
    return explicit;
  }
  final type = homepage.homepageType.trim();
  final slug = _canonicalSlug(homepage.title);
  if (type.isEmpty || slug.isEmpty) {
    return '';
  }
  return 'entity:$type:$slug';
}

String _canonicalSlug(String value) {
  final trimmed = value.trim().toLowerCase();
  if (trimmed.isEmpty) {
    return '';
  }
  final normalized = trimmed.replaceAll(RegExp(r'[\s/-]+'), '_');
  return normalized.replaceAll(RegExp(r'_+'), '_').replaceAll(
    RegExp(r'^_|_$'),
    '',
  );
}

String _objectPageTemplate(HomepageDetail homepage) {
  return switch (homepage.homepageType) {
    'university' => 'campus',
    'travel_photo' || 'sight' => 'travel_photo',
    _ => 'standard',
  };
}

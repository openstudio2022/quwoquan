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
    intersections: _mockObjectIntersections(homepage, relationEdges),
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
    'university' => '你和这所学校有校园交集',
    'travel_photo' || 'sight' => '你们都喜欢旅行与摄影',
    _ => '你们都关注这些内容',
  };
  final firstEdge = relationEdges.isNotEmpty ? relationEdges.first : null;
  return <IntersectionReason>[
    _mockReasonWithPoint(
      IntersectionReason(
        dimension: 'interest',
        tagRefs: homepage.categoryTags,
        relationKind: 'mutual',
        relationObjectId: homepage.id,
        label: interestLabel,
        sharedCount: homepage.categoryTags.length,
        strength: 0.86,
        displayText: interestLabel,
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
        label: '这里有你可能想加入的相关圈子',
        sharedCount: relationEdges.length,
        strength: 0.78,
        displayText: '这里有你可能想加入的相关圈子',
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
    label: reason.label,
    displayText: reason.displayText,
    sourceRef: reason.source,
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
        label: reason.label,
        count: 1,
      ),
    ],
    pointClassLabel: isRecommended ? '推荐交集' : '事实交集',
    recommendationTraceId: reason.actionTargetId,
    rankState: 'fresh',
  );
}

List<ObjectIntersection> _mockObjectIntersections(
  HomepageDetail homepage,
  List<ObjectRelationEdge> relationEdges,
) {
  final firstEdge = relationEdges.isNotEmpty ? relationEdges.first : null;
  final tagLabel = homepage.categoryTags.isNotEmpty
      ? homepage.categoryTags.first
      : homepage.title;
  return <ObjectIntersection>[
    ObjectIntersection(
      intersectionId: '${homepage.id}_fact_interest',
      dimension: 'interest',
      objectKind: 'homepage',
      objectId: homepage.id,
      shortLabel: '共同关注',
      evidenceLabel: tagLabel,
      actionType: 'view_object',
      actionLabel: '查看',
      strength: 0.86,
      confidenceLabel: '公开资料',
      surfaceScope: 'objectPage',
      privacyLevel: 'public',
      tagRefs: homepage.categoryTags,
      relationEdgeIds: firstEdge == null
          ? const <String>[]
          : <String>[firstEdge.edgeId],
      evidenceItems: <ObjectIntersectionEvidence>[
        ObjectIntersectionEvidence(
          evidenceId: '${homepage.id}_tag_evidence',
          evidenceType: 'tag',
          evidenceObjectId: tagLabel,
          evidenceLabel: tagLabel,
          source: 'tagRef',
          referralTarget: homepage.id,
          visibility: 'public',
        ),
      ],
    ),
    if (firstEdge != null)
      ObjectIntersection(
        intersectionId: '${homepage.id}_fact_circle',
        dimension: 'relationship',
        objectKind: 'circle',
        objectId: firstEdge.sourceObjectId,
        shortLabel: '相关圈子',
        evidenceLabel: firstEdge.sourceObjectId,
        actionType: 'join',
        actionLabel: '加入',
        strength: firstEdge.confidence,
        confidenceLabel: '公开关系',
        surfaceScope: 'objectPage',
        privacyLevel: 'public',
        tagRefs: firstEdge.tagRefs,
        relationEdgeIds: <String>[firstEdge.edgeId],
        evidenceItems: <ObjectIntersectionEvidence>[
          ObjectIntersectionEvidence(
            evidenceId: '${firstEdge.edgeId}_evidence',
            evidenceType: 'relationEdge',
            evidenceObjectId: firstEdge.sourceObjectId,
            evidenceLabel: '圈子关联到该对象',
            source: 'relationEdge',
            referralTarget: firstEdge.sourceObjectId,
            visibility: 'public',
          ),
        ],
      ),
  ];
}

String _canonicalEntityId(HomepageDetail homepage) {
  return 'entity:homepage:${homepage.id}';
}

String _objectPageTemplate(HomepageDetail homepage) {
  return switch (homepage.homepageType) {
    'university' => 'campus',
    'travel_photo' || 'sight' => 'travel_photo',
    _ => 'standard',
  };
}

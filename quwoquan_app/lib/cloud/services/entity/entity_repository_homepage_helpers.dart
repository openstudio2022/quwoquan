part of 'entity_repository.dart';

HomepageReviewSummaryData _mockDefaultReviewSummary(HomepageDetail homepage) {
  return HomepageReviewSummaryData(
    averageRating: homepage.averageRating ?? 4.6,
    ratingCount: homepage.ratingCount != 0 ? homepage.ratingCount : 18,
    highlightTags: homepage.categoryTags.isNotEmpty
        ? List<String>.from(homepage.categoryTags)
        : const <String>['体验稳定', '适合沉淀口碑'],
    dimensionScores: <HomepageReviewDimensionScore>[
      HomepageReviewDimensionScore(label: '环境', score: 4.6),
      HomepageReviewDimensionScore(label: '体验', score: 4.5),
      HomepageReviewDimensionScore(label: '推荐度', score: 4.7),
    ],
  );
}

List<HomepageContentPreview> _mockDefaultContentPreview(
  HomepageDetail homepage,
) {
  final title = homepage.title;
  return <HomepageContentPreview>[
    HomepageContentPreview(
      postId: '${homepage.id}_post_1',
      title: '$title 的体验笔记',
      summary: '从主页上下文进入内容挂载后的聚合。',
      contentType: 'article',
      coverUrl: homepage.coverUrl,
    ),
  ];
}

List<HomepageQuestionPreview> _mockDefaultQuestionPreview(
  HomepageDetail homepage,
) {
  final title = homepage.title;
  return <HomepageQuestionPreview>[
    HomepageQuestionPreview(
      postId: '${homepage.id}_question_1',
      title: '$title 值得什么时候去？',
      summary: '候选主页发布后也会得到基础问答壳层。',
    ),
  ];
}

List<HomepageRelatedGroupSummary> _mockDefaultRelatedGroups(
  HomepageDetail homepage,
) {
  final title = homepage.title;
  final id = homepage.id;
  return <HomepageRelatedGroupSummary>[
    HomepageRelatedGroupSummary(
      circleId: '${id}_group_1',
      name: '$title 讨论',
      memberCount: 12,
      linkedHomepageId: id,
      linkedHomepageTitle: title,
    ),
  ];
}

HomepageDetail _mergeBasicDraft(HomepageDetail h, HomepageBasicDraft d) {
  final now = DateTime.now().toUtc();
  return HomepageDetail(
    id: h.id,
    homepageType: h.homepageType,
    title: d.title != null && d.title!.trim().isNotEmpty
        ? d.title!.trim()
        : h.title,
    subtitle: d.subtitle != null
        ? (d.subtitle!.trim().isEmpty ? null : d.subtitle!.trim())
        : h.subtitle,
    coverUrl: d.coverUrl != null && d.coverUrl!.trim().isNotEmpty
        ? d.coverUrl!.trim()
        : h.coverUrl,
    status: h.status,
    sourceType: h.sourceType,
    claimStatus: h.claimStatus,
    canonicalEntityId: h.canonicalEntityId,
    categoryTags: d.categoryTags ?? h.categoryTags,
    address: d.address != null && d.address!.trim().isNotEmpty
        ? d.address!.trim()
        : h.address,
    city: d.city != null && d.city!.trim().isNotEmpty ? d.city!.trim() : h.city,
    location: d.location ?? h.location,
    ownerUserId: h.ownerUserId,
    averageRating: h.averageRating,
    ratingCount: h.ratingCount,
    reviewSummary: h.reviewSummary,
    contentPreview: h.contentPreview,
    questionPreview: h.questionPreview,
    relatedGroups: h.relatedGroups,
    createdAt: h.createdAt,
    updatedAt: now,
    publishedAt: h.publishedAt,
    offlineAt: h.offlineAt,
  );
}

String _normalize(String? value) => (value ?? '').trim().toLowerCase();

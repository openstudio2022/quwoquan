import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Constructs a complete server-authored impact fact for UI tests.
///
/// Empty visuals and action hints mean this anonymous aggregate has no safe
/// preview or direct action; its count remains the drill-down entry point.
AuthorImpactItem authorImpactItemFixture({
  String impactId = 'impact-circle-join-001',
  String helpType = 'community',
  String action = 'join',
  String intersectionDimension = 'interest',
  String tagRef = 'interest/photography',
  String source = 'source:circle_join',
  int count = 1,
  String primaryText = '1位读者加入了摄影爱好者圈',
  String subtitleText = '来自摄影爱好者圈',
  List<IntersectionTextSpan>? primarySpans,
  List<IntersectionVisual> sampleVisuals = const <IntersectionVisual>[],
  IntersectionRepresentativeActor? representativeActor,
  List<IntersectionActionHint> actionHints = const <IntersectionActionHint>[],
  IntersectionTarget? countTarget,
  String evidenceSnapshotId = 'impact-snapshot-circle-join-001',
  String countObjectKind = 'user',
  String iconKey = 'impact-community',
  String freshAt = '2026-06-19T08:00:00Z',
  String timeBucket = 'last_30_days',
  String lifecycleState = 'active',
  double previousStrength = 0.35,
  double strengthDelta = 0.10,
}) {
  return AuthorImpactItem(
    helpType: helpType,
    action: action,
    intersectionDimension: intersectionDimension,
    tagRef: tagRef,
    source: source,
    count: count,
    primaryText: primaryText,
    subtitleText: subtitleText,
    impactId: impactId,
    primarySpans:
        primarySpans ??
        <IntersectionTextSpan>[
          IntersectionTextSpan(text: primaryText, role: 'plain'),
        ],
    sampleVisuals: sampleVisuals,
    representativeActor: representativeActor,
    actionHints: actionHints,
    countTarget: countTarget,
    evidenceSnapshotId: evidenceSnapshotId,
    countObjectKind: countObjectKind,
    iconKey: iconKey,
    freshAt: DateTime.parse(freshAt),
    timeBucket: timeBucket,
    lifecycleState: lifecycleState,
    previousStrength: previousStrength,
    strengthDelta: strengthDelta,
  );
}

AuthorImpactEvidenceItem authorImpactEvidenceItemFixture({
  required String evidenceId,
  required String summaryText,
  String impactId = 'impact-circle-join-001',
  String helpType = 'community',
  String action = 'join',
  String intersectionDimension = 'interest',
  String occurredAt = '2026-06-19T08:00:00Z',
  IntersectionVisual? sampleVisual,
  IntersectionRepresentativeActor? representativeActor,
  List<IntersectionActionHint> actionHints = const <IntersectionActionHint>[],
  IntersectionTarget? contentTarget,
}) {
  return AuthorImpactEvidenceItem(
    evidenceId: evidenceId,
    impactId: impactId,
    helpType: helpType,
    action: action,
    intersectionDimension: intersectionDimension,
    occurredAt: DateTime.parse(occurredAt),
    summaryText: summaryText,
    sampleVisual: sampleVisual,
    representativeActor: representativeActor,
    actionHints: actionHints,
    contentTarget: contentTarget,
  );
}

AuthorImpactEvidencePage authorImpactEvidencePageFixture({
  String impactId = 'impact-circle-join-001',
  String evidenceSnapshotId = 'impact-snapshot-circle-join-001',
  List<AuthorImpactEvidenceItem> items = const <AuthorImpactEvidenceItem>[],
  int? totalCount,
  // A blank cursor is the canonical terminal-page value when hasMore is false.
  String nextCursor = '',
  bool hasMore = false,
}) {
  return AuthorImpactEvidencePage(
    impactId: impactId,
    evidenceSnapshotId: evidenceSnapshotId,
    totalCount: totalCount ?? items.length,
    items: items,
    nextCursor: nextCursor,
    hasMore: hasMore,
  );
}

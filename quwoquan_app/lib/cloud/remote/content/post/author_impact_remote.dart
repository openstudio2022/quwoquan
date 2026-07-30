import 'package:quwoquan_app/application/content/post/author_impact_query.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_evidence_page.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_evidence_item.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_item.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_summary.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_action_hint.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_propagation_path.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_representative_actor.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_visual.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Content/Post 作者影响力的 production Remote adapter。
///
/// 传输、路径、鉴权、重试和 decoder 由 generated operation client 处理；本适配器
/// 只在 pure-Dart projection 与 App runtime DTO 之间做强类型映射。
typedef AuthorImpactInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

final class RemoteAuthorImpactQuery implements AuthorImpactQuery {
  const RemoteAuthorImpactQuery({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final AuthorImpactInvocationContextFactory invocationContext;

  @override
  Future<AuthorImpactSummary> getAuthorImpact(String personaId) async {
    final projection = await client.contentPostGetAuthorImpact(
      GetAuthorImpactQuery(personaId: personaId),
      context: invocationContext(ContentRequestPageIds.getAuthorImpact),
    );
    return _toSummary(projection);
  }

  @override
  Future<AuthorImpactEvidencePage> listAuthorImpactEvidence({
    required String personaId,
    required String impactId,
    String evidenceSnapshotId = '',
    String cursor = '',
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final projection = await client.contentPostListAuthorImpactEvidence(
      ListAuthorImpactEvidenceQuery(
        personaId: personaId,
        impactId: impactId,
        evidenceSnapshotId: evidenceSnapshotId,
        cursor: cursor,
        limit: limit,
      ),
      context: invocationContext(
        ContentRequestPageIds.listAuthorImpactEvidence,
      ),
    );
    return _toEvidencePage(projection);
  }
}

AuthorImpactSummary _toSummary(AuthorImpactSummaryProjection projection) {
  return AuthorImpactSummary(
    authorId: projection.authorId,
    total: projection.total,
    items: projection.items.map(_toItem).toList(growable: false),
  );
}

AuthorImpactItem _toItem(AuthorImpactItemProjection projection) {
  return AuthorImpactItem(
    helpType: projection.helpType,
    action: projection.action,
    intersectionDimension: projection.intersectionDimension,
    tagRef: projection.tagRef,
    source: projection.source,
    count: projection.count,
    primaryText: projection.primaryText,
    subtitleText: projection.subtitleText,
    impactId: projection.impactId,
    primarySpans: projection.primarySpans
        .map(_toTextSpan)
        .toList(growable: false),
    sampleVisuals: projection.sampleVisuals
        .map(_toVisual)
        .toList(growable: false),
    representativeActor: projection.representativeActor == null
        ? null
        : _toRepresentativeActor(projection.representativeActor!),
    actionHints: projection.actionHints
        .map(_toActionHint)
        .toList(growable: false),
    countTarget: projection.countTarget == null
        ? null
        : _toTarget(projection.countTarget!),
    evidenceSnapshotId: projection.evidenceSnapshotId,
    countObjectKind: projection.countObjectKind,
    propagationPath: projection.propagationPath == null
        ? null
        : _toPropagationPath(projection.propagationPath!),
    iconKey: projection.iconKey,
    freshAt: projection.freshAt,
    timeBucket: projection.timeBucket,
    lifecycleState: projection.lifecycleState,
    previousStrength: projection.previousStrength,
    strengthDelta: projection.strengthDelta,
  );
}

AuthorImpactEvidencePage _toEvidencePage(
  AuthorImpactEvidencePageProjection projection,
) {
  return AuthorImpactEvidencePage(
    impactId: projection.impactId,
    evidenceSnapshotId: projection.evidenceSnapshotId,
    totalCount: projection.totalCount,
    items: projection.items.map(_toEvidenceItem).toList(growable: false),
    nextCursor: projection.nextCursor,
    hasMore: projection.hasMore,
  );
}

AuthorImpactEvidenceItem _toEvidenceItem(
  AuthorImpactEvidenceItemProjection projection,
) {
  return AuthorImpactEvidenceItem(
    evidenceId: projection.evidenceId,
    impactId: projection.impactId,
    helpType: projection.helpType,
    action: projection.action,
    intersectionDimension: projection.intersectionDimension,
    occurredAt: projection.occurredAt,
    summaryText: projection.summaryText,
    sampleVisual: projection.sampleVisual == null
        ? null
        : _toVisual(projection.sampleVisual!),
    representativeActor: projection.representativeActor == null
        ? null
        : _toRepresentativeActor(projection.representativeActor!),
    actionHints: projection.actionHints
        .map(_toActionHint)
        .toList(growable: false),
    contentTarget: projection.contentTarget == null
        ? null
        : _toTarget(projection.contentTarget!),
  );
}

IntersectionTarget _toTarget(AuthorImpactTargetProjection projection) {
  return IntersectionTarget(
    objectType: projection.objectType,
    objectId: projection.objectId,
    objectKind: projection.objectKind,
    routeId: projection.routeId,
  );
}

IntersectionVisual _toVisual(AuthorImpactVisualProjection projection) {
  return IntersectionVisual(
    assetKind: projection.assetKind,
    imageUrl: projection.imageUrl,
    displayName: projection.displayName,
    target: projection.target == null ? null : _toTarget(projection.target!),
  );
}

IntersectionTextSpan _toTextSpan(AuthorImpactTextSpanProjection projection) {
  return IntersectionTextSpan(
    text: projection.text,
    role: projection.role,
    target: projection.target == null ? null : _toTarget(projection.target!),
    visual: projection.visual == null ? null : _toVisual(projection.visual!),
  );
}

IntersectionRepresentativeActor _toRepresentativeActor(
  AuthorImpactRepresentativeActorProjection projection,
) {
  return IntersectionRepresentativeActor(
    actorId: projection.actorId,
    displayName: projection.displayName,
    avatarUrl: projection.avatarUrl,
    relationLabel: projection.relationLabel,
    privacyState: projection.privacyState,
    target: projection.target == null ? null : _toTarget(projection.target!),
    evidenceRank: projection.evidenceRank,
    snapshotVersion: projection.snapshotVersion,
  );
}

IntersectionActionHint _toActionHint(
  AuthorImpactActionHintProjection projection,
) {
  return IntersectionActionHint(
    actionKey: projection.actionKey,
    label: projection.label,
    target: projection.target == null ? null : _toTarget(projection.target!),
    isPrimary: projection.isPrimary,
    priority: projection.priority,
    actionTier: projection.actionTier,
    requiredGates: projection.requiredGates,
    targetAvailability: projection.targetAvailability,
    dispatch: projection.dispatch,
  );
}

IntersectionPropagationPath _toPropagationPath(
  AuthorImpactPropagationPathProjection projection,
) {
  return IntersectionPropagationPath(
    pathKind: projection.pathKind,
    hopCount: projection.hopCount,
    secondarySpreadCount: projection.secondarySpreadCount,
    summaryText: projection.summaryText,
    summaryTarget: projection.summaryTarget == null
        ? null
        : _toTarget(projection.summaryTarget!),
    nodes: projection.nodes.map(_toVisual).toList(growable: false),
  );
}

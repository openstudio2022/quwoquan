part of 'works_immersive_viewer.dart';

extension _WorksImmersiveViewerIntersectionActions
    on _WorksImmersiveViewerState {
  IntersectionTarget _postIntersectionContextTarget(PostBaseDto post) {
    return IntersectionTarget(
      objectType: 'post',
      objectId: post.id,
      objectKind: 'content',
      routeId: AppUiSurfaces.workBrowser.routeId,
    );
  }

  bool _sameIntersectionTarget(
    IntersectionTarget? left,
    IntersectionTarget? right,
  ) {
    if (left == null || right == null) {
      return false;
    }
    final leftId = left.objectId.trim();
    final rightId = right.objectId.trim();
    if (leftId.isEmpty || rightId.isEmpty || leftId != rightId) {
      return false;
    }
    final leftType = left.objectType.trim();
    final rightType = right.objectType.trim();
    if (leftType.isNotEmpty && rightType.isNotEmpty && leftType != rightType) {
      return false;
    }
    return true;
  }

  IntersectionReason? _primaryIntersectionReasonFor(PostBaseDto post) {
    final reasons = post.intersectionReasons ?? const <IntersectionReason>[];
    final contextTarget = _postIntersectionContextTarget(post);
    for (final reason in reasons) {
      final displayReason = displayReadyIntersectionReason(
        reason,
        contextObjectTarget: contextTarget,
      );
      if (displayReason != null) {
        return displayReason;
      }
    }
    return null;
  }

  void _showIntersectionDetail(BuildContext context, PostBaseDto post) {
    final reasons = post.intersectionReasons ?? const <IntersectionReason>[];
    if (reasons.isEmpty) return;
    showAppBottomModal<void>(
      context: context,
      builder: (sheetContext) => _WorksIntersectionDetailSheet(
        reasons: reasons,
        contextObjectTarget: _postIntersectionContextTarget(post),
        onAskAssistant: () {
          unawaited(
            dismissAppModalAndRun(
              sheetContext,
              action: () {
                if (!context.mounted) {
                  return;
                }
                _openAssistantForIntersectionReason(context, post, reasons);
              },
            ),
          );
        },
      ),
    );
  }

  void _openAssistantForIntersectionReason(
    BuildContext context,
    PostBaseDto post,
    List<IntersectionReason> reasons,
  ) {
    if (reasons.isEmpty) return;
    final primary = reasons.first;
    final target = VisitTarget.page('work_intersection_${post.id}');
    final openContext = AssistantOpenContext(
      source: AssistantSource.article,
      tab: 'work_intersection',
      dimension: primary.dimension,
      entityId: post.id,
      objectType: 'post',
      intersectionEvidenceRefs: _intersectionEvidenceRefsForReasons(
        post,
        reasons,
      ),
      visitTarget: target,
      experienceLevel: ref
          .read(visitRecorderServiceProvider)
          .getExperience(target),
      hints: <String, dynamic>{
        'postId': post.id,
        'contentType': post.type,
        'primaryText': primary.primaryText,
        'reasonCount': reasons.length,
      },
    );
    context.push(AppRoutePaths.assistantPersonal, extra: openContext);
  }

  List<AssistantIntersectionEvidenceRef> _intersectionEvidenceRefsForReasons(
    PostBaseDto post,
    List<IntersectionReason> reasons,
  ) {
    final refs = <String, AssistantIntersectionEvidenceRef>{};
    for (final reason in reasons) {
      final intersectionId = reason.intersectionId.trim();
      final evidenceId = reason.pointSummarySnapshotId.trim();
      final sourceRef = reason.kind.trim();
      if (intersectionId.isEmpty || evidenceId.isEmpty || sourceRef.isEmpty) {
        continue;
      }
      final ref = AssistantIntersectionEvidenceRef(
        intersectionId: intersectionId,
        evidenceId: evidenceId,
        sourceRef: sourceRef,
        objectTypeRef: 'post',
        objectId: post.id,
      );
      refs.putIfAbsent(
        '$intersectionId:$evidenceId:$sourceRef:${post.id}',
        () => ref,
      );
    }
    return refs.values.toList(growable: false);
  }

  void _openIntersectionSpan(
    BuildContext context,
    PostBaseDto post,
    IntersectionReason reason,
    IntersectionTextSpan span,
  ) {
    final navigator = IntersectionTargetNavigator(
      onTrack: (target, attribution) {
        _trackIntersectionTargetClick(
          post: post,
          target: target,
          attribution: attribution,
        );
      },
    );
    navigator.open(
      context,
      span.target,
      sourceRef: reason.source,
      attribution: _intersectionNavAttribution(reason),
    );
  }

  void _openIntersectionFallback(
    BuildContext context,
    PostBaseDto post,
    IntersectionReason reason,
  ) {
    final navigator = IntersectionTargetNavigator(
      onTrack: (target, attribution) {
        _trackIntersectionTargetClick(
          post: post,
          target: target,
          attribution: attribution,
        );
      },
    );
    final reasonTarget = IntersectionTargetNavigator.targetForReason(reason);
    if (!_sameIntersectionTarget(
          reasonTarget,
          _postIntersectionContextTarget(post),
        ) &&
        navigator.open(
          context,
          reasonTarget,
          sourceRef: reason.source,
          attribution: _intersectionNavAttribution(reason),
        )) {
      return;
    }
    for (final visual in reason.sampleVisuals) {
      if (navigator.open(
        context,
        visual.target,
        sourceRef: reason.source,
        attribution: _intersectionNavAttribution(reason),
      )) {
        return;
      }
    }
    final dimension = reason.dimension.trim();
    if (dimension.isNotEmpty &&
        navigator.open(
          context,
          IntersectionTarget(
            objectType: 'dimension',
            objectId: dimension,
            objectKind: 'tag',
            routeId: AppUiSurfaces.myIntersections.routeId,
          ),
          sourceRef: reason.source,
          attribution: _intersectionNavAttribution(reason),
        )) {
      return;
    }
    _showIntersectionDetail(context, post);
  }

  void _trackIntersectionTargetClick({
    required PostBaseDto post,
    required IntersectionTarget target,
    required IntersectionNavAttribution attribution,
  }) {
    final feedSession = ref.read(feedSessionProvider.notifier);
    ref
        .read(contentBehaviorTrackerProvider)
        .trackTagClick(
          target.objectId,
          contentType: target.objectKind.trim().isNotEmpty
              ? target.objectKind
              : post.type,
          authorId: target.objectKind == 'user' ? target.objectId : null,
          referralSource: widget.referralSource,
          tags: attribution.tagRefs,
          feedRequestId: _effectiveFeedRequestId(),
          channelId: _immersiveChannelId(),
          rankingVersion: feedSession.currentRankingVersion,
          reasonVersion: feedSession.currentReasonVersion,
          recallPath: post.recallPath,
          contentVertical: post.contentVertical,
          supplySource: post.supplySource,
          intersectionId: attribution.intersectionId,
          intersectionDimension: attribution.dimension,
          intersectionSourceRef: attribution.sourceRef,
          intersectionTagRefs: attribution.tagRefs,
          intersectionClass: attribution.intersectionClass,
          intersectionEvidenceId: attribution.evidenceId,
        );
  }

  IntersectionNavAttribution _intersectionNavAttribution(
    IntersectionReason reason,
  ) {
    return IntersectionNavAttribution(
      intersectionId: reason.intersectionId,
      dimension: reason.dimension,
      intersectionClass: reason.intersectionClass,
      sourceRef: reason.source,
      tagRefs: reason.tagRefs,
      evidenceId: reason.pointSummarySnapshotId,
    );
  }
}

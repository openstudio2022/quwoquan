part of 'works_immersive_viewer.dart';

extension _WorksImmersiveViewerIntersectionActions
    on _WorksImmersiveViewerState {
  IntersectionTarget _postIntersectionContextTarget(ContentPostViewData post) {
    return IntersectionTarget(
      objectType: 'post',
      objectId: post.id,
      objectKind: 'content',
      routeId: AppUiSurfaces.workBrowser.routeId,
    );
  }

  IntersectionReason? _primaryIntersectionReasonFor(ContentPostViewData post) {
    return resolveIntersectionDisplay(
      post.intersectionReasons,
      contextObjectTarget: _postIntersectionContextTarget(post),
    )?.reason;
  }

  void _showIntersectionDetail(BuildContext context, ContentPostViewData post) {
    final resolution = resolveIntersectionDisplay(
      post.intersectionReasons,
      contextObjectTarget: _postIntersectionContextTarget(post),
    );
    if (resolution == null) return;
    // 漏斗「证据展开」步：与首页卡同一事件类型，携带同一 intersectionId。
    final reason = resolution.reason;
    ref
        .read(contentBehaviorTrackerProvider)
        .trackIntersectionExpand(
          contentId: post.id,
          intersectionId: reason.intersectionId,
          intersectionDimension: reason.dimension,
          intersectionClass: reason.intersectionClass,
          intersectionSourceRef: sourceRefForReason(reason),
          intersectionCohort: reason.cohort,
          referralSource: widget.referralSource,
        );
    showAppBottomModal<void>(
      context: context,
      builder: (sheetContext) {
        return HomeFeedCrossObjectComposition.intersectionEvidenceSheet(
          panelKey: const ValueKey<String>('works-intersection-detail-sheet'),
          primaryActionKey: const ValueKey<String>(
            'works-intersection-primary-action',
          ),
          resolution: resolution,
          onDismiss: () => Navigator.of(sheetContext).pop(),
          onPrimaryAction: resolution.primaryHint == null
              ? null
              : () {
                  unawaited(
                    dismissAppModalAndRun(
                      sheetContext,
                      action: () {
                        if (!context.mounted) return;
                        _openIntersectionActionHint(
                          context,
                          post,
                          resolution.reason,
                          resolution.primaryHint!,
                        );
                      },
                    ),
                  );
                },
        );
      },
    );
  }

  /// 交集 CTA 一级化：把云侧主行动（如「发起聚集」）按 actionKeyMeta.dispatch
  /// 分发到真实承接页；分发失败时回落到证据详情，不做静默失败。
  void _openIntersectionActionHint(
    BuildContext context,
    ContentPostViewData post,
    IntersectionReason reason,
    IntersectionActionHint hint,
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
    final result = navigator.openActionHint(
      context,
      hint,
      sourceRef: sourceRefForReason(reason),
      attribution: _intersectionNavAttribution(reason),
      evidenceReason: reason,
      contextObjectTarget: _postIntersectionContextTarget(post),
      referralSource: widget.referralSource,
    );
    assert(
      !result.isConfigurationFailure,
      'startGatheringNavigationBinding 未注入：约伴行动被静默降级',
    );
    if (!result.didOpen) {
      _showIntersectionDetail(context, post);
    }
  }

  void _trackIntersectionTargetClick({
    required ContentPostViewData post,
    required IntersectionTarget target,
    required IntersectionNavAttribution attribution,
  }) {
    final feedAttribution = _feedAttributionForPost(post);
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
          feedRequestId: feedAttribution.feedRequestId,
          channelId: _immersiveChannelId(),
          policyDigest: feedAttribution.policyDigest,
          recallPath: post.recallPath,
          supplySource: post.supplySource,
          intersectionId: attribution.intersectionId,
          intersectionDimension: attribution.dimension,
          intersectionSourceRef: attribution.sourceRef,
          intersectionTagRefs: attribution.tagRefs,
          intersectionClass: attribution.intersectionClass,
          intersectionEvidenceId: attribution.evidenceId,
          intersectionCohort: attribution.cohort,
        );
  }

  IntersectionNavAttribution _intersectionNavAttribution(
    IntersectionReason reason,
  ) {
    return IntersectionNavAttribution(
      intersectionId: reason.intersectionId,
      dimension: reason.dimension,
      intersectionClass: reason.intersectionClass,
      sourceRef: sourceRefForReason(reason),
      tagRefs: reason.tagRefs,
      evidenceId: reason.pointSummarySnapshotId,
      cohort: reason.cohort,
    );
  }
}

part of 'works_immersive_viewer.dart';

extension _WorksImmersiveViewerSocialActions on _WorksImmersiveViewerState {
  void _onLike(ContentPostViewData post) {
    runWhenLoggedIn(ref, context, AuthGateReason.like, () {
      final isLiked = effectivePostLiked(ref, post.id);
      final currentCount = effectivePostLikeCount(
        ref,
        post.id,
        fallback: post.likeCount,
      );
      final nextLiked = !isLiked;
      final nextLikeCount = nextLiked
          ? currentCount + 1
          : (currentCount - 1).clamp(0, 1 << 31).toInt();
      syncPostLikeIntent(
        ref,
        postId: post.id,
        previousLiked: isLiked,
        isLiked: nextLiked,
        likeCount: nextLikeCount,
      );
    });
  }

  void _onFollow(ContentPostViewData post) {
    runWhenLoggedIn(ref, context, AuthGateReason.follow, () {
      final subjectId = post.personaId;
      final wasFollowing = effectiveProfileFollowing(ref, subjectId);
      final nextFollowing = !wasFollowing;
      syncProfileFollowIntent(
        ref,
        personaId: subjectId,
        previousFollowing: wasFollowing,
        isFollowing: nextFollowing,
        sourceSurfaceId: AppUiSurfaces.workBrowser.id,
      );
    });
  }

  /// 回顾内容的溯源锚点：作者主动写入的 gatheringRef（wire 直接可得）。
  String _recapGatheringRefFor(ContentPostViewData post) {
    final raw = _effectiveRawPostById(post.id);
    return raw?['gatheringRef']?.toString().trim() ?? '';
  }

  /// 种草内容溯源判定：content 锚点社会证明成形级 > 0 才显示
  /// 「他们从这条内容出发一起去了」；读取失败诚实缺席。
  void _ensureSeedProvenanceLoaded(ContentPostViewData post) {
    final postId = post.id.trim();
    if (postId.isEmpty ||
        _seedProvenanceByPostId.containsKey(postId) ||
        !_loadingSeedProvenancePostIds.add(postId)) {
      return;
    }
    unawaited(() async {
      var formed = false;
      try {
        final proof = await ref
            .read(workBrowserSocialProofReaderProvider)
            .getGatheringSocialProof(anchorKind: 'content', objectId: postId);
        formed = proof.formedCount > 0;
      } catch (error, stackTrace) {
        unawaited(
          ref
              .read(exceptionTelemetryPortProvider)
              .recordHandledException(
                source: 'content.works_viewer.load_seed_provenance',
                error: error,
                stackTrace: stackTrace,
              ),
        );
      } finally {
        _loadingSeedProvenancePostIds.remove(postId);
      }
      if (!mounted) return;
      _setMountedState(() => _seedProvenanceByPostId[postId] = formed);
    }());
  }

  void _openRecapProvenance(String gatheringRef) {
    context.push(AppRoutePaths.gatheringDetail(id: gatheringRef));
  }

  /// 种草溯源点击：经既有按源公开行动读面取第一条成形行动进详情。
  void _openSeedProvenance(ContentPostViewData post) {
    unawaited(() async {
      try {
        final cards = await ref
            .read(gatheringQueryReaderProvider)
            .listBySource(
              GatheringBySourceListQuery(
                sourceObjectTypeRef: 'content',
                sourceObjectId: post.id,
                limit: 1,
              ),
            );
        if (!mounted || cards.isEmpty) return;
        _openRecapProvenance(cards.first.gatheringId);
      } catch (error, stackTrace) {
        unawaited(
          ref
              .read(exceptionTelemetryPortProvider)
              .recordHandledException(
                source: 'content.works_viewer.open_seed_provenance',
                error: error,
                stackTrace: stackTrace,
              ),
        );
      }
    }());
  }
}

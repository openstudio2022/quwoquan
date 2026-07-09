part of 'works_immersive_viewer.dart';

extension _WorksImmersiveViewerEngagementActions on _WorksImmersiveViewerState {
  void _openCommentFor(String postId) {
    _setMountedState(() => _commentSplitPostId = postId);
  }

  Widget _buildCommentSplitContent(PostBaseDto post) {
    return ColoredBox(
      color: AppColors.worksBackground,
      child: _buildPostCanvas(
        post,
        enableArticlePageCurl: _enableArticlePageCurl,
      ),
    );
  }

  PostBaseDto? _postById(List<PostBaseDto> posts, String postId) {
    for (final post in posts) {
      if (post.id == postId) {
        return post;
      }
    }
    return null;
  }

  void _sharePost(
    BuildContext ctx,
    PostBaseDto post, {
    required bool enableIdentityTemplate,
  }) {
    runWhenLoggedIn(ref, context, AuthGateReason.shareRecord, () {
      final template = _buildShareTemplate(
        post: post,
        enableIdentityTemplate: enableIdentityTemplate,
      );
      ContentShareSheet.show(
        ctx,
        template: template,
        onActionCompleted: (result) async {
          await _recordShare(post.id, result.actionId);
        },
      );
    });
  }

  Future<void> _copyLink(
    BuildContext context,
    PostBaseDto post, {
    required bool enableIdentityTemplate,
  }) async {
    final result = await const DefaultContentShareActionHandler().execute(
      context,
      _buildShareTemplate(
        post: post,
        enableIdentityTemplate: enableIdentityTemplate,
      ),
      ContentShareAction(id: 'copy_link', label: UITextConstants.copyLink),
    );
    if (result.success) {
      await _recordShare(post.id, result.actionId);
    }
  }

  ContentShareTemplate _buildShareTemplate({
    required PostBaseDto post,
    required bool enableIdentityTemplate,
  }) {
    final raw = _rawPostById(post.id);
    final visibility =
        raw?[ContentPostImmersiveWireKeys.visibility]?.toString() ?? 'public';
    final surfaceView = ContentSurfaceViewMapper.fromDto(post, wire: raw);
    return ContentShareTemplateBuilder.build(
      surfaceView: surfaceView,
      enableIdentityTemplate: enableIdentityTemplate,
      visibility: visibility,
      circleNames: _circlesForPost(
        post,
      ).map((circle) => circle.name).toList(growable: false),
    );
  }

  Future<void> _recordShare(String postId, String actionId) async {
    final rawShareCount =
        (_rawPostById(postId)?[ContentPostImmersiveWireKeys.shareCount] as num?)
            ?.toInt() ??
        0;
    final baselineShareCount = effectivePostShareCount(
      ref,
      postId,
      fallback: rawShareCount,
    );
    await syncPostShareIntent(
      ref,
      postId: postId,
      baselineShareCount: baselineShareCount,
    );
    ref
        .read(contentBehaviorTrackerProvider)
        .trackShare(postId, tags: <String>[actionId]);
  }
}

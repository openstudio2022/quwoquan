part of 'home_multi_form_feed.dart';

/// Local share telemetry and reversible feed-card dismissal actions.
extension _HomeMultiFormFeedLocalActions on HomeMultiFormFeed {
  Future<void> _copyLink(
    BuildContext context,
    WidgetRef ref,
    ContentPostViewData post, {
    required bool enableIdentityTemplate,
  }) async {
    final result = await const DefaultContentShareActionHandler().execute(
      context,
      buildDiscoveryShareTemplate(
        post: post,
        enableIdentityTemplate: enableIdentityTemplate,
      ),
      ContentShareAction(id: 'copy_link', label: FoundationText.copyLink),
    );
    if (result.success) {
      await _recordShare(ref, post.id, result.actionId);
    }
  }

  Future<void> _recordShare(
    WidgetRef ref,
    String postId,
    String actionId,
  ) async {
    ref
        .read(contentBehaviorTrackerProvider)
        .trackShare(postId, tags: <String>[actionId]);
  }

  /// 任务 A · 负反馈即时反馈统一收口：本地移除卡片 + 降级提示 toast。
  ///
  /// 仅做本地乐观移除（`removePostLocally`），不改 discovery_feed_provider 的
  /// 实时补丁逻辑；负反馈行为事件已在调用点单独上报。
  void _dismissFeedPost(
    BuildContext context,
    WidgetRef ref,
    String postId, {
    required String toast,
    VoidCallback? onUndo,
  }) {
    final notifier = ref.read(discoveryFeedMapProvider.notifier);
    final removed = notifier.removePostLocally(postId);
    if (context.mounted) {
      AppToast.show(
        context,
        toast,
        actionLabel: onUndo == null ? null : ContentText.undo,
        onAction: onUndo == null
            ? null
            : () {
                notifier.restorePostsLocally(removed);
                onUndo();
              },
      );
    }
  }
}

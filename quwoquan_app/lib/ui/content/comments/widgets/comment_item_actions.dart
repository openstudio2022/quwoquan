part of 'comment_thread_view.dart';

// 评论长按操作面（复制 / 举报 / 删除）：贴底 action sheet，按服务端权限投影渲染。
// 举报复用 Report(target=comment) 既有对象通路与 content_report journey 埋点语义。

enum _CommentItemAction { copy, report, delete }

Future<void> showCommentItemActionsSheet(
  BuildContext context,
  WidgetRef ref, {
  required String postId,
  required ContentCommentListItem comment,
}) async {
  final action = await showAppActionSheet<_CommentItemAction>(
    context,
    sections: <AppActionSheetSection<_CommentItemAction>>[
      AppActionSheetSection(
        items: [
          AppActionSheetItem(
            value: _CommentItemAction.copy,
            label: UITextConstants.commentCopyAction,
            icon: CupertinoIcons.doc_on_doc,
          ),
          if (comment.canReport)
            AppActionSheetItem(
              value: _CommentItemAction.report,
              label: UITextConstants.commentReportAction,
              icon: CupertinoIcons.flag,
            ),
          if (comment.canDelete)
            AppActionSheetItem(
              value: _CommentItemAction.delete,
              label: UITextConstants.commentDeleteAction,
              icon: CupertinoIcons.trash,
              isDestructive: true,
            ),
        ],
      ),
    ],
  );
  if (action == null || !context.mounted) return;
  switch (action) {
    case _CommentItemAction.copy:
      await Clipboard.setData(ClipboardData(text: comment.content));
      if (!context.mounted) return;
      AppToast.show(context, UITextConstants.commentCopiedToast);
    case _CommentItemAction.report:
      await _reportComment(context, ref, comment);
    case _CommentItemAction.delete:
      final confirmed = await _confirmCommentDelete(context);
      if (!confirmed || !context.mounted) return;
      await ref
          .read(commentProviderFamily(postId).notifier)
          .deleteComment(comment.id);
  }
}

Future<void> _reportComment(
  BuildContext context,
  WidgetRef ref,
  ContentCommentListItem comment,
) async {
  final reason = await showContentReportReasonSheet(context);
  if (reason == null || !context.mounted) return;
  if (!ref.read(authSessionControllerProvider).isAuthenticated) {
    final accepted = ref
        .read(authContinuationProvider.notifier)
        .set(
          SubmitCommentReportContinuation(
            postId: comment.postId,
            commentId: comment.id,
            reason: reason,
          ),
          ownerToken: 'comment-report:${comment.postId}:${comment.id}',
        );
    if (!accepted) return;
    unawaited(
      requireLogin(
        ref,
        context,
        AuthGateReason.report,
        dismissFallback: AppRoutePaths.home,
        dismissPolicy: LoginDismissPolicy.safeFallback,
      ),
    );
    return;
  }
  await _submitCommentReport(
    context,
    ref,
    commentId: comment.id,
    reason: reason,
  );
}

Future<void> _submitCommentReport(
  BuildContext context,
  WidgetRef ref, {
  required String commentId,
  required ContentReportReason reason,
}) async {
  final journeyTracker = ref.read(journeyEventTrackerProvider);
  final startedAt = DateTime.now();
  try {
    await ref
        .read(workBrowserContentReportCommandWriterProvider)
        .createReport(
          CreateContentReportCommand(
            targetId: commentId,
            targetType: ContentReportTargetType.comment,
            reason: reason,
          ),
        );
    await journeyTracker.trackAction(
      journey: 'content_report',
      action: 'submit_report',
      pageName: 'comment_thread',
      payload: <String, Object?>{
        'result': 'success',
        'targetType': 'comment',
        'durationMs': DateTime.now().difference(startedAt).inMilliseconds,
      },
    );
    if (!context.mounted) return;
    AppToast.show(context, UITextConstants.reportSubmittedViewProgress);
  } catch (error) {
    await journeyTracker.trackAction(
      journey: 'content_report',
      action: 'submit_report',
      pageName: 'comment_thread',
      payload: <String, Object?>{
        'result': 'failure',
        'targetType': 'comment',
        'failReasonCode': error is CloudException
            ? (error.code ?? error.type.name)
            : error.runtimeType.toString(),
        'durationMs': DateTime.now().difference(startedAt).inMilliseconds,
      },
    );
    if (!context.mounted) return;
    await AppActionErrorFeedback.show(
      context,
      semantic: runtimeErrorSemantic(
        context,
        error: error,
        category: UiErrorCategory.submit,
        scope: UiErrorScope.global,
      ),
      onAction: (action) async {
        if (action.type == UiErrorActionType.retry ||
            action.type == UiErrorActionType.resubmit) {
          await _submitCommentReport(
            context,
            ref,
            commentId: commentId,
            reason: reason,
          );
        }
      },
    );
  }
}

Future<bool> _confirmCommentDelete(BuildContext context) async {
  final confirmed = await showAppCupertinoDialog<bool>(
    context: context,
    builder: (dialogContext) => CupertinoAlertDialog(
      title: const Text(UITextConstants.commentDeleteConfirmTitle),
      content: const Text(UITextConstants.commentDeleteConfirmMessage),
      actions: [
        CupertinoDialogAction(
          onPressed: () => Navigator.of(dialogContext).pop(false),
          child: const Text(UITextConstants.cancel),
        ),
        CupertinoDialogAction(
          isDestructiveAction: true,
          onPressed: () => Navigator.of(dialogContext).pop(true),
          child: const Text(UITextConstants.commentDeleteAction),
        ),
      ],
    ),
  );
  return confirmed ?? false;
}

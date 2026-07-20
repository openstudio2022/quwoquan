import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';

enum CreatePublishResultState { published, pendingReview, queued }

enum CreatePublishResultAction { viewWork, viewPublicationTasks, done }

Future<CreatePublishResultAction?> showCreatePublishResultSheet(
  BuildContext context, {
  required CreatePublishResultState state,
  String? postId,
}) {
  final canViewWork =
      state == CreatePublishResultState.published &&
      (postId?.trim().isNotEmpty ?? false);
  final canViewTasks = state != CreatePublishResultState.published;
  final title = switch (state) {
    CreatePublishResultState.published =>
      UITextConstants.publishResultSuccessTitle,
    CreatePublishResultState.pendingReview =>
      UITextConstants.publishResultPendingReviewTitle,
    CreatePublishResultState.queued => UITextConstants.publishResultQueuedTitle,
  };
  final description = switch (state) {
    CreatePublishResultState.published =>
      UITextConstants.publishResultSuccessDescription,
    CreatePublishResultState.pendingReview =>
      UITextConstants.publishResultPendingReviewDescription,
    CreatePublishResultState.queued =>
      UITextConstants.publishResultQueuedDescription,
  };
  return showCupertinoModalPopup<CreatePublishResultAction>(
    context: context,
    builder: (sheetContext) {
      return CupertinoActionSheet(
        key: TestKeys.createPublishResultSheet,
        title: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              state == CreatePublishResultState.published
                  ? CupertinoIcons.check_mark_circled_solid
                  : CupertinoIcons.clock_fill,
              color: state == CreatePublishResultState.published
                  ? AppColors.success
                  : AppColors.warning,
            ),
            const SizedBox(width: AppSpacing.sm),
            Text(title),
          ],
        ),
        message: Text(description),
        actions: [
          if (canViewWork)
            CupertinoActionSheetAction(
              key: TestKeys.createPublishResultViewWorkButton,
              onPressed: () => Navigator.of(
                sheetContext,
              ).pop(CreatePublishResultAction.viewWork),
              child: const Text(UITextConstants.publishResultViewWork),
            ),
          if (canViewTasks)
            CupertinoActionSheetAction(
              onPressed: () => Navigator.of(
                sheetContext,
              ).pop(CreatePublishResultAction.viewPublicationTasks),
              child: const Text(UITextConstants.publishResultViewTasks),
            ),
        ],
        cancelButton: CupertinoActionSheetAction(
          key: TestKeys.createPublishResultDoneButton,
          onPressed: () =>
              Navigator.of(sheetContext).pop(CreatePublishResultAction.done),
          child: const Text(UITextConstants.publishResultDone),
        ),
      );
    },
  );
}

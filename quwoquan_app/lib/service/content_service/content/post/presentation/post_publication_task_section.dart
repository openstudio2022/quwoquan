import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/post_publication_status_reader.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/post_publication_intent_queue_provider.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';

class PostPublicationTaskSection extends StatelessWidget {
  const PostPublicationTaskSection({
    super.key,
    required this.intents,
    required this.onRetry,
    required this.onEdit,
    required this.onRemove,
  });

  final List<LocalPostPublicationIntent> intents;
  final ValueChanged<LocalPostPublicationIntent> onRetry;
  final ValueChanged<LocalPostPublicationIntent> onEdit;
  final ValueChanged<LocalPostPublicationIntent> onRemove;

  @override
  Widget build(BuildContext context) {
    if (intents.isEmpty) {
      return const SizedBox.shrink();
    }
    return Semantics(
      container: true,
      label: CreationText.publishTasksTitle,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(
          AppSpacing.containerMd,
          AppSpacing.containerMd,
          AppSpacing.containerMd,
          0,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              CreationText.publishTasksTitle,
              style: TextStyle(
                color: AppColors.iosLabel(context),
                fontSize: AppTypography.iosTitle3,
                fontWeight: AppTypography.semiBold,
              ),
            ),
            const SizedBox(height: AppSpacing.containerSm),
            for (final intent in intents) ...[
              _PublicationTaskCard(
                key: ValueKey<String>(
                  'publication_task_${intent.command.localDraftId}',
                ),
                intent: intent,
                onRetry: () => onRetry(intent),
                onEdit: () => onEdit(intent),
                onRemove: () => onRemove(intent),
              ),
              const SizedBox(height: AppSpacing.containerSm),
            ],
          ],
        ),
      ),
    );
  }
}

class _PublicationTaskCard extends StatelessWidget {
  const _PublicationTaskCard({
    super.key,
    required this.intent,
    required this.onRetry,
    required this.onEdit,
    required this.onRemove,
  });

  final LocalPostPublicationIntent intent;
  final VoidCallback onRetry;
  final VoidCallback onEdit;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    final publicationState = intent.publicationState;
    final status = _statusForIntent(intent);
    final statusColor = switch (publicationState) {
      ContentPostPublicationState.rejected => AppColors.error,
      ContentPostPublicationState.pendingReview => AppColors.warning,
      ContentPostPublicationState.published =>
        intent.blocked
            ? AppColors.error
            : intent.retryCount > 0
            ? AppColors.warning
            : AppColors.success,
      null =>
        intent.blocked
            ? AppColors.error
            : intent.retryCount > 0
            ? AppColors.warning
            : AppColors.primaryColor,
    };
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.iosGroupedSurfaceElevated(context),
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        border: Border.all(
          color: AppColors.iosSeparator(context).withValues(alpha: 0.35),
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.containerMd),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    _taskTitle(intent),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: AppColors.iosLabel(context),
                      fontSize: AppTypography.body,
                      fontWeight: AppTypography.semiBold,
                    ),
                  ),
                ),
                const SizedBox(width: AppSpacing.sm),
                DecoratedBox(
                  decoration: BoxDecoration(
                    color: statusColor.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(
                      AppSpacing.largeBorderRadius,
                    ),
                  ),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(
                      horizontal: AppSpacing.sm,
                      vertical: AppSpacing.xs,
                    ),
                    child: Text(
                      status,
                      style: TextStyle(
                        color: statusColor,
                        fontSize: AppTypography.caption,
                        fontWeight: AppTypography.semiBold,
                      ),
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.sm),
            Text(
              _descriptionForIntent(intent),
              style: TextStyle(
                color: AppColors.iosSecondaryLabel(context),
                fontSize: AppTypography.caption,
                height: AppTypography.lineHeightRelaxed,
              ),
            ),
            const SizedBox(height: AppSpacing.containerSm),
            _PublicationTaskActions(
              intent: intent,
              onRetry: onRetry,
              onEdit: onEdit,
              onRemove: onRemove,
            ),
          ],
        ),
      ),
    );
  }
}

class _PublicationTaskActions extends StatelessWidget {
  const _PublicationTaskActions({
    required this.intent,
    required this.onRetry,
    required this.onEdit,
    required this.onRemove,
  });

  final LocalPostPublicationIntent intent;
  final VoidCallback onRetry;
  final VoidCallback onEdit;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    final publicationState = intent.publicationState;
    final requiresMediaPreparation = intent.requiresMediaPreparation;
    final requiresMediaCancellation = intent.requiresMediaCancellation;
    final isRejected = publicationState == ContentPostPublicationState.rejected;
    final canRetry =
        requiresMediaCancellation ||
            publicationState == ContentPostPublicationState.published
        ? intent.blocked || intent.retryCount > 0
        : !requiresMediaPreparation &&
              publicationState != ContentPostPublicationState.rejected;
    final canRemove =
        publicationState == ContentPostPublicationState.rejected ||
        (publicationState == null && !requiresMediaCancellation);
    final draftId = intent.command.localDraftId;
    return Row(
      mainAxisAlignment: MainAxisAlignment.end,
      children: [
        if (requiresMediaPreparation || isRejected)
          CupertinoButton(
            key: ValueKey<String>('publication_task_edit_$draftId'),
            padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm),
            onPressed: onEdit,
            child: const Text(CreationText.publishTaskContinueEditing),
          )
        else if (canRetry)
          CupertinoButton(
            key: ValueKey<String>('publication_task_retry_$draftId'),
            padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm),
            onPressed: onRetry,
            child: Text(
              publicationState == ContentPostPublicationState.pendingReview
                  ? CreationText.publishTaskRefresh
                  : CreationText.publishTaskRetry,
            ),
          ),
        if (canRemove)
          CupertinoButton(
            key: ValueKey<String>('publication_task_remove_$draftId'),
            padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm),
            onPressed: onRemove,
            child: const Text(CreationText.publishTaskRemove),
          ),
      ],
    );
  }
}

String _taskTitle(LocalPostPublicationIntent intent) {
  final title = intent.command.title?.trim() ?? '';
  if (title.isNotEmpty) {
    return title;
  }
  final body = intent.command.body?.trim() ?? '';
  return body.isEmpty ? CreationText.publishTaskUntitled : body;
}

String _statusForIntent(LocalPostPublicationIntent intent) {
  switch (intent.publicationState) {
    case ContentPostPublicationState.pendingReview:
      return CreationText.publishTaskPendingReviewStatus;
    case ContentPostPublicationState.published:
      return CreationText.publishTaskFinalizingStatus;
    case ContentPostPublicationState.rejected:
      return CreationText.publishTaskRejectedStatus;
    case null:
      if (intent.requiresMediaCancellation) {
        return CreationText.publishTaskCancellingMediaStatus;
      }
      if (intent.requiresMediaPreparation) {
        return CreationText.publishTaskPreparingMediaStatus;
      }
      if (intent.blocked) {
        return CreationText.publishTaskBlockedStatus;
      }
      if (intent.retryCount > 0) {
        return CreationText.publishTaskRetryWaitingStatus;
      }
      return CreationText.publishTaskSubmittingStatus;
  }
}

String _descriptionForIntent(LocalPostPublicationIntent intent) {
  return switch (intent.publicationState) {
    ContentPostPublicationState.pendingReview =>
      CreationText.publishTaskPendingReviewDescription,
    ContentPostPublicationState.rejected =>
      CreationText.publishTaskRejectedDescription,
    ContentPostPublicationState.published =>
      CreationText.publishTaskFinalizingDescription,
    null when intent.requiresMediaCancellation =>
      CreationText.publishTaskCancellingMediaDescription,
    null when intent.requiresMediaPreparation =>
      CreationText.publishTaskPreparingMediaDescription,
    null when intent.blocked => switch (intent.blockReason) {
      LocalPostPublicationBlockReason.personaChanged =>
        CreationText.publishTaskPersonaChangedDescription,
      LocalPostPublicationBlockReason.invalidReceipt =>
        CreationText.publishTaskInvalidReceiptDescription,
      _ => CreationText.publishTaskBlockedDescription,
    },
    null => CreationText.publishTaskRetryWaitingDescription,
  };
}

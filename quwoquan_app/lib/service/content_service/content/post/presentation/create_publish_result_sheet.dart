import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart' show ValueListenable;
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/publish_settings_models.dart';

enum CreatePublishResultState { published, pendingReview, queued }

/// 发布结果页去向摘要（GWT-005）：只陈述用户真实选择的分发去向，
/// 无对应选择的维度不出现，不伪造去向。
String buildPublishDestinationSummary(PublishSettings settings) {
  final homepageTitle = settings.homepage?.title.trim() ?? '';
  final parts = <String>[
    settings.isPublic
        ? CreationText.publishDestinationPublic
        : CreationText.publishDestinationPrivate,
    if (settings.circleNames.isNotEmpty)
      '${CreationText.publishDestinationCircles}：'
          '${settings.circleNames.join('、')}',
    if (homepageTitle.isNotEmpty)
      '${CreationText.publishDestinationHomepage}：$homepageTitle',
    if (settings.tagLabels.isNotEmpty)
      '${CreationText.publishDestinationTags}：${settings.tagLabels.join('、')}',
    if (settings.locationName.trim().isNotEmpty)
      '${CreationText.publishDestinationLocation}：'
          '${settings.locationName.trim()}',
    if (settings.gatheringTitle.trim().isNotEmpty)
      '${CreationText.publishDestinationGathering}：'
          '${settings.gatheringTitle.trim()}',
  ];
  return parts.join(' · ');
}

enum CreatePublishResultAction { viewWork, viewPublicationTasks, done }

final class CreatePublishResultPresentation {
  const CreatePublishResultPresentation({required this.state, this.postId});

  final CreatePublishResultState state;
  final String? postId;
}

Future<CreatePublishResultAction?> showCreatePublishResultSheet(
  BuildContext context, {
  required CreatePublishResultState state,
  String? postId,
  String destinationSummary = '',
  ValueListenable<CreatePublishResultPresentation>? presentationListenable,
}) {
  final initialPresentation = CreatePublishResultPresentation(
    state: state,
    postId: postId,
  );
  return showCupertinoModalPopup<CreatePublishResultAction>(
    context: context,
    builder: (sheetContext) {
      final listenable = presentationListenable;
      if (listenable == null) {
        return _buildCreatePublishResultSheet(
          sheetContext,
          initialPresentation,
          destinationSummary: destinationSummary,
        );
      }
      return ValueListenableBuilder<CreatePublishResultPresentation>(
        valueListenable: listenable,
        builder: (context, presentation, _) => _buildCreatePublishResultSheet(
          context,
          presentation,
          destinationSummary: destinationSummary,
        ),
      );
    },
  );
}

Widget _buildCreatePublishResultSheet(
  BuildContext sheetContext,
  CreatePublishResultPresentation presentation, {
  String destinationSummary = '',
}) {
  final state = presentation.state;
  final postId = presentation.postId;
  final canViewWork =
      state == CreatePublishResultState.published &&
      (postId?.trim().isNotEmpty ?? false);
  final canViewTasks = state != CreatePublishResultState.published;
  final title = switch (state) {
    CreatePublishResultState.published =>
      CreationText.publishResultSuccessTitle,
    CreatePublishResultState.pendingReview =>
      CreationText.publishResultPendingReviewTitle,
    CreatePublishResultState.queued => CreationText.publishResultQueuedTitle,
  };
  final description = switch (state) {
    CreatePublishResultState.published =>
      CreationText.publishResultSuccessDescription,
    CreatePublishResultState.pendingReview =>
      CreationText.publishResultPendingReviewDescription,
    CreatePublishResultState.queued =>
      CreationText.publishResultQueuedDescription,
  };
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
    message: Column(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Text(description),
        if (destinationSummary.trim().isNotEmpty) ...<Widget>[
          const SizedBox(height: AppSpacing.sm),
          Text(
            destinationSummary.trim(),
            key: TestKeys.createPublishResultDestinationSummary,
            textAlign: TextAlign.center,
          ),
        ],
      ],
    ),
    actions: [
      if (canViewWork)
        CupertinoActionSheetAction(
          key: TestKeys.createPublishResultViewWorkButton,
          onPressed: () => Navigator.of(
            sheetContext,
          ).pop(CreatePublishResultAction.viewWork),
          child: const Text(CreationText.publishResultViewWork),
        ),
      if (canViewTasks)
        CupertinoActionSheetAction(
          onPressed: () => Navigator.of(
            sheetContext,
          ).pop(CreatePublishResultAction.viewPublicationTasks),
          child: const Text(CreationText.publishResultViewTasks),
        ),
    ],
    cancelButton: CupertinoActionSheetAction(
      key: TestKeys.createPublishResultDoneButton,
      onPressed: () =>
          Navigator.of(sheetContext).pop(CreatePublishResultAction.done),
      child: const Text(CreationText.publishResultDone),
    ),
  );
}

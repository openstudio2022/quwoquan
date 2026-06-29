import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/models/create_media_models.dart';

enum CreateMediaPickerBottomAction { oneTapMovie, nextStep }

enum MediaPickerSelectionBlockReason {
  none,
  overLimit,
  imageOnly,
  videoOnly,
  imageLocked,
  videoLocked,
}

@immutable
class CreateMediaPickerBottomActionSpec {
  const CreateMediaPickerBottomActionSpec({
    required this.action,
    required this.label,
    required this.enabled,
    required this.isPrimary,
  });

  final CreateMediaPickerBottomAction action;
  final String label;
  final bool enabled;
  final bool isPrimary;
}

bool isPhotoCreationEntryMode(MediaPickerEntryMode mode) {
  return mode == MediaPickerEntryMode.image;
}

bool isMixedCreationEntryMode(MediaPickerEntryMode mode) {
  return mode == MediaPickerEntryMode.mixed;
}

List<MediaPickerCategory> mediaPickerCategoriesForEntryMode(
  MediaPickerEntryMode mode,
) {
  switch (mode) {
    case MediaPickerEntryMode.image:
    case MediaPickerEntryMode.video:
    case MediaPickerEntryMode.mixed:
      return const <MediaPickerCategory>[];
  }
}

String mediaPickerCompletionLabel({
  required MediaPickerEntryMode mode,
  required int selectionCount,
}) {
  const prefix = UITextConstants.mediaPickerNextStep;
  return '$prefix($selectionCount)';
}

List<CreateMediaPickerBottomActionSpec> mediaPickerBottomActionsForEntryMode({
  required MediaPickerEntryMode mode,
  required int selectionCount,
}) {
  final canContinue = selectionCount > 0;
  if (isPhotoCreationEntryMode(mode)) {
    return <CreateMediaPickerBottomActionSpec>[
      CreateMediaPickerBottomActionSpec(
        action: CreateMediaPickerBottomAction.oneTapMovie,
        label: UITextConstants.mediaPickerOneTapMovie,
        enabled: canContinue,
        isPrimary: false,
      ),
      CreateMediaPickerBottomActionSpec(
        action: CreateMediaPickerBottomAction.nextStep,
        label: mediaPickerCompletionLabel(
          mode: mode,
          selectionCount: selectionCount,
        ),
        enabled: canContinue,
        isPrimary: true,
      ),
    ];
  }
  return <CreateMediaPickerBottomActionSpec>[
    CreateMediaPickerBottomActionSpec(
      action: CreateMediaPickerBottomAction.nextStep,
      label: mediaPickerCompletionLabel(
        mode: mode,
        selectionCount: selectionCount,
      ),
      enabled: canContinue,
      isPrimary: true,
    ),
  ];
}

MediaPickerSelectionBlockReason mediaPickerSelectionBlockReason({
  required MediaPickerEntryMode mode,
  required List<CreateMediaItem> selectedItems,
  required CreateMediaItem candidate,
  required int maxSelection,
}) {
  if (mode == MediaPickerEntryMode.image && candidate.isVideo) {
    return MediaPickerSelectionBlockReason.imageOnly;
  }
  if (mode == MediaPickerEntryMode.video && !candidate.isVideo) {
    return MediaPickerSelectionBlockReason.videoOnly;
  }
  if (mode != MediaPickerEntryMode.mixed) {
    return selectedItems.length >= maxSelection
        ? MediaPickerSelectionBlockReason.overLimit
        : MediaPickerSelectionBlockReason.none;
  }
  if (selectedItems.isEmpty) {
    return maxSelection <= 0
        ? MediaPickerSelectionBlockReason.overLimit
        : MediaPickerSelectionBlockReason.none;
  }
  final lockedToVideo = selectedItems.first.isVideo;
  if (lockedToVideo) {
    return MediaPickerSelectionBlockReason.videoLocked;
  }
  if (candidate.isVideo) {
    return MediaPickerSelectionBlockReason.imageLocked;
  }
  return selectedItems.length >= maxSelection
      ? MediaPickerSelectionBlockReason.overLimit
      : MediaPickerSelectionBlockReason.none;
}

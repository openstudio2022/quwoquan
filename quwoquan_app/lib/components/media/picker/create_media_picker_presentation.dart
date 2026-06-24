import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/models/create_media_models.dart';

enum CreateMediaPickerBottomAction { editImage, completeImage, nextStep }

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

List<MediaPickerCategory> mediaPickerCategoriesForEntryMode(
  MediaPickerEntryMode mode,
) {
  switch (mode) {
    case MediaPickerEntryMode.image:
    case MediaPickerEntryMode.video:
      return const <MediaPickerCategory>[];
  }
}

String mediaPickerCompletionLabel({
  required MediaPickerEntryMode mode,
  required int selectionCount,
}) {
  final prefix = isPhotoCreationEntryMode(mode)
      ? UITextConstants.mediaPickerComplete
      : UITextConstants.mediaPickerNextStep;
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
        action: CreateMediaPickerBottomAction.editImage,
        label: UITextConstants.mediaPickerEditImage,
        enabled: canContinue,
        isPrimary: false,
      ),
      CreateMediaPickerBottomActionSpec(
        action: CreateMediaPickerBottomAction.completeImage,
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

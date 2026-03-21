import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';

enum ConversationLinkAction { openInBrowser, copyLink }

Future<ConversationLinkAction?> showConversationLinkActionSheet(
  BuildContext context, {
  required String url,
  required bool allowOpenInBrowser,
}) {
  return showCupertinoModalPopup<ConversationLinkAction>(
    context: context,
    builder: (popupContext) {
      return CupertinoActionSheet(
        title: const Text(UITextConstants.assistantReferenceActionTitle),
        message: Text(
          url,
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
        ),
        actions: <Widget>[
          if (allowOpenInBrowser)
            CupertinoActionSheetAction(
              onPressed: () => Navigator.of(popupContext).pop(
                ConversationLinkAction.openInBrowser,
              ),
              child: const Text(UITextConstants.assistantReferenceOpenInBrowser),
            ),
          CupertinoActionSheetAction(
            onPressed: () => Navigator.of(popupContext).pop(
              ConversationLinkAction.copyLink,
            ),
            child: const Text(UITextConstants.assistantReferenceCopyLink),
          ),
        ],
        cancelButton: CupertinoActionSheetAction(
          isDefaultAction: true,
          onPressed: () => Navigator.of(popupContext).pop(),
          child: const Text(UITextConstants.cancel),
        ),
      );
    },
  );
}

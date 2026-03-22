import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

enum ConversationLinkAction { openInBrowser, copyLink }

Future<ConversationLinkAction?> showConversationLinkActionSheet(
  BuildContext context, {
  required String url,
  required bool allowOpenInBrowser,
}) {
  return showAppActionSheet<ConversationLinkAction>(
    context,
    title: UITextConstants.assistantReferenceActionTitle,
    message: url,
    sections: [
      AppActionSheetSection<ConversationLinkAction>(
        items: [
          if (allowOpenInBrowser)
            const AppActionSheetItem<ConversationLinkAction>(
              value: ConversationLinkAction.openInBrowser,
              label: UITextConstants.assistantReferenceOpenInBrowser,
              icon: CupertinoIcons.compass,
            ),
          const AppActionSheetItem<ConversationLinkAction>(
            value: ConversationLinkAction.copyLink,
            label: UITextConstants.assistantReferenceCopyLink,
            icon: CupertinoIcons.link,
          ),
        ],
      ),
    ],
  );
}

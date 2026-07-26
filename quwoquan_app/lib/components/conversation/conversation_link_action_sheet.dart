import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/constants/assistant_text_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

enum ConversationLinkAction { openInBrowser, copyLink }

Future<ConversationLinkAction?> showConversationLinkActionSheet(
  BuildContext context, {
  required String url,
  required bool allowOpenInBrowser,
}) {
  return showAppActionSheet<ConversationLinkAction>(
    context,
    title: AssistantText.assistantReferenceActionTitle,
    message: url,
    sections: [
      AppActionSheetSection<ConversationLinkAction>(
        items: [
          if (allowOpenInBrowser)
            const AppActionSheetItem<ConversationLinkAction>(
              value: ConversationLinkAction.openInBrowser,
              label: AssistantText.assistantReferenceOpenInBrowser,
              icon: CupertinoIcons.compass,
            ),
          const AppActionSheetItem<ConversationLinkAction>(
            value: ConversationLinkAction.copyLink,
            label: AssistantText.assistantReferenceCopyLink,
            icon: CupertinoIcons.link,
          ),
        ],
      ),
    ],
  );
}

import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/surfaces/app_action_sheet.dart';

Future<String?> showBlockedKeywordConfirmationSheet(
  BuildContext context, {
  required String suggestedKeyword,
}) {
  final keyword = suggestedKeyword.trim();
  if (keyword.isEmpty) return Future<String?>.value();
  return showAppActionSheet<String>(
    context,
    title: ContentText.blockedKeywordsAddTitle,
    message: UITextConstants.blockKeywordConfirmMessage(keyword),
    sections: <AppActionSheetSection<String>>[
      AppActionSheetSection<String>(
        items: <AppActionSheetItem<String>>[
          AppActionSheetItem<String>(
            value: keyword,
            label: UITextConstants.blockKeywordConfirmLabel(keyword),
          ),
        ],
      ),
    ],
  );
}

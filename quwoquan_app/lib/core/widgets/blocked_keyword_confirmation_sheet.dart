import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/widgets/app_action_sheet.dart';

Future<String?> showBlockedKeywordConfirmationSheet(
  BuildContext context, {
  required String suggestedKeyword,
}) {
  final keyword = suggestedKeyword.trim();
  if (keyword.isEmpty) return Future<String?>.value();
  return showAppActionSheet<String>(
    context,
    title: UITextConstants.blockedKeywordsAddTitle,
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

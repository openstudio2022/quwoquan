import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/widgets/app_action_sheet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 所有内容、评论与用户举报入口共享的原因选择器。
///
/// 选项值严格来自 metadata `ReportReason`，页面不得自行维护第二套 reason。
Future<ContentReportReason?> showContentReportReasonSheet(
  BuildContext context,
) {
  return showAppActionSheet<ContentReportReason>(
    context,
    title: UITextConstants.profileReportReasonTitle,
    sections: <AppActionSheetSection<ContentReportReason>>[
      AppActionSheetSection<ContentReportReason>(
        items: <AppActionSheetItem<ContentReportReason>>[
          for (final reason in ContentReportReason.values)
            AppActionSheetItem<ContentReportReason>(
              value: reason,
              label: contentReportReasonLabel(reason),
            ),
        ],
      ),
    ],
  );
}

String contentReportReasonLabel(ContentReportReason reason) {
  return switch (reason) {
    ContentReportReason.spam => UITextConstants.profileReportReasonSpam,
    ContentReportReason.harassment =>
      UITextConstants.profileReportReasonHarassment,
    ContentReportReason.violence => UITextConstants.reportReasonViolence,
    ContentReportReason.adult => UITextConstants.profileReportReasonPornography,
    ContentReportReason.copyright => UITextConstants.reportReasonCopyright,
    ContentReportReason.other => UITextConstants.profileReportReasonOther,
  };
}

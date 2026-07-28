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
    title: ContentText.profileReportReasonTitle,
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
    ContentReportReason.spam => ContentText.profileReportReasonSpam,
    ContentReportReason.harassment =>
      ContentText.profileReportReasonHarassment,
    ContentReportReason.violence => ContentText.reportReasonViolence,
    ContentReportReason.adult => ContentText.profileReportReasonPornography,
    ContentReportReason.copyright => ContentText.reportReasonCopyright,
    ContentReportReason.other => ContentText.profileReportReasonOther,
  };
}

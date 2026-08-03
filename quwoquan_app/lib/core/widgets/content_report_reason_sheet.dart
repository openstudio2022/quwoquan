import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/widgets/app_action_sheet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 所有内容、评论与用户举报入口共享的原因选择器。
///
/// 选项值严格来自 metadata `ReportReason`，页面不得自行维护第二套 reason。
Future<ReportReason?> showContentReportReasonSheet(BuildContext context) {
  return showAppActionSheet<ReportReason>(
    context,
    title: ContentText.profileReportReasonTitle,
    sections: <AppActionSheetSection<ReportReason>>[
      AppActionSheetSection<ReportReason>(
        items: <AppActionSheetItem<ReportReason>>[
          for (final reason in ReportReason.values)
            AppActionSheetItem<ReportReason>(
              value: reason,
              label: contentReportReasonLabel(reason),
            ),
        ],
      ),
    ],
  );
}

String contentReportReasonLabel(ReportReason reason) {
  return switch (reason) {
    ReportReason.spam => ContentText.profileReportReasonSpam,
    ReportReason.harassment => ContentText.profileReportReasonHarassment,
    ReportReason.violence => ContentText.reportReasonViolence,
    ReportReason.adult => ContentText.profileReportReasonPornography,
    ReportReason.copyright => ContentText.reportReasonCopyright,
    ReportReason.other => ContentText.profileReportReasonOther,
  };
}

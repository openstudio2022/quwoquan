import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show EndReason;

/// 通话 ended 跳离前的终态反馈文案（单一真相源）。
///
/// 跳离竞态会吞掉页面内 CallStageBanner，超时/未接/被拒的原因必须以
/// toast 在离场前可感知；返回 null 表示正常收尾不打扰。
/// - 呼出方：no_answer/timeout →「无人接听」，rejected →「对方已拒绝」。
/// - 来电方：no_answer/timeout →「未接听」。
String? callEndedFeedbackText({
  required EndReason? endReason,
  required bool outgoing,
}) {
  return switch (endReason) {
    EndReason.noAnswer || EndReason.timeout =>
      outgoing ? CallText.callSummaryNoAnswer : CallText.callSummaryMissed,
    EndReason.rejected when outgoing => CallText.callSummaryRejected,
    _ => null,
  };
}

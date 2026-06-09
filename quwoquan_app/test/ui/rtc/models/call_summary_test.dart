import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/ui/rtc/models/call_state.dart';

void main() {
  // ──────────────────────────────────────────────────────────────────
  // FaceTime 级结束摘要：时长/未接通原因单一派生，后续通话记录回插复用。
  // ──────────────────────────────────────────────────────────────────
  group('CallSummary.formatDuration', () {
    test('分秒补零', () {
      expect(
        CallSummary.formatDuration(const Duration(seconds: 5)),
        '00:05',
      );
      expect(
        CallSummary.formatDuration(
          const Duration(minutes: 3, seconds: 9),
        ),
        '03:09',
      );
    });

    test('超过一小时显示 h:mm:ss', () {
      expect(
        CallSummary.formatDuration(
          const Duration(hours: 1, minutes: 2, seconds: 7),
        ),
        '1:02:07',
      );
    });
  });

  group('CallSummary.describe', () {
    test('已接通：显示通话时长', () {
      expect(
        CallSummary.describe(
          duration: const Duration(minutes: 2, seconds: 30),
          endReason: EndReason.completed,
          connected: true,
        ),
        '${UITextConstants.callSummaryDurationPrefix}02:30',
      );
    });

    test('未接通 + cancelled/initiatorHangup → 已取消', () {
      for (final reason in [
        EndReason.cancelled,
        EndReason.initiatorHangup,
      ]) {
        expect(
          CallSummary.describe(
            duration: Duration.zero,
            endReason: reason,
            connected: false,
          ),
          UITextConstants.callSummaryCancelled,
          reason: reason.name,
        );
      }
    });

    test('未接通 + rejected/busy → 对方已拒绝', () {
      for (final reason in [EndReason.rejected, EndReason.busy]) {
        expect(
          CallSummary.describe(
            duration: Duration.zero,
            endReason: reason,
            connected: false,
          ),
          UITextConstants.callSummaryRejected,
          reason: reason.name,
        );
      }
    });

    test('未接通 + timeout → 无人接听', () {
      expect(
        CallSummary.describe(
          duration: Duration.zero,
          endReason: EndReason.timeout,
          connected: false,
        ),
        UITextConstants.callSummaryNoAnswer,
      );
    });

    test('connected 但时长为 0 仍按未接通原因', () {
      expect(
        CallSummary.describe(
          duration: Duration.zero,
          endReason: EndReason.timeout,
          connected: true,
        ),
        UITextConstants.callSummaryNoAnswer,
      );
    });
  });
}

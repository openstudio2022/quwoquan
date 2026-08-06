import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/domain/call_participant.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/domain/call_state.dart';

void main() {
  // ──────────────────────────────────────────────────────────────────
  // FaceTime 级结束摘要：时长/未接通原因单一派生，后续通话记录回插复用。
  // ──────────────────────────────────────────────────────────────────
  group('CallSummary.formatDuration', () {
    test('分秒补零', () {
      expect(CallSummary.formatDuration(const Duration(seconds: 5)), '00:05');
      expect(
        CallSummary.formatDuration(const Duration(minutes: 3, seconds: 9)),
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
          endReason: EndReason.normal,
          connected: true,
        ),
        '${CallText.callSummaryDurationPrefix}02:30',
      );
    });

    test('未接通 + cancelled → 已取消', () {
      expect(
        CallSummary.describe(
          duration: Duration.zero,
          endReason: EndReason.cancelled,
          connected: false,
        ),
        CallText.callSummaryCancelled,
      );
    });

    test('未接通 + rejected → 对方已拒绝', () {
      expect(
        CallSummary.describe(
          duration: Duration.zero,
          endReason: EndReason.rejected,
          connected: false,
        ),
        CallText.callSummaryRejected,
      );
    });

    test('未接通 + noAnswer/timeout → 无人接听', () {
      for (final reason in [EndReason.noAnswer, EndReason.timeout]) {
        expect(
          CallSummary.describe(
            duration: Duration.zero,
            endReason: reason,
            connected: false,
          ),
          CallText.callSummaryNoAnswer,
          reason: reason.name,
        );
      }
    });

    test('connected 但时长为 0 仍按未接通原因', () {
      expect(
        CallSummary.describe(
          duration: Duration.zero,
          endReason: EndReason.timeout,
          connected: true,
        ),
        CallText.callSummaryNoAnswer,
      );
    });
  });

  group('多人通话摘要', () {
    test('超过 6 人时以 +N 表达未展开人数', () {
      expect(callParticipantOverflowCount(6), 0);
      expect(callParticipantOverflowCount(7), 1);
      expect(callParticipantOverflowCount(12), 6);
      expect(
        UITextConstants.callAdditionalParticipants(
          callParticipantOverflowCount(12),
        ),
        '+6',
      );
    });
  });
}

import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show EndReason;

enum CallLogSummaryKind { duration, cancelled, rejected, noAnswer, missed }

final class CallLogSummaryView {
  const CallLogSummaryView({required this.kind, this.formattedDuration});

  final CallLogSummaryKind kind;
  final String? formattedDuration;
}

String formatCallLogDuration(Duration duration) {
  final hours = duration.inHours;
  final minutes = duration.inMinutes.remainder(60).toString().padLeft(2, '0');
  final seconds = duration.inSeconds.remainder(60).toString().padLeft(2, '0');
  if (hours > 0) {
    return '$hours:$minutes:$seconds';
  }
  return '$minutes:$seconds';
}

CallLogSummaryView resolveCallLogSummary({
  required Duration duration,
  required EndReason endReason,
  required bool connected,
}) {
  if (connected && duration > Duration.zero) {
    return CallLogSummaryView(
      kind: CallLogSummaryKind.duration,
      formattedDuration: formatCallLogDuration(duration),
    );
  }
  return CallLogSummaryView(
    kind: switch (endReason) {
      EndReason.cancelled => CallLogSummaryKind.cancelled,
      EndReason.rejected => CallLogSummaryKind.rejected,
      EndReason.noAnswer || EndReason.timeout => CallLogSummaryKind.noAnswer,
      _ => CallLogSummaryKind.missed,
    },
  );
}

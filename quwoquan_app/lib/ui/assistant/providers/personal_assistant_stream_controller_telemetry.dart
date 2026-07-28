part of 'personal_assistant_stream_controller.dart';

void _recordAssistantTurnQuality(
  Ref ref, {
  required String turnAction,
  required String result,
  required DateTime startedAt,
  String? failReasonCode,
  String? operationId,
}) {
  if (!ref.mounted) {
    return;
  }
  final durationMs = DateTime.now()
      .difference(startedAt)
      .inMilliseconds
      .clamp(0, 1 << 31)
      .toInt();
  unawaited(() async {
    try {
      await ref
          .read(appTelemetryReporterProvider)
          .record(
            AppTelemetryPayload.assistantTurnQuality(
              turnAction: turnAction,
              result: result,
              durationMs: durationMs,
              failReasonCode: failReasonCode?.trim().isEmpty ?? true
                  ? null
                  : failReasonCode!.trim(),
              operationId: operationId?.trim().isEmpty ?? true
                  ? null
                  : operationId!.trim(),
            ),
          );
    } catch (error, stackTrace) {
      developer.log(
        'assistant turn telemetry failed',
        name: 'personal_assistant',
        error: error.runtimeType,
        stackTrace: stackTrace,
      );
    }
  }());
}

import 'package:quwoquan_app/runtime/observability/generated/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_outbox.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_reporter.dart';

final class RecordedAppTelemetry {
  const RecordedAppTelemetry({
    required this.payload,
    required this.pageName,
    required this.occurredAt,
  });

  final AppTelemetryPayload payload;
  final String? pageName;
  final DateTime? occurredAt;

  String get eventType => payload.eventType;
  String get action => (payload.extensions['action'] ?? '').toString();
  Map<String, Object?> get extensions => payload.extensions;
}

class RecordingAppTelemetryRecorder implements AppTelemetryRecorder {
  RecordingAppTelemetryRecorder({
    this.recordResult = AppTelemetryRecordResult.accepted,
    this.flushResult = AppTelemetryFlushResult.delivered,
    this.recordError,
  });

  final List<RecordedAppTelemetry> recorded = <RecordedAppTelemetry>[];
  AppTelemetryRecordResult recordResult;
  AppTelemetryFlushResult flushResult;
  Object? recordError;
  int clearPendingCount = 0;
  int flushCount = 0;
  int networkAvailableCount = 0;

  @override
  Future<AppTelemetryRecordResult> record(
    AppTelemetryPayload payload, {
    String? pageName,
    DateTime? occurredAt,
  }) async {
    final error = recordError;
    if (error != null) throw error;
    recorded.add(
      RecordedAppTelemetry(
        payload: payload,
        pageName: pageName,
        occurredAt: occurredAt,
      ),
    );
    return recordResult;
  }

  @override
  Future<AppTelemetryFlushResult> flush() async {
    flushCount++;
    return flushResult;
  }

  @override
  Future<void> clearPendingForLogout() async {
    clearPendingCount++;
  }

  @override
  void onNetworkAvailable() {
    networkAvailableCount++;
  }
}

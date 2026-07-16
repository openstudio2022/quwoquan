import 'package:quwoquan_app/cloud/runtime/observability/cloud_operation_telemetry.dart';

final class RecordingCloudOperationTelemetrySink
    implements CloudOperationTelemetrySink {
  final List<CloudOperationTelemetryEvent> events =
      <CloudOperationTelemetryEvent>[];

  @override
  void record(CloudOperationTelemetryEvent event) {
    events.add(event);
  }
}

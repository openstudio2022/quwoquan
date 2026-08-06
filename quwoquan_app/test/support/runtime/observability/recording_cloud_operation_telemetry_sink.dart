import 'package:quwoquan_app/runtime/observability/cloud_operation_telemetry.dart';

/// Local-contract recorder for the runtime observability boundary.
final class RecordingCloudOperationTelemetrySink
    implements CloudOperationTelemetrySink {
  final List<CloudOperationTelemetryEvent> events =
      <CloudOperationTelemetryEvent>[];

  @override
  void record(CloudOperationTelemetryEvent event) {
    events.add(event);
  }
}

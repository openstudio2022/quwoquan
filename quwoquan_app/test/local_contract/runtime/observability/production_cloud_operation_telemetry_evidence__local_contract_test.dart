// spec_ref: specs/feature-tree/runtime/runtime-observability/log-schema-and-kv-policy/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/observability/cloud_operation_telemetry.dart';

import '../../../support/runtime/api_contract/production_cloud_operation_telemetry_evidence.dart';

void main() {
  test('production sink evidence is read from the real access.log', () async {
    final evidence = await ProductionCloudOperationTelemetryEvidence.start(
      clientContextProvider: const _ContractClientContext(),
    );
    addTearDown(evidence.dispose);

    evidence.sink.record(
      const CloudOperationTelemetryEvent(
        canonicalOperationId: 'runtime.contract.ReadTelemetryEvidence',
        surfaceId: 'appShell',
        method: 'GET',
        pathTemplate: '/runtime/telemetry-evidence',
        elapsed: Duration(milliseconds: 7),
        succeeded: true,
        attempt: 1,
        requestId: 'request-telemetry-evidence',
        traceId: 'trace-telemetry-evidence',
        statusCode: 200,
      ),
    );
    evidence.sink.record(
      const CloudOperationTelemetryEvent(
        canonicalOperationId: 'runtime.contract.WriteTelemetryEvidence',
        surfaceId: 'appShell',
        method: 'POST',
        pathTemplate: '/runtime/telemetry-evidence',
        elapsed: Duration(milliseconds: 11),
        succeeded: false,
        attempt: 1,
        requestId: 'request-telemetry-failure',
        traceId: 'trace-telemetry-failure',
        statusCode: 503,
        failureCode: 'RUNTIME.SYSTEM.unavailable',
      ),
    );

    final events = await evidence.waitForEvents(minimumCount: 2);

    expect(events, hasLength(2));
    expect(
      events.first.canonicalOperationId,
      contains('ReadTelemetryEvidence'),
    );
    expect(events.first.succeeded, isTrue);
    expect(events.first.requestId, 'request-telemetry-evidence');
    expect(events.first.traceId, 'trace-telemetry-evidence');
    expect(events.first.statusCode, 200);
    expect(
      events.last.canonicalOperationId,
      contains('WriteTelemetryEvidence'),
    );
    expect(events.last.succeeded, isFalse);
    expect(events.last.statusCode, 503);
  });
}

final class _ContractClientContext implements CloudClientContextProvider {
  const _ContractClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'telemetry-evidence-contract',
      platform: 'test',
      appVersion: 'contract',
      locale: 'zh-CN',
    );
  }
}

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/app/startup/startup_telemetry.dart';
import 'package:quwoquan_app/cloud/remote/ops/startup_telemetry_remote.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';

void main() {
  test('服务端 duplicateBatch 回执映射为完整幂等 ACK', () async {
    final transport = RemoteStartupTelemetryTransport(
      httpClient: CloudHttpClient(
        client: MockClient(
          (request) async => http.Response(
            '{"acceptedCount":1,"duplicateBatch":true}',
            200,
            headers: const {'content-type': 'application/json'},
          ),
        ),
      ),
      baseUrl: 'https://ops.gamma.quwoquan.com',
    );
    final ack = await transport.report([
      StartupTelemetryEvent(
        eventId: 'event_1234567890123456',
        attemptId: 'attempt_12345678901234',
        sequence: 1,
        phase: StartupTelemetryPhase.terminal,
        phaseDurationMs: 10,
        elapsedMs: 1000,
        outcome: 'success',
        occurredAt: DateTime.utc(2026, 7, 28),
        platform: 'android',
        runtimeEnv: 'gamma',
        appVersion: '1.0.0',
        networkClass: 'wifi',
        recoverySurface: '',
        failureCode: '',
        failureSource: '',
        deadlineOrigin: 'android_process',
      ),
    ], proof: 'proof_123456789012345678901234');

    expect(ack.acceptedCount, 0);
    expect(ack.duplicateCount, 1);
    expect(ack.acknowledges(1), isTrue);
  });
}

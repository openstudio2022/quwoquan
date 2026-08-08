// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-003
// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/realtime-gateway/realtime-channel-delivery/spec.md#gwt-001
// readiness_case: connection_issue_connection_ticket_app_api
// readiness_case: connection_long_poll_app_api

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/realtime_api_contract_harness.dart';

void main() {
  RealtimeApiContractHarness? harness;

  setUpAll(() async => harness = await RealtimeApiContractHarness.create());
  tearDownAll(() async {
    final currentHarness = harness;
    if (currentHarness != null) {
      await currentHarness.close();
    }
  });

  test('generated Remote 签发 connection ticket', () async {
    final stopwatch = Stopwatch()..start();
    final ticket = await harness!.connectionOperations.issueConnectionTicket();
    stopwatch.stop();

    expect(stopwatch.elapsedMilliseconds, lessThan(1500));
    expect(ticket.ticket, isNotEmpty);
    expect(ticket.expiresAt, isNotNull);
  });

  test('generated Remote long-poll 返回 canonical response', () async {
    final response = await harness!.connectionOperations.longPoll(timeout: 1);

    expect(response.nextCursor, isNotEmpty);
    expect(response.events, isA<List<RealtimeEventEnvelope>>());
    expect(response.transportResumed, isA<bool>());
  });
}

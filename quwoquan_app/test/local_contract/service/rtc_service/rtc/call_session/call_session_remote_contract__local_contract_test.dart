// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/commercial-remote-only-message-system/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/spec.md#sit-006
import 'package:flutter_test/flutter_test.dart';

import '../../../../../support/runtime/business_contract_fixture_server.dart';

void main() {
  test('call session fixture exposes canonical RTC sessions', () async {
    final server = await BusinessContractFixtureServer.start();
    addTearDown(server.close);

    final calls = await server.getJsonList('/rtc/calls', 'items');
    expect(
      calls.map((item) => item['sessionId']),
      contains(server.expectedRtcSessionId),
    );
  });
}

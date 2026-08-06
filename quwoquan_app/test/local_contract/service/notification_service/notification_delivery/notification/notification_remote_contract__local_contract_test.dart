// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/commercial-remote-only-message-system/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/spec.md#sit-006
import 'package:flutter_test/flutter_test.dart';

import '../../../../../support/runtime/business_contract_fixture_server.dart';

void main() {
  test('notification fixture exposes canonical app messages', () async {
    final server = await BusinessContractFixtureServer.start();
    addTearDown(server.close);

    final messages = await server.getJsonList('/app-messages', 'items');
    expect(
      messages.map((item) => item['messageId']),
      contains('fixture_app_message_assistant_stock'),
    );
  });
}

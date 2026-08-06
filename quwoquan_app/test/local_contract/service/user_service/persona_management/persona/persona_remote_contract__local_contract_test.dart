// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/commercial-remote-only-message-system/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/spec.md#sit-006
import 'package:flutter_test/flutter_test.dart';

import '../../../../../support/runtime/business_contract_fixture_server.dart';

void main() {
  test('persona fixture exposes the canonical current user', () async {
    final server = await BusinessContractFixtureServer.start();
    addTearDown(server.close);

    final profiles = await server.getJsonList('/user/profile', 'items');
    expect(
      profiles.map((item) => item['userId']),
      contains(businessFixtureCurrentUserId),
    );
  });
}

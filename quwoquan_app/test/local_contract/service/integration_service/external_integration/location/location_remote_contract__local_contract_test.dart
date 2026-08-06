// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/commercial-remote-only-message-system/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/spec.md#sit-006
import 'package:flutter_test/flutter_test.dart';

import '../../../../../support/runtime/business_contract_fixture_server.dart';

void main() {
  test('location fixture exposes canonical POI rows', () async {
    final server = await BusinessContractFixtureServer.start();
    addTearDown(server.close);

    final pois = await server.getJsonList(
      '/integration/external_integration/locations/pois',
      'items',
    );
    expect(
      pois.map((item) => item['poiId']),
      contains('fixture_poi_west_lake'),
    );
  });
}

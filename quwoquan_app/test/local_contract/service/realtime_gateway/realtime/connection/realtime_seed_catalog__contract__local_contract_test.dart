import 'package:flutter_test/flutter_test.dart';

import '../../../../../support/service/realtime_gateway/realtime/connection/connection_typed_double.dart';

void main() {
  test('registered conversation returns canonical fixture event', () {
    final events = FixtureRealtimeEventCatalog.eventsForConversation(
      'conv_001',
    );
    expect(events, isNotEmpty);
    expect(events.single['type'], 'MessageSent');
    expect(events.single['conversationId'], 'conv_001');
  });

  test('unknown conversation does not synthesize events', () {
    expect(
      FixtureRealtimeEventCatalog.eventsForConversation('unknown_conversation'),
      isEmpty,
    );
  });
}

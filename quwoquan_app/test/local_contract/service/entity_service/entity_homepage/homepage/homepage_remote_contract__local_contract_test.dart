// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/commercial-remote-only-message-system/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/spec.md#sit-006
import 'package:flutter_test/flutter_test.dart';

import '../../../../../support/runtime/business_contract_fixture_server.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_state_seed_builder.dart';
import '../../../../../support/service/circle_service/circle_management/circle/circle_test_builder.dart';
import '../../../../../support/service/content_service/content/post/content_post_wire_test_builder.dart';
import '../../../../../support/service/notification_service/notification_delivery/notification/app_message_test_builder.dart';
import '../../../../../support/service/user_service/account/user_account/user_profile_test_builder.dart';


BusinessFixtureSeeds businessFixtureSeeds() {
  final chatSeed = minimalChatStateSeed();
  return BusinessFixtureSeeds(
    content: contentDiscoveryWireExample(),
    chatTimeline: chatStateSeedTimelineWire(chatSeed),
    chatContacts: chatStateSeedContactsWire(chatSeed),
    circle: businessCircleWireExample(),
    user: userProfileWireExample(),
    notificationMessages: appMessageWireExamples(),
  );
}

void main() {
  test('homepage fixture exposes canonical search rows', () async {
    final server = await BusinessContractFixtureServer.start(
      seeds: businessFixtureSeeds(),
    );
    addTearDown(server.close);

    final homepages = await server.getJsonList('/homepages/search', 'items');
    expect(
      homepages.map((item) => item['homepageId']),
      contains('fixture_homepage_author'),
    );
  });
}

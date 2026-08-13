// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/commercial-remote-only-message-system/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/spec.md#sit-006
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/adapters/discovery_feed_query_remote.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

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
  test(
    'feed delivery page reads canonical fixture feed through HTTP',
    () async {
      final server = await BusinessContractFixtureServer.start(
        seeds: businessFixtureSeeds(),
      );
      addTearDown(server.close);
      final query = RemoteContentDiscoveryFeedQuery(
        client: server.buildGeneratedClient(),
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.homeFeed.id,
          routeId: AppUiSurfaces.homeFeed.routeId,
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(),
        ),
        blockedKeywordsLoader: () async => const <String>[],
      );

      final photoFeed = (await query.listDiscoveryFeedPage(
        category: 'photo',
        identity: 'work',
        type: 'photo',
        limit: 20,
      )).items;
      expect(photoFeed.length, greaterThanOrEqualTo(3));
      expect(photoFeed.map((item) => item.id), contains('fixture_photo_001'));
      expect(
        photoFeed.every(
          (item) => item.primaryVisualUrl.contains(
            'media/image/s/archived-image/post/',
          ),
        ),
        isTrue,
      );

      final videoFeed = (await query.listDiscoveryFeedPage(
        category: 'video',
        identity: 'work',
        type: 'video',
        limit: 20,
      )).items;
      expect(videoFeed.length, greaterThanOrEqualTo(2));
      expect(videoFeed.every((item) => item.hasVideo), isTrue);

      final followingFeed = (await query.listDiscoveryFeedPage(
        category: 'following',
        identity: 'moment',
        limit: 20,
      )).items;
      expect(followingFeed.length, greaterThanOrEqualTo(3));
    },
  );
}

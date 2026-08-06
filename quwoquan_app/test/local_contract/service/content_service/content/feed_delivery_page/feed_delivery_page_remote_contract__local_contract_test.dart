// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/commercial-remote-only-message-system/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/spec.md#sit-006
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/adapters/discovery_feed_query_remote.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/business_contract_fixture_server.dart';

void main() {
  test(
    'feed delivery page reads canonical fixture feed through HTTP',
    () async {
      final server = await BusinessContractFixtureServer.start();
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

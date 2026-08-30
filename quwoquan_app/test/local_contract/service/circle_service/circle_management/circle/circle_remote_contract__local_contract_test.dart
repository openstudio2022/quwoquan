// spec_ref: specs/feature-tree/circle-community/spec.md#dom-001
// spec_ref: specs/feature-tree/circle-community/spec.md#dom-002
// spec_ref: specs/feature-tree/circle-community/spec.md#dom-002.t5
// spec_ref: specs/feature-tree/circle-community/spec.md#dom-002.t12
// readiness_case: circle_list_circles_app_local
// readiness_case: circle_list_circle_discovery_feed_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/adapters/circle_query_remote.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/circle/circle_request_page_ids.g.dart';
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
  test('circle reader decodes canonical circles through HTTP', () async {
    final server = await BusinessContractFixtureServer.start(
      seeds: businessFixtureSeeds(),
    );
    addTearDown(server.close);
    final query = RemoteCircleQueryReader(
      client: server.buildGeneratedClient(),
      invocationContext: (clientPageId, {required command}) {
        final surface =
            clientPageId == CircleRequestPageIds.listCircles ||
                clientPageId == CircleRequestPageIds.searchCircles ||
                clientPageId == CircleRequestPageIds.listCircleDiscoveryFeed
            ? AppUiSurfaces.circlesList
            : AppUiSurfaces.circleDetail;
        return CloudOperationInvocationContext(
          surfaceId: surface.id,
          routeId: surface.routeId,
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(
            accountId: businessFixtureCurrentUserId,
            personaId: businessFixtureCurrentUserId,
          ),
        );
      },
    );

    final circles = (await query.list(CircleListQuery(limit: 20))).items;
    expect(circles.length, greaterThanOrEqualTo(6));
    expect(circles.map((item) => item.id), contains('fixture_circle_photo'));
    expect(
      circles.every(
        (item) =>
            item.coverUrl?.contains('media/image/s/archived-image/circle/') ==
            true,
      ),
      isTrue,
    );
    final circle = await query.get(
      CircleDetailQuery(circleId: 'fixture_circle_photo'),
    );
    expect(circle.id, 'fixture_circle_photo');
    await expectLater(
      query.listDiscoveryFeed(CircleDiscoveryFeedQuery(limit: 20)),
      throwsA(
        isA<CloudException>().having(
          (error) => error.runtimeFailure,
          'runtimeFailure',
          isNotNull,
        ),
      ),
    );
  });
}

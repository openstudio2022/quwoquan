// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/text-post-commercial-publication/spec.md#gwt-005
// readiness_case: post_get_post_app_local
// readiness_case: post_list_user_posts_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/post_reader_remote.dart';
import 'package:quwoquan_app/runtime/di/content_surface_view_mapper.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
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
  test('post reader decodes detail and persona posts through HTTP', () async {
    final server = await BusinessContractFixtureServer.start(
      seeds: businessFixtureSeeds(),
    );
    addTearDown(server.close);
    final reader = RemoteContentPostReaderAdapter(
      client: server.buildGeneratedClient(),
      invocationContext: (clientPageId) {
        final surface = clientPageId == ContentRequestPageIds.listUserPosts
            ? AppUiSurfaces.userProfile
            : AppUiSurfaces.workBrowser;
        return CloudOperationInvocationContext(
          surfaceId: surface.id,
          routeId: surface.routeId,
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(),
        );
      },
    );

    final post = await reader.getPost(postId: 'fixture_photo_001');
    expect(post.post.id, 'fixture_photo_001');

    final userPostsPage = await reader.listUserPosts(
      userId: businessFixtureCurrentUserId,
      limit: 20,
    );
    final userPosts = userPostsPage.items;
    expect(userPosts.length, greaterThanOrEqualTo(4));
    expect(userPosts.map((item) => item.id), contains('fixture_moment_001'));
    final moment = userPosts.firstWhere(
      (item) => item.id == 'fixture_moment_001',
    );
    final unavailableMediaResolver = MediaDeliveryResolver(
      MediaEndpointConfig.tryCreateAvailable(
        avatarBaseUrl: '',
        imageBaseUrl: '',
        videoBaseUrl: '',
        attachmentBaseUrl: '',
      )!,
    );
    final momentView = ContentSurfaceViewMapper.fromDto(
      moment,
      mediaResolver: unavailableMediaResolver,
    );
    expect(
      momentView.cover,
      isNull,
      reason: '未注入媒体交付 endpoint 时，不得把 post object key 当作可加载 URL',
    );
    expect(momentView.images, isEmpty);
  });
}

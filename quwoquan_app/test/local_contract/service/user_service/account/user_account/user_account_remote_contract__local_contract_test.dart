// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/commercial-remote-only-message-system/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/spec.md#sit-006
// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/persona-management/spec.md#gwt-001
// readiness_case: user_account_get_active_persona_context_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/adapters/user_profile_query_remote.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/adapters/persona_query_remote.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/adapters/profile_query_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/business_contract_fixture_server.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_state_seed_builder.dart';
import '../../../../../support/service/circle_service/circle_management/circle/circle_test_builder.dart';
import '../../../../../support/service/content_service/content/post/content_post_wire_test_builder.dart';
import '../../../../../support/service/notification_service/notification_delivery/notification/app_message_test_builder.dart';
import '../../../../../support/service/user_service/account/user_account/user_profile_test_builder.dart';

final RegExp _defaultNicknamePattern = RegExp(r'^新同学_\d{6}_\d{7}$');


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
  test('user account facet decodes active persona and profile', () async {
    final server = await BusinessContractFixtureServer.start(
      seeds: businessFixtureSeeds(),
    );
    addTearDown(server.close);
    final userProfileQuery = RemoteUserProfileQueryFacet(
      client: server.buildGeneratedClient(),
      invocationContext: (clientPageId, canonicalOperationId) {
        final operation = appCloudOperationContracts[canonicalOperationId]!;
        final surface = AppUiSurfaces.byId[operation.surfaceIds.first]!;
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
    final personaQuery = RemotePersonaQuery(
      managementQuery: userProfileQuery,
      publicProfileQuery: userProfileQuery,
    );
    final profileQuery = RemoteProfileQuery(
      publicProfileQuery: userProfileQuery,
      userHomepageQuery: userProfileQuery,
    );

    final currentUser = await profileQuery.getUserProfile(
      businessFixtureCurrentUserId,
    );
    final activePersonaContext = await personaQuery.getActivePersonaContext();
    expect(activePersonaContext.ownerUserId, businessFixtureCurrentUserId);
    expect(activePersonaContext.personaId, businessFixtureCurrentUserId);
    expect(currentUser.displayName, matches(_defaultNicknamePattern));
    final imageBase = CloudRuntimeConfig.mediaImageCdnBaseUrl.trim();
    if (imageBase.isEmpty) {
      expect(
        currentUser.backgroundUrl,
        isEmpty,
        reason: '未注入媒体交付 endpoint 时，不得把 object key 当作可加载 URL',
      );
    } else {
      expect(
        currentUser.backgroundUrl,
        startsWith('${Uri.parse(imageBase).origin}/media/background/'),
        reason: 'background 复用 mediaImage origin，路径只由 publicSliceKey 决定',
      );
    }
  });
}

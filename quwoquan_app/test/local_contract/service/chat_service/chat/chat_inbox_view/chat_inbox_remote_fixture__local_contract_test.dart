// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/commercial-remote-only-message-system/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/spec.md#sit-006
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/chat_dependencies.dart';
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
  test('chat inbox reads canonical conversations through HTTP', () async {
    final server = await BusinessContractFixtureServer.start(
      seeds: businessFixtureSeeds(),
    );
    addTearDown(server.close);
    final repository = ChatProductionComposition.repository(
      client: server.buildGeneratedClient(),
      invocationContext: _chatContext,
    );

    final inbox = await repository.listInbox(limit: 20);
    expect(inbox, hasLength(2));
    expect(inbox.map((item) => item.id), contains('fixture_conv_direct'));
    expect(inbox.every((item) => item.avatarUrl.trim().isNotEmpty), isTrue);
  });
}

CloudOperationInvocationContext _chatContext(
  AppUiSurface surface,
  String clientPageId, {
  String? idempotencyKey,
}) {
  return CloudOperationInvocationContext(
    surfaceId: surface.id,
    routeId: surface.routeId,
    clientPageId: clientPageId,
    actor: const CloudOperationActorContext(
      accountId: businessFixtureCurrentUserId,
      personaId: businessFixtureCurrentUserId,
    ),
    idempotencyKey: idempotencyKey,
  );
}

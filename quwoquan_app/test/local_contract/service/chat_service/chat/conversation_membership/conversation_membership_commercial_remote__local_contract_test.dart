// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/commercial-remote-only-message-system/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/spec.md#sit-006
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/chat_dependencies.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/business_contract_fixture_server.dart';

void main() {
  test(
    'conversation membership resolves members from canonical contacts',
    () async {
      final server = await BusinessContractFixtureServer.start();
      addTearDown(server.close);
      final repository = ChatProductionComposition.repository(
        client: server.buildGeneratedClient(),
        invocationContext: _chatContext,
      );

      final contacts = await repository.listContacts(limit: 20);
      final groupMembers = await repository.listMembers(
        conversationId: 'fixture_conv_group',
        limit: 20,
      );
      final contactIds = contacts.items.map((item) => item.userId).toSet();
      expect(
        groupMembers
            .where((member) => !member.isCurrentUser)
            .every((member) => contactIds.contains(member.userId)),
        isTrue,
      );
    },
  );
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

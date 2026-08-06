// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/commercial-remote-only-message-system/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/spec.md#sit-006
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/chat_dependencies.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/business_contract_fixture_server.dart';

void main() {
  test('chat conversation views preserve contacts and message home', () async {
    final server = await BusinessContractFixtureServer.start();
    addTearDown(server.close);
    final repository = ChatProductionComposition.repository(
      client: server.buildGeneratedClient(),
      invocationContext: _chatContext,
    );

    final contacts = await repository.listContacts(limit: 20);
    expect(contacts.items.length, greaterThanOrEqualTo(6));
    expect(
      contacts.items.map((item) => item.userId),
      contains('fixture_user_friend'),
    );
    final contactStates = contacts.items
        .map((item) => item.relationState)
        .toSet();
    expect(contactStates, contains('mutual'));
    expect(contactStates, isNot(contains('not_following')));
    expect(contacts.items.every((item) => item.source.isNotEmpty), isTrue);
    expect(
      contacts.items.every(
        (item) => item.avatarUrl.toLowerCase().startsWith('media/avatar/'),
      ),
      isTrue,
    );

    final messageHome = await repository.listMessageHome(limit: 20);
    expect(messageHome.length, greaterThanOrEqualTo(5));
    expect(
      messageHome.every(
        (row) => row.avatarUrl.toLowerCase().startsWith('media/avatar/'),
      ),
      isTrue,
    );
    expect(messageHome.any((row) => row.mentionUnreadCount > 0), isTrue);

    final contactHomeAll = await repository.listContactHome(
      filter: 'all',
      limit: 50,
    );
    expect(contactHomeAll.where((row) => row.kind == 'user'), isNotEmpty);
    expect(contactHomeAll.where((row) => row.kind == 'circle'), isNotEmpty);
    expect(
      contactHomeAll.every(
        (row) =>
            row.avatarUrl.isEmpty ||
            row.avatarUrl.toLowerCase().startsWith('media/avatar/'),
      ),
      isTrue,
    );

    final contactHomeCircles = await repository.listContactHome(
      filter: 'circle',
      limit: 20,
    );
    expect(contactHomeCircles, isNotEmpty);
    expect(contactHomeCircles.every((row) => row.kind == 'circle'), isTrue);
    expect(
      contactHomeCircles.map((item) => item.id),
      contains('fixture_circle_photo'),
    );

    final funGroups = await repository.listContactHome(
      filter: 'group',
      limit: 20,
    );
    expect(
      funGroups.map((item) => item.conversationId),
      contains('fixture_conv_group'),
    );
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

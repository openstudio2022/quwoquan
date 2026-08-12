/// App 四核心 Remote readback：通过 production Remote ports 准备并回读会话。
library;

import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/di/chat_contacts_rows_dependencies.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/message_home_rows.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/message_home_rows_provider.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/chat_contacts_row.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class PatrolCoreChatProvision {
  const PatrolCoreChatProvision({
    required this.conversationId,
    required this.messageText,
    required this.messageId,
  });

  final String conversationId;
  final String messageText;
  final String messageId;
}

final class PatrolCoreBusinessReadback {
  const PatrolCoreBusinessReadback({
    required this.messageRows,
    required this.contactRows,
  });

  final Map<String, List<MessageHomeRow>> messageRows;
  final Map<ChatContactHomeFilter, List<ChatContactsRow>> contactRows;
}

ProviderContainer patrolMountedContainer() {
  final navigators = find.byType(Navigator).evaluate();
  if (navigators.isEmpty) {
    throw StateError('Patrol core readback requires a mounted Navigator');
  }
  return ProviderScope.containerOf(navigators.first);
}

AuthSessionState patrolAuthenticatedSession(ProviderContainer container) {
  final session = container.read(authSessionControllerProvider);
  if (!session.isAuthenticated ||
      session.ownerId.trim().isEmpty ||
      session.activePersonaId.trim().isEmpty) {
    throw StateError(
      'Patrol core readback requires an authenticated owner/persona session',
    );
  }
  return session;
}

Future<PatrolCoreChatProvision> provisionPatrolCoreChatConversation(
  PatrolIntegrationTester $,
) async {
  final container = patrolMountedContainer();
  patrolAuthenticatedSession(container);
  final stamp = DateTime.now().toUtc().microsecondsSinceEpoch.toRadixString(16);
  final messageText = '双端核心可用性验证 $stamp';
  final conversations = container.read(chatConversationRepositoryProvider);
  final created = await conversations.createConversation(
    type: 'group',
    title: '双端核心可用性验证',
    maxGroupSize: 500,
    idempotencyKey: 'patrol-core-chat-$stamp',
  );
  final conversationId = created.conversationId.trim();
  if (conversationId.isEmpty) {
    throw StateError('createConversation returned empty conversationId');
  }
  final sent = await container
      .read(chatMessageCommandWriterProvider)
      .sendMessage(
        ChatSendMessageCommand(
          conversationId: conversationId,
          type: 'text',
          content: messageText,
          clientMsgId: 'patrol-core-msg-$stamp',
        ),
      );
  final messageId = sent.messageId.trim();
  if (messageId.isEmpty) {
    throw StateError('sendMessage returned empty messageId');
  }
  for (final filter in messageHomeFilters) {
    container.invalidate(messageHomeRowsStateProvider(filter));
  }
  await $.pump();
  await $.pump(const Duration(milliseconds: 300));
  return PatrolCoreChatProvision(
    conversationId: conversationId,
    messageText: messageText,
    messageId: messageId,
  );
}

Future<PatrolCoreBusinessReadback> readPatrolCoreBusinessReadback(
  PatrolIntegrationTester $,
) async {
  final container = patrolMountedContainer();
  patrolAuthenticatedSession(container);
  const messageFilters = <String>['all', 'direct', 'group'];
  const contactFilters = <ChatContactHomeFilter>[
    ChatContactHomeFilter.all,
    ChatContactHomeFilter.mutual,
    ChatContactHomeFilter.circle,
    ChatContactHomeFilter.group,
  ];
  for (final filter in messageFilters) {
    container.invalidate(messageHomeRowsStateProvider(filter));
  }
  for (final filter in contactFilters) {
    container.invalidate(chatContactsRowsForSubTabProvider(filter));
  }
  await $.pump();
  final messageRows = <String, List<MessageHomeRow>>{};
  for (final filter in messageFilters) {
    final snapshot = await container.read(
      messageHomeRowsStateProvider(filter).future,
    );
    messageRows[filter] = snapshot.rows;
  }
  final contactRows = <ChatContactHomeFilter, List<ChatContactsRow>>{};
  for (final filter in contactFilters) {
    contactRows[filter] = await container.read(
      chatContactsRowsForSubTabProvider(filter).future,
    );
  }
  return PatrolCoreBusinessReadback(
    messageRows: messageRows,
    contactRows: contactRows,
  );
}

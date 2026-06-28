import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_member_dto.g.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/core/media/avatar_image_url.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_message_provider.dart';
import 'package:quwoquan_app/ui/chat/providers/conversation_members_provider.dart';
import 'package:quwoquan_app/ui/chat/providers/group_home_provider.dart';

const _conversationId = 'conv_002';
const _newMemberId = 'user_roster_contract_new';

void main() {
  group('local_contract.chat.member_roster', () {
    test('listMembers 与 chatMessageProvider sender 快照一致', () async {
      final container = ProviderContainer(
        overrides: [
          chatRepositoryProvider.overrideWithValue(MockChatRepository()),
          currentUserIdProvider.overrideWithValue('user_001'),
        ],
      );
      addTearDown(container.dispose);

      final members = await container
          .read(chatRepositoryProvider)
          .listMembers(conversationId: _conversationId, limit: 200);
      final memberByUserId = {
        for (final member in members)
          if (member.userId.isNotEmpty) member.userId: member,
      };

      final notifier = container.read(
        chatMessageProvider(_conversationId).notifier,
      );
      await notifier.loadMessages();
      final messages = container
          .read(chatMessageProvider(_conversationId))
          .messages;

      for (final message in messages) {
        if (message.senderId.isEmpty || message.type == 'system') {
          continue;
        }
        final member = memberByUserId[message.senderId];
        if (member == null) {
          continue;
        }
        expect(
          message.senderName,
          member.displayName,
          reason: 'senderId=${message.senderId}',
        );
        expect(
          resolveAvatarImageUrl(message.senderAvatar),
          resolveAvatarImageUrl(member.avatarUrl),
          reason: 'senderId=${message.senderId}',
        );
      }
    });

    test('addMembers / removeMember 后 provider 与 repository 人数一致', () async {
      final repo = MockChatRepository();
      final container = ProviderContainer(
        overrides: [
          chatRepositoryProvider.overrideWithValue(repo),
          currentUserIdProvider.overrideWithValue('user_001'),
        ],
      );
      addTearDown(container.dispose);

      final notifier = container.read(
        conversationMembersProvider(_conversationId).notifier,
      );
      await notifier.load();
      final before = container
          .read(conversationMembersProvider(_conversationId))
          .members
          .length;

      await notifier.addMembers([_newMemberId]);
      final afterAdd = container
          .read(conversationMembersProvider(_conversationId))
          .members;
      expect(afterAdd.length, before + 1);
      expect(afterAdd.any((m) => m.userId == _newMemberId), isTrue);

      final repoMembers = await repo.listMembers(conversationId: _conversationId);
      expect(repoMembers.length, afterAdd.length);

      final conversation = await repo.getConversation(_conversationId);
      expect(conversation.memberCount, afterAdd.length);

      await notifier.removeMember(_newMemberId);
      final afterRemove = container
          .read(conversationMembersProvider(_conversationId))
          .members;
      expect(afterRemove.length, before);
      expect(afterRemove.any((m) => m.userId == _newMemberId), isFalse);
    });

    test('invalidate 后 reload 仍与 repository 对齐', () async {
      final repo = MockChatRepository();
      final container = ProviderContainer(
        overrides: [
          chatRepositoryProvider.overrideWithValue(repo),
          currentUserIdProvider.overrideWithValue('user_001'),
        ],
      );
      addTearDown(container.dispose);

      await repo.addMembers(
        conversationId: _conversationId,
        userIds: ['user_roster_invalidate'],
      );

      container.invalidate(conversationMembersProvider(_conversationId));
      container.invalidate(groupHomeProvider(_conversationId));
      final notifier = container.read(
        conversationMembersProvider(_conversationId).notifier,
      );
      await notifier.load();

      final providerCount = container
          .read(conversationMembersProvider(_conversationId))
          .members
          .length;
      final repoCount = (await repo.listMembers(conversationId: _conversationId))
          .length;
      expect(providerCount, repoCount);

      await repo.removeMember(
        conversationId: _conversationId,
        userId: 'user_roster_invalidate',
      );
    });
  });
}

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facets_typed_double.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facet_overrides.dart';
import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_profile_view_data.dart';
import 'package:quwoquan_app/runtime/transport/media/avatar_image_url.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/di/chat_message_application_dependencies.dart';
import 'package:quwoquan_app/runtime/di/conversation_members_provider.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/group_home_provider.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/persona_query.dart';

const _conversationId = 'fixture_conv_group';
const _newMemberId = 'user_roster_contract_new';

/// Roster consistency does not exercise persona-backed local search. Keep that
/// unrelated cloud query outside this suite instead of letting guarded Alpha
/// defines turn it into a real Gateway request.
final class _RosterPersonaQuery implements PersonaQuery {
  const _RosterPersonaQuery();

  @override
  Future<ActivePersonaContextViewData> getActivePersonaContext() {
    throw StateError('persona context is outside the roster contract');
  }

  @override
  Future<PersonaLifecycleGuardViewData> getPersonaLifecycleGuard(
    String personaId,
  ) {
    throw UnimplementedError();
  }

  @override
  Future<PersonaManagementSummaryViewData> getPersonaManagementSummary() {
    throw UnimplementedError();
  }

  @override
  Future<PersonaProfileViewData> getPersonaProfile(String personaId) {
    throw UnimplementedError();
  }

  @override
  Future<List<PersonaManagementItemViewData>> listPersonas() {
    throw UnimplementedError();
  }
}

List<Override> _boundaryOverrides(ChatTestFacets facets) {
  return <Override>[
    ...sealedCloudBoundaryOverrides(),
    ...chatTestRepositoryOverrides(facets: facets),
    personaQueryProvider(
      AppUiSurfaces.appShell,
    ).overrideWithValue(const _RosterPersonaQuery()),
    currentUserIdProvider.overrideWithValue('fixture_user_current'),
  ];
}

void main() {
  group('local_contract.chat.member_roster', () {
    test('listMembers 与 chatMessageProvider sender 快照一致', () async {
      final facets = ChatTestFacets();
      final container = ProviderContainer(
        overrides: _boundaryOverrides(facets),
      );
      addTearDown(container.dispose);

      final members = await container
          .read(chatMemberRepositoryProvider)
          .listMembers(conversationId: _conversationId, limit: 200);
      final memberByUserId = {
        for (final member in members)
          if (member.userId.isNotEmpty) member.userId: member,
      };

      final notifier = container.read(
        chatMessageTimelineControllerProvider(_conversationId),
      );
      await notifier.loadMessages();
      final messages = container
          .read(chatMessageTimelineProvider(_conversationId))
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
      final facets = ChatTestFacets();
      final container = ProviderContainer(
        overrides: _boundaryOverrides(facets),
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

      final repoMembers = await facets.member.listMembers(
        conversationId: _conversationId,
      );
      expect(repoMembers.length, afterAdd.length);

      final conversation = await facets.conversation.getConversation(
        _conversationId,
      );
      expect(conversation.memberCount, afterAdd.length);

      await notifier.removeMember(_newMemberId);
      final afterRemove = container
          .read(conversationMembersProvider(_conversationId))
          .members;
      expect(afterRemove.length, before);
      expect(afterRemove.any((m) => m.userId == _newMemberId), isFalse);
    });

    test('invalidate 后 reload 仍与 repository 对齐', () async {
      final facets = ChatTestFacets();
      final container = ProviderContainer(
        overrides: _boundaryOverrides(facets),
      );
      addTearDown(container.dispose);

      await facets.member.addMembers(
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
      final repoCount = (await facets.member.listMembers(
        conversationId: _conversationId,
      )).length;
      expect(providerCount, repoCount);

      await facets.member.removeMember(
        conversationId: _conversationId,
        userId: 'user_roster_invalidate',
      );
    });

    test(
      'contract group memberCount / listMembers / getGroupHome 一致',
      () async {
        final facets = ChatTestFacets();
        final members = await facets.member.listMembers(
          conversationId: _conversationId,
          limit: 200,
        );
        final conversation = await facets.conversation.getConversation(
          _conversationId,
        );
        final groupHome = await facets.groupAdmin.getGroupHome(_conversationId);

        expect(conversation.memberCount, members.length);
        expect(groupHome.memberCount, members.length);
      },
    );

    test('addMembers 后 contract groupAvatarVersion 递增', () async {
      final facets = ChatTestFacets();
      final before = await facets.conversation.getConversation(_conversationId);
      await facets.member.addMembers(
        conversationId: _conversationId,
        userIds: ['user_group_avatar_version_new'],
      );
      final after = await facets.conversation.getConversation(_conversationId);
      expect(after.memberCount, before.memberCount + 1);
      expect(after.groupAvatarVersion, greaterThan(before.groupAvatarVersion));
    });
  });
}

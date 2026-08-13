// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/group-home-chat-info-contract/spec.md#gwt-001
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/chat_conversation_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/group_home_provider.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facet_overrides.dart';

void main() {
  test('groupHomeProvider 消费 GetGroupHome 云端主页契约', () async {
    final repo = _FakeChatRepository();
    final container = ProviderContainer(
      overrides: chatTestRepositoryOverrides(groupAdmin: repo),
    );
    addTearDown(container.dispose);

    final dto = await container.read(groupHomeProvider('conv_group_01').future);

    expect(repo.requestedConversationIds, <String>['conv_group_01']);
    expect(dto.title, '九寨沟摄影群');
    expect(dto.sourceEntityTitle, '九寨沟');
    expect(dto.sourceCircleTitle, '摄影圈');
    expect(dto.memberCount, 368);
    expect(
      dto.capabilities,
      containsAll(<String>['album', 'file', 'activity']),
    );
  });
}

final class _FakeChatRepository extends Fake
    implements ChatGroupAdminRepository {
  final List<String> requestedConversationIds = <String>[];

  @override
  Future<GroupHome> getGroupHome(String conversationId) async {
    requestedConversationIds.add(conversationId);
    return GroupHome(
      conversationId: conversationId,
      title: '九寨沟摄影群',
      avatarUrl: 'media/avatar/s/archived-avatar/group/$conversationId/v1.png',
      groupAvatarVersion: 1,
      circleId: '',
      circleGroupId: '',
      gatheringId: '',
      entityId: '',
      sourceEntityTitle: '九寨沟',
      sourceCircleTitle: '摄影圈',
      memberCount: 368,
      announcement: '周末外拍集合',
      capabilities: const <String>['album', 'file', 'activity', 'members'],
      originType: 'ad_hoc_group',
      accessMode: ConversationAccessMode.active,
      postingPolicy: ConversationPostingPolicy.memberChat,
      canManageMembers: true,
      canDissolve: true,
    );
  }
}

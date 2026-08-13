import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/chat_conversation_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/chat_conversation_view_data.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_membership/application/public/chat_member_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/chat_announcement_page.dart';

import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facet_overrides.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_seed_refs.dart';

List<Override> _overrides({
  ChatMemberRepository? member,
  ChatGroupAdminRepository? groupAdmin,
}) => [
  ...chatTestRepositoryOverrides(member: member, groupAdmin: groupAdmin),
  currentUserIdProvider.overrideWithValue(chatCurrentUserProfileId()),
];

Widget _scopedApp({
  ChatMemberRepository? member,
  ChatGroupAdminRepository? groupAdmin,
}) {
  return ProviderScope(
    overrides: _overrides(member: member, groupAdmin: groupAdmin),
    child: MaterialApp.router(
      routerConfig: GoRouter(
        initialLocation: '/chat/fixture_conv_group/announcement',
        routes: [
          GoRoute(
            path: '/chat/:id/announcement',
            builder: (_, state) => Scaffold(
              body: ChatAnnouncementPage(
                conversationId:
                    state.pathParameters['id'] ?? 'fixture_conv_group',
              ),
            ),
          ),
          GoRoute(
            path: '/chat/:id/settings',
            builder: (_, _) => const SizedBox(),
          ),
        ],
      ),
    ),
  );
}

void main() {
  group('ChatAnnouncementPage — 群公告页契约', () {
    testWidgets('owner 可见编辑器与发布按钮', (tester) async {
      await tester.pumpWidget(_scopedApp());
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(
        find.byKey(const ValueKey('chat_announcement_editor')),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey('chat_announcement_publish_button')),
        findsOneWidget,
      );
    });

    testWidgets('发布公告经确认后调用 UpdateAnnouncement 契约', (tester) async {
      final repo = _RecordingAnnouncementRepository();
      await tester.pumpWidget(_scopedApp(groupAdmin: repo));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      await tester.enterText(
        find.byKey(const ValueKey('chat_announcement_editor')),
        '周六线下面基，老地方集合',
      );
      await tester.tap(
        find.byKey(const ValueKey('chat_announcement_publish_button')),
      );
      await tester.pumpAndSettle();
      expect(
        find.text(ChatText.groupAnnouncementPublishConfirm),
        findsOneWidget,
      );

      await tester.tap(find.text(ChatText.groupAnnouncementPublish).last);
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(repo.published, contains(('fixture_conv_group', '周六线下面基，老地方集合')));
      // 消化发布成功 toast 的自动消失 timer。
      await tester.pump(const Duration(seconds: 4));
    });

    testWidgets('普通成员只读呈现且不可见发布按钮', (tester) async {
      await tester.pumpWidget(
        _scopedApp(member: _MemberRoleAnnouncementRepository()),
      );
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(
        find.byKey(const ValueKey('chat_announcement_publish_button')),
        findsNothing,
      );
      expect(
        find.byKey(const ValueKey('chat_announcement_readonly_body')),
        findsOneWidget,
      );
      expect(find.text(ChatText.groupAnnouncementViewOnlyNote), findsOneWidget);
    });

    testWidgets('取消确认不调用发布契约', (tester) async {
      final repo = _RecordingAnnouncementRepository();
      await tester.pumpWidget(_scopedApp(groupAdmin: repo));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      await tester.enterText(
        find.byKey(const ValueKey('chat_announcement_editor')),
        '不该发布的内容',
      );
      await tester.tap(
        find.byKey(const ValueKey('chat_announcement_publish_button')),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text(FoundationText.cancel));
      await tester.pumpAndSettle();

      expect(repo.published, isEmpty);
    });
  });
}

class _RecordingAnnouncementRepository extends Fake
    implements ChatGroupAdminRepository {
  final List<(String, String)> published = <(String, String)>[];

  @override
  Future<void> updateAnnouncement(
    String conversationId,
    String announcement, {
    String? idempotencyKey,
  }) async {
    published.add((conversationId, announcement));
  }

  /// 成员角色加载与公告水合都经同一 admin repository；Fake 缺任一读面都会
  /// 让页面落入错误/只读分支，编辑器不渲染。
  @override
  Future<ChatGroupSettingsViewData> getGroupSettings(
    String conversationId,
  ) async => const ChatGroupSettingsViewData(
    nameEditableByAdminOnly: false,
    conversationType: 'group',
    circleId: '',
    circleGroupId: '',
  );

  @override
  Future<GroupHome> getGroupHome(String conversationId) async => GroupHome(
    conversationId: conversationId,
    title: '产品共创群',
    avatarUrl: '',
    groupAvatarVersion: 0,
    circleId: '',
    circleGroupId: '',
    gatheringId: '',
    entityId: '',
    sourceEntityTitle: '',
    sourceCircleTitle: '',
    memberCount: 3,
    announcement: '',
    capabilities: const <String>[],
    originType: 'group',
    accessMode: ConversationAccessMode.active,
    postingPolicy: ConversationPostingPolicy.memberChat,
    canManageMembers: true,
    canDissolve: false,
  );
}

/// 当前用户为普通成员：公告只读。
class _MemberRoleAnnouncementRepository extends Fake
    implements ChatMemberRepository {
  @override
  Future<List<ConversationMemberListRow>> listMembers({
    required String conversationId,
    String? cursor,
    int limit = 20,
    String? role,
    MemberListSort? sort,
  }) async {
    return [
      ConversationMemberListRow(
        userId: chatCurrentUserProfileId(),
        userHandle: chatCurrentUserProfileId(),
        displayName: '我',
        avatarUrl: '',
        role: 'member',
        memberType: 'user',
        joinedAt: null,
        isCurrentUser: true,
      ),
      ConversationMemberListRow(
        userId: 'fixture_user_other_owner',
        userHandle: 'fixture_user_other_owner',
        displayName: '群主',
        avatarUrl: '',
        role: 'owner',
        memberType: 'user',
        joinedAt: null,
        isCurrentUser: false,
      ),
    ];
  }
}

/// 群空间承载面入口契约（聊天信息页 = 群空间首页，L1 DEC-002）。
///
/// 覆盖：活动群（gatheringId 绑定）在能力宫格展示「活动」格并直达
/// Gathering Board 路由；普通群不出现活动格；成员网格提供成员搜索入口格
/// 并直达成员搜索路由（消灭 chatMemberSearch/gatheringBoard 两个无入口路由）。
///
/// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/spec.md#sit-004.t3
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/chat_conversation_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/chat_settings_page.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';

import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facet_overrides.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_seed_refs.dart';

final class _GatheringGroupAdminRepository extends Fake
    implements ChatGroupAdminRepository {
  _GatheringGroupAdminRepository({required this.gatheringId});

  final String gatheringId;

  @override
  Future<GroupHome> getGroupHome(String conversationId) async => GroupHome(
    conversationId: conversationId,
    title: '黄龙同行活动群',
    avatarUrl: '',
    groupAvatarVersion: 0,
    circleId: '',
    circleGroupId: '',
    gatheringId: gatheringId,
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

Widget _scopedSettings({required String gatheringId}) {
  return ProviderScope(
    overrides: [
      ...chatTestRepositoryOverrides(
        groupAdmin: _GatheringGroupAdminRepository(gatheringId: gatheringId),
      ),
      currentUserIdProvider.overrideWithValue(chatCurrentUserProfileId()),
    ],
    child: MaterialApp.router(
      routerConfig: GoRouter(
        initialLocation: '/chat/fixture_conv_group/settings',
        routes: [
          GoRoute(
            path: '/chat/:id/settings',
            builder: (_, state) => Scaffold(
              body: ChatSettingsPage(
                conversationId:
                    state.pathParameters['id'] ?? 'fixture_conv_group',
              ),
            ),
          ),
          GoRoute(
            path: '/chat/:id/board',
            builder: (_, _) =>
                const SizedBox(key: ValueKey('gathering-board-page')),
          ),
          GoRoute(
            path: '/chat/:id/member-search',
            builder: (_, _) =>
                const SizedBox(key: ValueKey('member-search-page')),
          ),
          GoRoute(path: '/chat/:id', builder: (_, _) => const SizedBox()),
        ],
      ),
    ),
  );
}

void _suppressImageErrors() {
  final original = FlutterError.onError;
  FlutterError.onError = (FlutterErrorDetails details) {
    final msg = details.exception.toString();
    if (msg.contains('HTTP request failed') ||
        msg.contains('NetworkImageLoadException')) {
      return;
    }
    original?.call(details);
  };
}

void main() {
  testWidgets('活动群能力宫格展示活动格并直达 Gathering Board', (tester) async {
    _suppressImageErrors();
    await tester.pumpWidget(_scopedSettings(gatheringId: 'gathering_1'));
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));

    final boardEntry = find.byKey(
      const ValueKey<String>('chat_settings_board_entry'),
    );
    expect(boardEntry, findsOneWidget);
    expect(find.text(ChatText.groupCapabilityActivity), findsOneWidget);

    await tester.tap(boardEntry);
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey('gathering-board-page')),
      findsOneWidget,
      reason: '活动格必须直达 Board，不得是无承接入口',
    );
  });

  testWidgets('普通群不展示活动格', (tester) async {
    _suppressImageErrors();
    await tester.pumpWidget(_scopedSettings(gatheringId: ''));
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));

    expect(
      find.byKey(const ValueKey<String>('chat_settings_board_entry')),
      findsNothing,
    );
    expect(find.text(ChatText.groupCapabilityActivity), findsNothing);
  });

  testWidgets('成员网格搜索入口直达成员搜索页', (tester) async {
    _suppressImageErrors();
    await tester.pumpWidget(_scopedSettings(gatheringId: ''));
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));

    final searchEntry = find.byKey(
      const ValueKey('chat_settings_member_search_entry'),
    );
    expect(searchEntry, findsOneWidget);
    await tester.ensureVisible(searchEntry);
    await tester.tap(searchEntry);
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('member-search-page')), findsOneWidget);
  });
}

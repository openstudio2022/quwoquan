import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_contact_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_created_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/pages/start_group_chat_page.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_contacts_rows_provider.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_inbox_provider.dart';
import '../../../common/chat/chat_mock_seed_refs.dart';

void _suppressImageErrors() {
  final original = FlutterError.onError;
  FlutterError.onError = (FlutterErrorDetails details) {
    final message = details.exception.toString();
    if (message.contains('HTTP request failed') ||
        message.contains('NetworkImageLoadException')) {
      return;
    }
    original?.call(details);
  };
}

Future<void> _pumpStartGroupChatPage(
  WidgetTester tester, {
  required ProviderContainer container,
  String? conversationId,
}) async {
  await tester.pumpWidget(
    UncontrolledProviderScope(
      container: container,
      child: MaterialApp.router(
        routerConfig: GoRouter(
          initialLocation: '/chat/start-group',
          routes: [
            GoRoute(
              path: '/chat/start-group',
              builder: (context, state) => StartGroupChatPage(
                conversationId: conversationId,
                onBack: () {},
              ),
            ),
            GoRoute(
              path: '/chat/:id',
              builder: (_, state) =>
                  Scaffold(body: Text('chat:${state.pathParameters['id']}')),
            ),
          ],
        ),
      ),
    ),
  );
  await tester.pump();
  await tester.pump(const Duration(seconds: 1));
}

class _RecordingAnalyticsService extends AnalyticsService {
  _RecordingAnalyticsService() : super.forTesting();

  final List<AnalyticsEvent> events = <AnalyticsEvent>[];

  @override
  Future<void> trackEvent(AnalyticsEvent event) async {
    events.add(event);
  }

  Iterable<AnalyticsEvent> pageLifecycleEvents(String phase) => events.where(
    (event) =>
        event.eventName == 'page_lifecycle_state' &&
        event.properties['phase'] == phase,
  );
}

ProviderContainer _buildContainer(
  MockChatRepository repository, {
  AnalyticsService? analytics,
}) {
  final container = ProviderContainer(
    overrides: [
      chatRepositoryProvider.overrideWithValue(repository),
      userProfileRepositoryProvider.overrideWithValue(
        const MockUserProfileRepository(),
      ),
      if (analytics != null) analyticsProvider.overrideWithValue(analytics),
    ],
  );
  addTearDown(container.dispose);
  return container;
}

Map<String, dynamic> _groupConversation(
  String id,
  String title, {
  String avatarUrl = '',
  int memberCount = 2,
}) {
  final now = DateTime.utc(2026, 1, 1).toIso8601String();
  return <String, dynamic>{
    '_id': id,
    'id': id,
    'conversationId': id,
    'type': 'group',
    'title': title,
    'avatarUrl': avatarUrl,
    'creatorId': chatCurrentUserProfileId(),
    'maxSeq': 0,
    'memberCount': memberCount,
    'maxGroupSize': 500,
    'receiptEnabled': true,
    'lastMessagePreview': '',
    'lastMessageTime': now,
    'messageCount': 0,
    'status': 'active',
    'createdAt': now,
    'updatedAt': now,
  };
}

Map<String, dynamic> _member(
  String userId, {
  required int order,
  String role = 'member',
  bool isCurrentUser = false,
  String? avatarUrl,
}) {
  return <String, dynamic>{
    'userId': userId,
    'displayName': chatDisplayNameFor(userId),
    'avatarUrl': avatarUrl ?? chatAvatarUrlFor(userId),
    'role': role,
    'isCurrentUser': isCurrentUser,
    'joinedAt': DateTime.utc(
      2026,
      1,
      1,
    ).add(Duration(seconds: order)).toIso8601String(),
  };
}

/// 模拟服务端互关/拉黑/上限校验失败：createConversation 抛出携带结构化
/// userMessage 的 CloudException，其余能力沿用 MockChatRepository。
class _RejectingCreateChatRepository extends MockChatRepository {
  _RejectingCreateChatRepository(this._error);

  final CloudException _error;

  @override
  Future<ChatConversationCreatedDto> createConversation({
    required String type,
    String? title,
    String? circleId,
    String? circleGroupId,
    String? originType,
    String? bindingType,
    String? lifecyclePolicy,
    int? maxGroupSize,
    List<String>? initialMemberIds,
  }) async {
    throw _error;
  }
}

class _SeededGroupCandidatesChatRepository extends MockChatRepository {
  _SeededGroupCandidatesChatRepository(this._rows);

  final List<ChatContactRowDto> _rows;

  @override
  Future<List<ChatContactRowDto>> listGroupCandidates({
    String? conversationId,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return _rows.take(limit).toList(growable: false);
  }
}

void main() {
  testWidgets('发起群聊使用设置页同源壳且空/坏头像显示默认图标兜底', (tester) async {
    _suppressImageErrors();

    final repository = _SeededGroupCandidatesChatRepository(<ChatContactRowDto>[
      ChatContactRowDto(
        userId: 'user_empty_avatar',
        displayName: '空头像联系人',
        avatarUrl: '',
        relationState: 'mutual',
      ),
      ChatContactRowDto(
        userId: 'user_broken_avatar',
        displayName: '坏头像联系人',
        avatarUrl: 'https://avatar.invalid.test/broken.png',
        relationState: 'mutual',
      ),
    ]);
    final container = _buildContainer(repository);
    await _pumpStartGroupChatPage(tester, container: container);

    expect(find.byType(SettingsInsetMemberPickerPageScaffold), findsOneWidget);
    expect(find.text('空头像联系人'), findsOneWidget);
    expect(find.text('坏头像联系人'), findsOneWidget);
    expect(find.byIcon(CupertinoIcons.person_fill), findsAtLeastNWidgets(2));

    await tester.tap(find.byIcon(CupertinoIcons.circle).first);
    await tester.pumpAndSettle();

    expect(
      find.text(UITextConstants.startGroupChatSelectedCount(1)),
      findsOneWidget,
    );
    expect(find.byIcon(CupertinoIcons.person_fill), findsAtLeastNWidgets(3));
  });

  testWidgets('发起群聊失败时透出服务端结构化提示而非吞错', (tester) async {
    _suppressImageErrors();

    const serverMessage = '只能邀请互相关注的好友加入群聊';
    final repository = _RejectingCreateChatRepository(
      CloudException(
        type: CloudErrorType.forbidden,
        message: 'forbidden',
        statusCode: 403,
        code: 'CHAT.USER.group_member_not_mutual',
        userMessage: serverMessage,
      ),
    );
    final container = _buildContainer(repository);
    await _pumpStartGroupChatPage(tester, container: container);

    await tester.tap(find.byIcon(CupertinoIcons.circle).first);
    await tester.pumpAndSettle();
    await tester.tap(find.text(UITextConstants.startGroupChatActionCount(1)));
    await tester.pumpAndSettle();

    // 标题为发起群聊语境，正文透出服务端 userMessage（端云错误链路闭合）
    expect(
      find.text(UITextConstants.startGroupChatCreateIncompleteTitle),
      findsOneWidget,
    );
    expect(find.text(serverMessage), findsOneWidget);
    // 创建失败不应跳转到新会话路由
    expect(find.textContaining('chat:conv_new_'), findsNothing);
  });

  testWidgets('发起群聊曝光/加载/提交成功均上报页面观测事件', (tester) async {
    _suppressImageErrors();

    final analytics = _RecordingAnalyticsService();
    final container = _buildContainer(
      MockChatRepository(),
      analytics: analytics,
    );
    await _pumpStartGroupChatPage(tester, container: container);

    // 曝光 + 候选加载成功（itemCount 透出，App→Observability 链路接通）
    expect(analytics.pageLifecycleEvents('enter'), isNotEmpty);
    final loaded = analytics.pageLifecycleEvents('onlineSuccess');
    expect(loaded, isNotEmpty);
    expect(loaded.first.properties['itemCount'], greaterThan(0));

    await tester.tap(find.byIcon(CupertinoIcons.circle).first);
    await tester.pumpAndSettle();
    await tester.tap(find.text(UITextConstants.startGroupChatActionCount(1)));
    await tester.pumpAndSettle();

    // 转化成功事件，携带本次群成员数
    final submitted = analytics.pageLifecycleEvents('submitSuccess');
    expect(submitted, isNotEmpty);
    expect(submitted.first.properties['itemCount'], 1);
    await tester.pump(const Duration(seconds: 3));
  });

  testWidgets('发起群聊失败时观测事件携带服务端错误码（错误码到埋点同源）', (tester) async {
    _suppressImageErrors();

    final analytics = _RecordingAnalyticsService();
    final repository = _RejectingCreateChatRepository(
      CloudException(
        type: CloudErrorType.forbidden,
        message: 'forbidden',
        statusCode: 403,
        code: 'CHAT.USER.group_member_not_mutual',
        userMessage: '只能邀请互相关注的好友加入群聊',
      ),
    );
    final container = _buildContainer(repository, analytics: analytics);
    await _pumpStartGroupChatPage(tester, container: container);

    await tester.tap(find.byIcon(CupertinoIcons.circle).first);
    await tester.pumpAndSettle();
    await tester.tap(find.text(UITextConstants.startGroupChatActionCount(1)));
    await tester.pumpAndSettle();

    final failed = analytics.pageLifecycleEvents('submitFailure');
    expect(failed, isNotEmpty);
    expect(failed.first.properties['sourceCode'], 'CHAT.USER.group_member_not_mutual');
  });

  testWidgets('选中联系人后可提交并跳转到新会话', (tester) async {
    _suppressImageErrors();

    final container = _buildContainer(MockChatRepository());
    await _pumpStartGroupChatPage(tester, container: container);

    expect(find.byType(StartGroupChatPage), findsOneWidget);
    expect(
      find.text(UITextConstants.startGroupChatActionCount(1)),
      findsNothing,
    );

    await tester.tap(find.byIcon(CupertinoIcons.circle).first);
    await tester.pumpAndSettle();

    expect(
      find.text(UITextConstants.startGroupChatActionCount(1)),
      findsOneWidget,
    );

    await tester.tap(find.text(UITextConstants.startGroupChatActionCount(1)));
    await tester.pumpAndSettle();

    expect(find.textContaining('chat:conv_new_'), findsOneWidget);
    await tester.pump(const Duration(seconds: 3));
  });

  testWidgets('添加成员向导只展示服务端过滤后的候选成员', (tester) async {
    _suppressImageErrors();

    final repository = MockChatRepository(
      seedConversations: <Map<String, dynamic>>[
        _groupConversation('conv_existing', '当前群'),
        _groupConversation('conv_source', '候选群'),
      ],
      seedMembers: <String, List<Map<String, dynamic>>>{
        'conv_existing': <Map<String, dynamic>>[
          _member(
            chatCurrentUserProfileId(),
            order: 0,
            role: 'owner',
            isCurrentUser: true,
          ),
          _member('user_002', order: 1),
        ],
        'conv_source': <Map<String, dynamic>>[
          _member(
            chatCurrentUserProfileId(),
            order: 0,
            role: 'owner',
            isCurrentUser: true,
          ),
          _member('user_002', order: 1),
          _member('user_003', order: 2),
        ],
      },
    );
    final container = _buildContainer(repository);
    await _pumpStartGroupChatPage(
      tester,
      container: container,
      conversationId: 'conv_existing',
    );

    expect(find.text('李明'), findsNothing);
    expect(find.text('张华'), findsOneWidget);
    expect(find.text('李青'), findsOneWidget);

    await tester.ensureVisible(find.text('张华').last);
    await tester.pumpAndSettle();
    await tester.tap(
      find
          .ancestor(
            of: find.text('张华').last,
            matching: find.byType(CupertinoButton),
          )
          .last,
    );
    await tester.pumpAndSettle();

    expect(find.text('${UITextConstants.addMember}（1）'), findsOneWidget);
  });

  testWidgets('建群聊成功后同时刷新消息列表与群聊列表', (tester) async {
    _suppressImageErrors();

    final container = _buildContainer(MockChatRepository());
    final keepAlive = container.listen(chatInboxListProvider, (_, _) {});
    addTearDown(keepAlive.close);
    await _pumpStartGroupChatPage(tester, container: container);

    await container.read(chatInboxListProvider.notifier).refresh();
    final beforeInboxIds = container
        .read(chatInboxListProvider)
        .items
        .map((item) => item.id)
        .toSet();
    final beforeFunGroups = await container.read(
      chatContactsRowsForSubTabProvider(
        UITextConstants.contactsTabGroups,
      ).future,
    );

    await tester.tap(find.byIcon(CupertinoIcons.circle).first);
    await tester.pumpAndSettle();
    await tester.tap(find.text(UITextConstants.startGroupChatActionCount(1)));
    await tester.pumpAndSettle();

    final inboxItems = container.read(chatInboxListProvider).items;
    expect(
      inboxItems.any(
        (item) =>
            item.id.startsWith('conv_new_') &&
            !beforeInboxIds.contains(item.id),
      ),
      isTrue,
    );
    final afterFunGroups = await container.read(
      chatContactsRowsForSubTabProvider(
        UITextConstants.contactsTabGroups,
      ).future,
    );
    expect(afterFunGroups.length, greaterThanOrEqualTo(beforeFunGroups.length));
    expect(
      afterFunGroups.any(
        (row) => (row.conversationId ?? '').startsWith('conv_new_'),
      ),
      isTrue,
    );
    await tester.pump(const Duration(seconds: 3));
    await tester.pumpAndSettle();
  });
}

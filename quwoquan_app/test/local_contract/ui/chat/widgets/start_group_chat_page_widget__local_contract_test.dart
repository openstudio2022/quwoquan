import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_contact_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_created_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/selectable_group_conversation_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository_api.dart';
import '../../../../support/cloud_services/chat_repository_mock.dart';
import 'package:quwoquan_app/core/models/start_group_chat_route_extra.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/pages/start_group_chat_page.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_contacts_rows_provider.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_inbox_provider.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';
import '../../../../support/runtime_failure_fixtures.dart';
import '../../../../support/recording_app_telemetry_recorder.dart';
import '../../../../support/cloud_services/repository_mock_reexports.dart';

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
  StartGroupChatRouteExtra? routeExtra,
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
                routeExtra: routeExtra,
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
  RecordingAppTelemetryRecorder? telemetryRecorder,
}) {
  final container = ProviderContainer(
    retry: (_, _) => null,
    overrides: [
      chatRepositoryCompositionProvider.overrideWithValue(repository),
      profileQueryProvider.overrideWith(
        (ref, surface) => const MockUserProfileRepository(),
      ),
      if (analytics != null) analyticsProvider.overrideWithValue(analytics),
      if (telemetryRecorder != null)
        appTelemetryReporterProvider.overrideWithValue(telemetryRecorder),
    ],
  );
  addTearDown(container.dispose);
  return container;
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

/// 确定性「从群聊中选择」数据源：图四群列表与图五群成员均由测试给定，
/// 用于稳定校验返回路径、long title 无 overflow 等 UI 契约。
class _SelectableGroupChatRepository extends MockChatRepository {
  _SelectableGroupChatRepository({
    required this.groups,
    required this.membersByConversation,
  });

  final List<SelectableGroupConversationRowDto> groups;
  final Map<String, List<ChatContactRowDto>> membersByConversation;

  @override
  Future<List<SelectableGroupConversationRowDto>>
  listSelectableGroupConversations({
    String? query,
    ChatSelectableGroupSource source = ChatSelectableGroupSource.all,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return groups
        .where(
          (row) =>
              source == ChatSelectableGroupSource.all ||
              (source == ChatSelectableGroupSource.group &&
                  row.circleId.isEmpty) ||
              (source == ChatSelectableGroupSource.circle &&
                  row.circleId.isNotEmpty),
        )
        .take(limit)
        .toList(growable: false);
  }

  @override
  Future<List<ChatContactRowDto>> listSelectableGroupContactMembers({
    required String conversationId,
    String? query,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return (membersByConversation[conversationId] ??
            const <ChatContactRowDto>[])
        .take(limit)
        .toList(growable: false);
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

    expect(find.text(ChatText.startGroupChatSelectedCount(1)), findsOneWidget);
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
        runtimeFailure: testRuntimeFailure(
          code: 'CHAT.USER.group_member_not_mutual',
          kind: RuntimeFailureKind.permission,
        ),
      ),
    );
    final container = _buildContainer(repository);
    await _pumpStartGroupChatPage(tester, container: container);

    await tester.tap(find.byIcon(CupertinoIcons.circle).first);
    await tester.pumpAndSettle();
    await tester.tap(find.text(ChatText.startGroupChatActionCount(1)));
    await tester.pumpAndSettle();

    // 标题为发起群聊语境，正文透出服务端 userMessage（端云错误链路闭合）
    expect(
      find.text(ChatText.startGroupChatCreateIncompleteTitle),
      findsOneWidget,
    );
    expect(find.text(serverMessage), findsOneWidget);
    // 创建失败不应跳转到新会话路由
    expect(find.textContaining('chat:fixture_conv_created_'), findsNothing);
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
    await tester.tap(find.text(ChatText.startGroupChatActionCount(1)));
    await tester.pumpAndSettle();

    // 转化成功事件，携带本次群成员数
    final submitted = analytics.pageLifecycleEvents('submitSuccess');
    expect(submitted, isNotEmpty);
    expect(submitted.first.properties['itemCount'], 1);
    await tester.pump(const Duration(seconds: 3));
  });

  testWidgets('交集结伴入口展示上下文并将 target/source 写入 journey 事件', (tester) async {
    _suppressImageErrors();

    final ops = RecordingAppTelemetryRecorder();
    final container = _buildContainer(
      MockChatRepository(),
      telemetryRecorder: ops,
    );
    const extra = StartGroupChatRouteExtra(
      actionKey: 'start_companion',
      actionLabel: '发起结伴',
      targetObjectId: 'fixture_homepage_travel_photo_west_lake',
      targetObjectKind: 'place',
      intersectionId: 'ix_wishlist',
      dimension: 'location',
      intersectionClass: 'fact',
      sourceRef: 'coWishlistedEntity',
      evidenceId: 'ev_wishlist_1',
    );

    await _pumpStartGroupChatPage(
      tester,
      container: container,
      routeExtra: extra,
    );

    expect(
      find.byKey(const ValueKey<String>('start-group-companion-context-card')),
      findsOneWidget,
    );
    expect(
      find.text(ChatText.startGroupChatCompanionContextTitle),
      findsOneWidget,
    );
    await tester.pumpAndSettle();
    final enterEvents = ops.recorded
        .where((event) => event.action == 'companion_context_enter')
        .toList(growable: false);
    expect(enterEvents, isNotEmpty);
    expect(enterEvents.last.extensions['journey'], 'start_group_chat');
    expect(enterEvents.last.extensions.containsKey('targetObjectId'), isFalse);

    await tester.tap(find.byIcon(CupertinoIcons.circle).first);
    await tester.pumpAndSettle();
    await tester.tap(find.text(ChatText.startGroupChatActionCount(1)));
    await tester.pumpAndSettle();

    final createEvents = ops.recorded
        .where((event) => event.action == 'create_success')
        .toList(growable: false);
    expect(createEvents, isNotEmpty);
    expect(createEvents.last.extensions['journey'], 'start_group_chat');
    expect(
      createEvents.last.extensions.containsKey('intersectionEvidenceId'),
      isFalse,
    );
    await tester.pump(const Duration(seconds: 3));
    await tester.pumpAndSettle();
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
        runtimeFailure: testRuntimeFailure(
          code: 'CHAT.USER.group_member_not_mutual',
          kind: RuntimeFailureKind.permission,
        ),
      ),
    );
    final container = _buildContainer(repository, analytics: analytics);
    await _pumpStartGroupChatPage(tester, container: container);

    await tester.tap(find.byIcon(CupertinoIcons.circle).first);
    await tester.pumpAndSettle();
    await tester.tap(find.text(ChatText.startGroupChatActionCount(1)));
    await tester.pumpAndSettle();

    final failed = analytics.pageLifecycleEvents('submitFailure');
    expect(failed, isNotEmpty);
    expect(
      failed.first.properties['sourceCode'],
      'CHAT.USER.group_member_not_mutual',
    );
  });

  testWidgets('选中联系人后可提交并跳转到新会话', (tester) async {
    _suppressImageErrors();

    final container = _buildContainer(MockChatRepository());
    await _pumpStartGroupChatPage(tester, container: container);

    expect(find.byType(StartGroupChatPage), findsOneWidget);
    expect(find.text(ChatText.startGroupChatActionCount(1)), findsNothing);

    await tester.tap(find.byIcon(CupertinoIcons.circle).first);
    await tester.pumpAndSettle();

    expect(find.text(ChatText.startGroupChatActionCount(1)), findsOneWidget);

    await tester.tap(find.text(ChatText.startGroupChatActionCount(1)));
    await tester.pumpAndSettle();

    expect(find.textContaining('chat:fixture_conv_created_'), findsOneWidget);
    await tester.pump(const Duration(seconds: 3));
  });

  testWidgets('添加成员向导只展示服务端过滤后的候选成员', (tester) async {
    _suppressImageErrors();

    final repository = _SeededGroupCandidatesChatRepository(<ChatContactRowDto>[
      ChatContactRowDto(
        userId: 'user_003',
        displayName: '张华',
        relationState: 'mutual',
        source: 'mutual',
      ),
      ChatContactRowDto(
        userId: 'user_004',
        displayName: '李青',
        relationState: 'mutual',
        source: 'mutual',
      ),
    ]);
    final container = _buildContainer(repository);
    await _pumpStartGroupChatPage(
      tester,
      container: container,
      conversationId: 'conv_existing',
    );

    // 已在群内的成员（李明 = user_002）经服务端过滤后不应出现在候选列表。
    expect(find.text('李明'), findsNothing);

    // 联系人样式行更高（头像 52），候选较多时尾部成员需滚动进入视口后才被构建。
    Future<void> scrollUntilFound(Finder target) async {
      for (var i = 0; i < 30; i++) {
        if (tester.any(target)) {
          return;
        }
        await tester.drag(find.byType(ListView).first, const Offset(0, -320));
        await tester.pumpAndSettle();
      }
    }

    await scrollUntilFound(find.text('张华'));
    expect(find.text('张华'), findsOneWidget);

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

    expect(find.text('${ChatText.addMember}（1）'), findsOneWidget);

    // 选中后再滚动校验尾部候选李青仍可进入视口。
    await scrollUntilFound(find.text('李青'));
    expect(find.text('李青'), findsOneWidget);
  });

  testWidgets('拼音搜索输入 li 命中姓李的联系人且隐藏字母索引', (tester) async {
    _suppressImageErrors();

    final container = _buildContainer(
      _SeededGroupCandidatesChatRepository(<ChatContactRowDto>[
        ChatContactRowDto(
          userId: 'user_li_ming',
          displayName: '李明',
          relationState: 'mutual',
          source: 'mutual',
        ),
        ChatContactRowDto(
          userId: 'user_zhang_hua',
          displayName: '张华',
          relationState: 'mutual',
          source: 'mutual',
        ),
      ]),
    );
    await _pumpStartGroupChatPage(tester, container: container);

    // 默认列表展示全部 mutual 候选。
    expect(find.byIcon(CupertinoIcons.circle), findsWidgets);

    await tester.enterText(find.byType(CupertinoTextField), 'li');
    await tester.pumpAndSettle();

    // 全拼匹配：李明→liming、李想→lixiang 等含 "li"；张华→zhanghua 不含。
    expect(find.text('李明'), findsOneWidget);
    expect(find.text('张华'), findsNothing);

    // 搜索时右侧字母索引应隐藏。
    expect(
      find.byKey(const ValueKey<String>('start-group-letter-index')),
      findsNothing,
    );
  });

  testWidgets('点击已选头像取消选择并提示用户', (tester) async {
    _suppressImageErrors();

    final container = _buildContainer(MockChatRepository());
    await _pumpStartGroupChatPage(tester, container: container);

    // 选中第一个候选。
    await tester.tap(find.byIcon(CupertinoIcons.circle).first);
    await tester.pumpAndSettle();
    expect(find.text(ChatText.startGroupChatSelectedCount(1)), findsOneWidget);

    // 点击选中横向条里的头像 → 取消并 toast。
    final selectedAvatar = find
        .descendant(
          of: find.byKey(const ValueKey<String>('start-group-selected-list')),
          matching: find.byType(GestureDetector),
        )
        .first;
    expect(selectedAvatar, findsOneWidget);
    await tester.tap(selectedAvatar);
    await tester.pumpAndSettle();

    // 取消后已选区块整体隐藏（count 标签不再展示）。
    expect(find.text(ChatText.startGroupChatSelectedCount(1)), findsNothing);
    expect(find.textContaining('已移除'), findsOneWidget);

    // 等待 toast 自动消失计时器结束，避免 pending timer 残留。
    await tester.pump(const Duration(seconds: 3));
    await tester.pumpAndSettle();
  });

  testWidgets('从群聊中选择联系人：群列表展示朋友数且可进入群成员多选', (tester) async {
    _suppressImageErrors();

    final container = _buildContainer(MockChatRepository());
    await _pumpStartGroupChatPage(tester, container: container);

    // 点击「从群聊中选择」入口进入图四。
    await tester.tap(find.text(ChatText.startGroupChatPickFromGroup));
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey<String>('start-group-group-picker-sheet')),
      findsOneWidget,
    );
    // 图四标题与至少一个群行（含「个朋友」计数）。
    expect(find.text(ChatText.startGroupChatGroupPickerTitle), findsOneWidget);
    expect(find.textContaining('个朋友）'), findsWidgets);

    // 进入第一个群（图五）。
    final groupRow = find
        .ancestor(
          of: find.textContaining('个朋友）').first,
          matching: find.byType(CupertinoButton),
        )
        .first;
    await tester.ensureVisible(groupRow);
    await tester.pumpAndSettle();
    await tester.tap(groupRow);
    await tester.pumpAndSettle();

    // 图五群成员多选页打开，标题含「个朋友」。
    expect(
      find.byKey(const ValueKey<String>('start-group-member-select-sheet')),
      findsOneWidget,
    );
    expect(find.textContaining('个朋友）'), findsWidgets);
  });

  testWidgets('从圈子中选择联系人：只展示圈子绑定群并复用成员多选链', (tester) async {
    _suppressImageErrors();

    final repository = _SelectableGroupChatRepository(
      groups: <SelectableGroupConversationRowDto>[
        SelectableGroupConversationRowDto(
          conversationId: 'conv_private',
          title: '私建同行群',
          circleId: '',
          friendMemberCount: 1,
          memberCount: 3,
        ),
        SelectableGroupConversationRowDto(
          conversationId: 'conv_circle',
          title: '摄影圈交流群',
          circleId: 'circle_photo',
          friendMemberCount: 1,
          memberCount: 8,
        ),
      ],
      membersByConversation: <String, List<ChatContactRowDto>>{
        'conv_circle': <ChatContactRowDto>[
          ChatContactRowDto(
            userId: 'user_circle_friend',
            displayName: '圈友',
            relationState: 'mutual',
            source: 'circle',
          ),
        ],
      },
    );
    final container = _buildContainer(repository);
    await _pumpStartGroupChatPage(tester, container: container);

    await tester.tap(find.text(ChatText.startGroupChatPickFromCircle));
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey<String>('start-group-circle-picker-sheet')),
      findsOneWidget,
    );
    expect(find.text(ChatText.startGroupChatCirclePickerTitle), findsOneWidget);
    expect(
      find.byKey(const ValueKey<String>('start-group-picker-row-conv_circle')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('start-group-picker-row-conv_private')),
      findsNothing,
    );

    await tester.tap(
      find.byKey(const ValueKey<String>('start-group-picker-row-conv_circle')),
    );
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey<String>('start-group-member-select-sheet')),
      findsOneWidget,
    );
    expect(
      find.byKey(
        const ValueKey<String>('start-group-candidate-row-user_circle_friend'),
      ),
      findsOneWidget,
    );
  });

  testWidgets('建群聊成功后同时刷新消息列表与群聊列表', (tester) async {
    _suppressImageErrors();

    final repository = MockChatRepository();
    final container = _buildContainer(repository);
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
      chatContactsRowsForSubTabProvider(ChatText.contactsTabGroups).future,
    );

    await tester.tap(find.byIcon(CupertinoIcons.circle).first);
    await tester.pumpAndSettle();
    await tester.tap(find.text(ChatText.startGroupChatActionCount(1)));
    await tester.pumpAndSettle();

    final repositoryInbox = await repository.listInbox(limit: 100);
    expect(
      repositoryInbox.any(
        (item) => item.id.startsWith('fixture_conv_created_'),
      ),
      isTrue,
      reason:
          'Mock 状态引擎应先暴露新会话，实际：'
          '${repositoryInbox.map((item) => item.id).join(',')}',
    );
    final inboxItems = container.read(chatInboxListProvider).items;
    expect(
      inboxItems.any(
        (item) =>
            item.id.startsWith('fixture_conv_created_') &&
            !beforeInboxIds.contains(item.id),
      ),
      isTrue,
      reason:
          'chatInboxListProvider 应刷新新会话，实际：'
          '${inboxItems.map((item) => item.id).join(',')}',
    );
    final afterFunGroups = await container.read(
      chatContactsRowsForSubTabProvider(ChatText.contactsTabGroups).future,
    );
    expect(afterFunGroups.length, greaterThanOrEqualTo(beforeFunGroups.length));
    expect(
      afterFunGroups.any(
        (row) => (row.conversationId ?? '').startsWith('fixture_conv_created_'),
      ),
      isTrue,
    );
    await tester.pump(const Duration(seconds: 3));
    await tester.pumpAndSettle();
  });

  testWidgets('图五选「选择(N)」直接关闭图四+图五回主页并并入已选成员', (tester) async {
    _suppressImageErrors();

    final ops = RecordingAppTelemetryRecorder();
    final repository = _SelectableGroupChatRepository(
      groups: <SelectableGroupConversationRowDto>[
        SelectableGroupConversationRowDto(
          conversationId: 'conv_source',
          title: '产品交流群',
          avatarUrl: '',
          friendMemberCount: 1,
          memberCount: 8,
        ),
      ],
      membersByConversation: <String, List<ChatContactRowDto>>{
        'conv_source': <ChatContactRowDto>[
          ChatContactRowDto(
            userId: 'user_002',
            displayName: '李明',
            avatarUrl: '',
            relationState: 'mutual',
            source: 'group',
          ),
        ],
      },
    );
    final container = _buildContainer(repository, telemetryRecorder: ops);
    await _pumpStartGroupChatPage(tester, container: container);

    // 进入图四群列表。
    await tester.tap(find.text(ChatText.startGroupChatPickFromGroup));
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey<String>('start-group-group-picker-sheet')),
      findsOneWidget,
    );

    // 进入图五群成员多选页。
    await tester.tap(
      find.byKey(const ValueKey<String>('start-group-picker-row-conv_source')),
    );
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey<String>('start-group-member-select-sheet')),
      findsOneWidget,
    );

    // 选中群成员（行整体可点，避免与底部「全选」圈图标混淆）。
    await tester.tap(
      find.byKey(const ValueKey<String>('start-group-candidate-row-user_002')),
    );
    await tester.pumpAndSettle();

    // 点击「选择(1)」→ 直接关闭图五与图四，回到发起群聊主页。
    await tester.tap(find.text('${ChatText.selectAction}（1）'));
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey<String>('start-group-member-select-sheet')),
      findsNothing,
    );
    expect(
      find.byKey(const ValueKey<String>('start-group-group-picker-sheet')),
      findsNothing,
    );
    expect(find.byType(StartGroupChatPage), findsOneWidget);
    // 主页已选区块展示新并入成员。
    expect(find.text(ChatText.startGroupChatSelectedCount(1)), findsOneWidget);
    expect(
      ops.recorded.any((event) => event.action == 'source_group_open'),
      isTrue,
    );
    expect(
      ops.recorded.any(
        (event) => event.action == 'source_group_selection_applied',
      ),
      isTrue,
    );

    await tester.tap(find.text(ChatText.startGroupChatActionCount(1)));
    await tester.pumpAndSettle();
    final createEvent = ops.recorded.lastWhere(
      (event) => event.action == 'create_success',
    );
    expect(createEvent.extensions['result'], 'group');
    await tester.pump(const Duration(seconds: 3));
    await tester.pumpAndSettle();
  });

  testWidgets('图四超长群名 + 朋友数不触发 RenderFlex overflow', (tester) async {
    _suppressImageErrors();

    const longTitle = '一个用于压力测试横向溢出的超长群聊名称连续不断没有空格也没有换行符号';
    final repository = _SelectableGroupChatRepository(
      groups: <SelectableGroupConversationRowDto>[
        SelectableGroupConversationRowDto(
          conversationId: 'conv_long',
          title: longTitle,
          avatarUrl: '',
          friendMemberCount: 12,
          memberCount: 30,
        ),
      ],
      membersByConversation: <String, List<ChatContactRowDto>>{
        'conv_long': <ChatContactRowDto>[
          ChatContactRowDto(
            userId: 'user_002',
            displayName: '李明',
            avatarUrl: '',
            relationState: 'mutual',
            source: 'group',
          ),
        ],
      },
    );
    final container = _buildContainer(repository);
    await _pumpStartGroupChatPage(tester, container: container);

    await tester.tap(find.text(ChatText.startGroupChatPickFromGroup));
    await tester.pumpAndSettle();

    // 长群名行已渲染，且未抛出布局溢出异常。
    expect(
      find.byKey(const ValueKey<String>('start-group-picker-row-conv_long')),
      findsOneWidget,
    );
    expect(find.text(longTitle), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}

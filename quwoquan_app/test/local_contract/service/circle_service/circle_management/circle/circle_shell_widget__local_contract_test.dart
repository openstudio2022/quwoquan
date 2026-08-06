import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/public/rtc_call_entry_coordinator.dart';
import 'package:quwoquan_app/runtime/di/object_intersection_provider.dart';
import 'package:quwoquan_app/runtime/di/rtc_call_entry_presenter.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_behavior_fact/application/public/circle_behavior_fact_appender.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_group/application/public/circle_group_ports.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_membership/application/public/circle_membership_ports.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_surface.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/presentation/circle_action_bar.dart';
import 'package:quwoquan_app/runtime/di/presentation/circle_shell.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_file/presentation/section_storage.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/call_permission_guard.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../../support/service/circle_service/circle_management/circle/circle_query_typed_double.dart';
import '../../../../../support/service/content_service/content/content_behavior_fact/recording_content_behavior_repository.dart';

import '../../../../../support/service/circle_service/circle_management/circle/typed_circle_query_test_double.dart';
import '../../../../../support/service/circle_service/circle_management/circle/circle_contract_test_builders.dart';

class _AuthenticatedCircleSession extends AuthSessionController {
  @override
  AuthSessionState build() => const AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: 'circle-shell-test-token',
    refreshToken: 'circle-shell-test-refresh-token',
    ownerId: 'user_001',
    activePersonaId: 'user_001',
    accountState: 'active',
    identityOrigin: 'widget-test',
    installId: 'circle-shell-widget-test-install',
  );
}

final class _FixtureCircleGroupQuery implements CircleGroupQueries {
  const _FixtureCircleGroupQuery();

  @override
  Future<CircleGroupSlice> get(CircleGroupQuery query) async =>
      CircleGroupSlice(
        groupId: query.groupId,
        version: 1,
        circleId: query.circleId,
        parentGroupId: null,
        groupType: CircleGroupType.publicGroup,
        nodeType: null,
        name: '默认公共群',
        description: '',
        visibility: CircleGroupVisibility.public,
        joinPolicy: CircleGroupJoinPolicy.applyOnly,
        conversationId: 'fixture_conv_${query.circleId}',
        storageEnabled: true,
        noticeEnabled: true,
        isDefaultPublicGroup: true,
        status: CircleGroupStatus.active,
        memberCount: 1,
        createdAt: DateTime.utc(2026, 5, 6),
        updatedAt: DateTime.utc(2026, 5, 6),
      );

  @override
  Future<CircleGroupPageSlice> list(CircleGroupListQuery query) async =>
      CircleGroupPageSlice(items: <CircleGroupSlice>[]);

  @override
  Future<CircleGroupPageSlice> search(CircleGroupSearchQuery query) async =>
      CircleGroupPageSlice(items: <CircleGroupSlice>[]);
}

final class _FixtureCircleMembershipQuery implements CircleMembershipQueries {
  const _FixtureCircleMembershipQuery();

  CircleMembershipSlice _membership({
    required String circleId,
    String personaId = 'user_001',
  }) => CircleMembershipSlice(
    membershipId: '${circleId}_$personaId',
    version: 1,
    circleId: circleId,
    personaId: personaId,
    role: CircleMemberRole.owner,
    state: CircleMembershipState.active,
    joinedAt: DateTime.utc(2026, 5, 6),
    leftAt: null,
    lastActiveAt: DateTime.utc(2026, 5, 6),
    contribution: 0,
    createdAt: DateTime.utc(2026, 5, 6),
    updatedAt: DateTime.utc(2026, 5, 6),
  );

  @override
  Future<CircleMembershipSlice> getMyMembership(
    MyCircleMembershipQuery query,
  ) async => _membership(circleId: query.circleId);

  @override
  Future<CircleMembershipPageSlice> listMemberships(
    CircleMembershipListQuery query,
  ) async => CircleMembershipPageSlice(
    items: <CircleMembershipSlice>[_membership(circleId: query.circleId)],
  );

  @override
  Future<PersonaCirclePageSlice> listPersonaCircles(
    PersonaCircleListQuery query,
  ) async => PersonaCirclePageSlice(items: <PersonaCircleSlice>[]);
}

final class _NoopCircleBehaviorFactWriter
    implements CircleBehaviorFactAppender {
  @override
  Future<void> append(AppendCircleBehaviorFactCommand command) async {}
}

final class _FixtureCircleMembershipCommandWriter
    implements CircleMembershipCommands {
  _FixtureCircleMembershipCommandWriter();

  int _version = 0;

  @override
  Future<CircleMembershipCommandResult> join(
    JoinCircleMembershipCommand command,
  ) async => CircleMembershipCommandResult(
    membershipId: 'fixture_membership',
    version: ++_version,
    state: CircleMembershipState.pending,
    role: CircleMemberRole.member,
    idempotentReplay: false,
  );

  @override
  Future<CircleMembershipCommandResult> leave(
    LeaveCircleMembershipCommand command,
  ) async => CircleMembershipCommandResult(
    membershipId: 'fixture_membership',
    version: ++_version,
    state: CircleMembershipState.left,
    role: CircleMemberRole.member,
    idempotentReplay: false,
  );

  @override
  Future<CircleMembershipCommandResult> updateRole(
    UpdateCircleMembershipRoleCommand command,
  ) async => CircleMembershipCommandResult(
    membershipId: 'fixture_membership',
    version: ++_version,
    state: CircleMembershipState.active,
    role: command.role,
    idempotentReplay: false,
  );
}

Widget _scopedApp({
  CircleQueryReader? circleQuery,
  VoidCallback? onBack,
  String circleId = 'fixture_circle_photo',
  UiErrorAppearanceMode sourceAppearanceMode = UiErrorAppearanceMode.inherit,
  List<Override> overrides = const <Override>[],
}) {
  final alphaQueries = InMemoryCircleQueryReader();
  final query = circleQuery ?? alphaQueries;
  final CircleDiscoveryFeedQueryReader discoveryQuery =
      query is CircleDiscoveryFeedQueryReader
      ? query as CircleDiscoveryFeedQueryReader
      : CircleDiscoveryFeedQueryTestDouble(
          (CircleDiscoveryFeedQuery query) => CircleDiscoveryFeedPageSlice(
            circles: const <Circle>[],
            items: const <CircleFeedItemView>[],
          ),
        );
  return ProviderScope(
    overrides: [
      authSessionControllerProvider.overrideWith(
        _AuthenticatedCircleSession.new,
      ),
      circlesListQueryProvider.overrideWithValue(query),
      circleDetailQueryProvider.overrideWithValue(query),
      circlesListDiscoveryFeedQueryProvider.overrideWithValue(discoveryQuery),
      circleDetailGroupQueryProvider.overrideWithValue(
        const _FixtureCircleGroupQuery(),
      ),
      circleDetailMembershipQueryProvider.overrideWithValue(
        const _FixtureCircleMembershipQuery(),
      ),
      circleDetailMembershipCommandWriterProvider.overrideWithValue(
        _FixtureCircleMembershipCommandWriter(),
      ),
      activePersonaContextProvider.overrideWith(
        (_) async => ActivePersonaContextViewData.fallback(
          personaId: 'user_001',
          ownerUserId: 'user_001',
          displayName: '圈子测试用户',
          avatarUrl: '',
          contextVersion: 1,
        ),
      ),
      circleDetailBehaviorFactWriterProvider.overrideWithValue(
        _NoopCircleBehaviorFactWriter(),
      ),
      behaviorRepositoryProvider.overrideWithValue(RecordingContentBehaviorRepository()),
      ...overrides,
    ],
    child: MaterialApp.router(
      routerConfig: GoRouter(
        initialLocation: '/',
        routes: [
          GoRoute(
            path: '/',
            builder: (_, _) => Scaffold(
              body: CircleShell(
                circleId: circleId,
                membershipApprovalPageBuilder: (_) => const SizedBox.shrink(),
                onBack: onBack,
                sourceAppearanceMode: sourceAppearanceMode,
              ),
            ),
          ),
          GoRoute(path: '/chat/:id', builder: (_, _) => const SizedBox()),
        ],
      ),
    ),
  );
}

Future<void> _pumpShell(
  WidgetTester tester, {
  CircleQueryReader? circleQuery,
  VoidCallback? onBack,
  String circleId = 'fixture_circle_photo',
  UiErrorAppearanceMode sourceAppearanceMode = UiErrorAppearanceMode.inherit,
  List<Override> overrides = const <Override>[],
}) async {
  // 对象主页改版后圈子壳层内容更长，默认 800x600 视口会触发 NestedScrollView
  // 的 pinned tab/吸顶层覆盖，导致动作栏命中测试失败。这里放大视口让壳层完整内联展示。
  tester.view.physicalSize = const Size(1080, 3600);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(
    _scopedApp(
      circleQuery: circleQuery,
      onBack: onBack,
      circleId: circleId,
      sourceAppearanceMode: sourceAppearanceMode,
      overrides: overrides,
    ),
  );
  await tester.pumpAndSettle();
  await tester.pump(const Duration(milliseconds: 350));
}

void main() {
  group('CircleShell - 渲染契约', () {
    testWidgets('黄金投资圈预制 seed 可直接打开圈子高保壳层', (tester) async {
      await _pumpShell(tester, circleId: 'fixture_circle_gold_invest');

      expect(find.text('黄金投资圈'), findsWidgets);
      expect(find.text('黄金 · 贵金属 · 资产配置'), findsWidgets);
      expect(find.text('围绕黄金、贵金属和长期资产配置展开事实讨论。'), findsWidgets);
      expect(find.text('8.4k'), findsOneWidget);
      expect(find.text(CommunityText.circleMembers), findsWidgets);
      expect(find.text('1.2k'), findsOneWidget);
      expect(find.text('326'), findsWidgets);
      expect(find.byType(AppPageErrorState), findsNothing);
      expect(find.text(ObjectHomepageText.objectTabRecord), findsWidgets);
      expect(find.text('讨论'), findsWidgets);
      expect(find.text('成员'), findsWidgets);
      expect(
        find.byKey(const ValueKey<String>('circle-header-verified-badge')),
        findsNothing,
        reason: 'CircleStatus.active 只表示生命周期，不能推断官方认证',
      );
      expect(
        find.byKey(const ValueKey<String>('circle-creations-filter-bar')),
        findsOneWidget,
      );
    });

    testWidgets('使用资料页背景层与一级 tab 壳层', (tester) async {
      await _pumpShell(tester);

      expect(
        find.byKey(const ValueKey<String>('circle-shell-background-layer')),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey<String>('circle-shell-primary-tabs-inline')),
        findsOneWidget,
      );
      expect(find.byType(CircleActionBar), findsOneWidget);
      // 圈子壳层一级 Tab 收敛为 记录 / 讨论 / 成员（统一「记录」载体口径，§18「讨论」命名一致）。
      expect(
        find.descendant(
          of: find.byKey(
            const ValueKey<String>('circle-shell-primary-tabs-inline'),
          ),
          matching: find.text(ObjectHomepageText.objectTabRecord),
        ),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: find.byKey(
            const ValueKey<String>('circle-shell-primary-tabs-inline'),
          ),
          matching: find.text('讨论'),
        ),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: find.byKey(
            const ValueKey<String>('circle-shell-primary-tabs-inline'),
          ),
          matching: find.text('成员'),
        ),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: find.byKey(
            const ValueKey<String>('circle-shell-primary-tabs-inline'),
          ),
          matching: find.text('首页'),
        ),
        findsNothing,
      );
    });

    testWidgets('讨论 Tab 不再混入资料存储与上传入口', (tester) async {
      await _pumpShell(tester, circleId: 'fixture_circle_gold_invest');

      final discussionTab = find.descendant(
        of: find.byKey(
          const ValueKey<String>('circle-shell-primary-tabs-inline'),
        ),
        matching: find.text(ObjectHomepageText.objectTabDiscussion),
      );
      await tester.tap(discussionTab);
      await tester.pumpAndSettle();

      expect(find.byType(SectionStorage), findsNothing);
      expect(find.text('资料'), findsNothing);
      expect(find.text('上传文件'), findsNothing);
    });

    testWidgets('圈子影响展示云侧 displayText，最多三条且不本地拼装', (tester) async {
      await _pumpShell(tester, circleQuery: _ImpactCircleQuery());

      expect(
        find.text(ObjectHomepageText.objectImpactTitleCircle),
        findsOneWidget,
      );
      expect(find.text('12人在这里建立了新连接'), findsOneWidget);
      expect(find.text('5个讨论正在这里发生'), findsOneWidget);
      expect(find.text('3人最近参与了这里'), findsOneWidget);
      expect(find.text('第4条不应显示'), findsNothing);
      expect(find.textContaining('条内容正在沉淀经验'), findsNothing);
    });

    testWidgets('圈子有打动事实但我的交集为空时，不提示成为第一个人', (tester) async {
      const circleId = 'fixture_circle_photo';
      const viewerId = 'viewer_empty_intersection';
      const query = ObjectIntersectionQuery(
        objectAId: viewerId,
        objectAType: 'user',
        objectBId: circleId,
        objectBType: 'circle',
      );
      await _pumpShell(
        tester,
        circleQuery: _ImpactCircleQuery(),
        circleId: circleId,
        overrides: <Override>[
          currentUserIdProvider.overrideWithValue(viewerId),
          objectSharedReasonsProvider(
            query,
          ).overrideWith((_) async => const []),
        ],
      );

      expect(
        find.text(ObjectHomepageText.objectImpactTitleCircle),
        findsOneWidget,
      );
      expect(find.text('12人在这里建立了新连接'), findsOneWidget);
      expect(
        find.text(ObjectHomepageText.objectIntersectionEmptyCircle),
        findsOneWidget,
      );
      expect(find.textContaining('成为第一个'), findsNothing);
    });

    testWidgets('圈子影响事实行可点开查看来源说明', (tester) async {
      await _pumpShell(tester, circleQuery: _ImpactCircleQuery());

      await tester.tap(find.text('12人在这里建立了新连接'));
      await tester.pumpAndSettle();

      expect(find.text('12人在这里建立了新连接'), findsWidgets);
      expect(
        find.textContaining(ObjectHomepageText.impactEnumerableHintCircle),
        findsOneWidget,
      );
    });

    testWidgets('圈子影响为空时整体收起', (tester) async {
      await _pumpShell(tester, circleQuery: _EmptyImpactCircleQuery());

      expect(
        find.text(ObjectHomepageText.objectImpactTitleCircle),
        findsNothing,
      );
    });

    testWidgets('圈子影响错误时不阻塞主页并收起影响卡', (tester) async {
      await _pumpShell(tester, circleQuery: _ImpactErrorCircleQuery());

      expect(find.byType(CircleShell), findsOneWidget);
      expect(
        find.text(ObjectHomepageText.objectImpactTitleCircle),
        findsNothing,
      );
    });

    testWidgets('私密圈子游客访问时显示内容门禁', (tester) async {
      await _pumpShell(
        tester,
        circleQuery: _PrivateVisitorCircleQuery(),
        overrides: <Override>[
          resolvedOwnerUserIdProvider.overrideWithValue(''),
        ],
      );

      // 默认 Tab 为「内容」，私密圈子游客态展示内容门禁。
      expect(
        find.byKey(const ValueKey<String>('circle-shell-gate-content')),
        findsOneWidget,
      );

      await tester.tap(find.text('讨论').first);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(
        find.byKey(const ValueKey<String>('circle-shell-gate-discussion')),
        findsOneWidget,
      );
    });
  });

  group('CircleShell - 交互契约', () {
    testWidgets('返回按钮回调正确触发', (tester) async {
      var called = false;

      await _pumpShell(tester, onBack: () => called = true);

      await tester.tap(find.byIcon(CupertinoIcons.back));
      await tester.pump();

      expect(called, isTrue);
    });

    testWidgets('成员从圈子更多动作进入 picker 并携带 circle/conversation context', (
      tester,
    ) async {
      final pickerIntents = <RtcCallEntryIntent>[];
      await _pumpShell(
        tester,
        overrides: <Override>[
          rtcCallEntryPresenterProvider.overrideWithValue(
            RtcCallEntryPresenter(
              permissionRequest: (_, _) async => CallPermissionOutcome.granted,
              participantPicker: (_, intent) async {
                pickerIntents.add(intent);
                return null;
              },
            ),
          ),
        ],
      );

      await tester.tap(
        find.byKey(const ValueKey<String>('object-chrome-more')),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text(CallText.callGroupVoice));
      await tester.pumpAndSettle();

      expect(pickerIntents, hasLength(1));
      expect(pickerIntents.single.contextKind, RtcCallEntryContextKind.circle);
      expect(pickerIntents.single.circleId, 'fixture_circle_photo');
      expect(
        pickerIntents.single.conversationId,
        'fixture_conv_fixture_circle_photo',
      );
      expect(pickerIntents.single.defaultSelectAll, isTrue);
    });

    testWidgets('更多按钮打开统一底部动作面板并支持复制链接', (tester) async {
      String? copiedText;
      tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        SystemChannels.platform,
        (call) async {
          if (call.method == 'Clipboard.setData') {
            copiedText = (call.arguments as Map?)?['text']?.toString();
          }
          return null;
        },
      );
      addTearDown(() {
        tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
          SystemChannels.platform,
          null,
        );
      });

      await _pumpShell(tester);

      await tester.tap(
        find.byKey(const ValueKey<String>('object-chrome-more')),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.byType(AppBottomModalSurface), findsOneWidget);
      expect(find.text(FoundationText.copyLink), findsOneWidget);

      await tester.tap(find.text(FoundationText.copyLink));
      await tester.pumpAndSettle();
      await tester.pump(const Duration(seconds: 3));

      // 复制链接必须是可分享深链（metadata link_templates circle path），
      // 而不是裸 circleId（2026-07-20 M8-H Phase 1 断点修复）。
      expect(copiedText, isNotNull);
      expect(copiedText, endsWith('/circle/fixture_circle_photo'));
      expect(copiedText, isNot(equals('fixture_circle_photo')));
    });

    testWidgets('审批加入后切换为待审核状态', (tester) async {
      await _pumpShell(
        tester,
        circleQuery: _ApprovalVisitorCircleQuery(),
        overrides: <Override>[
          resolvedOwnerUserIdProvider.overrideWithValue(''),
        ],
      );

      final joinFinder = find.descendant(
        of: find.byType(CircleActionBar),
        matching: find.text(CommunityText.circleJoinApproval),
      );
      await tester.tap(joinFinder);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 350));

      expect(
        find.descendant(
          of: find.byType(CircleActionBar),
          matching: find.text(CommunityText.joinPending),
        ),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: find.byType(CircleActionBar),
          matching: find.text(ObjectHomepageText.circleActionEnterDiscussion),
        ),
        findsOneWidget,
      );
    });
  });

  group('CircleShell - 稳定性', () {
    testWidgets('Repository 异常时 Widget 不崩溃', (tester) async {
      await _pumpShell(tester, circleQuery: _ErrorCircleQuery());

      expect(find.byType(AppPageErrorState), findsOneWidget);
      expect(find.text(SearchText.reload), findsOneWidget);
      expect(
        find.byKey(const ValueKey<String>('circle-shell-error-back')),
        findsOneWidget,
      );
    });

    testWidgets('Repository 异常时只由宿主顶栏提供返回', (tester) async {
      var backCalled = false;
      await _pumpShell(
        tester,
        circleQuery: _ErrorCircleQuery(),
        onBack: () => backCalled = true,
      );

      expect(
        find.byKey(const ValueKey<String>('circle-shell-error-back')),
        findsOneWidget,
      );
      expect(find.byIcon(CupertinoIcons.xmark), findsNothing);
      expect(find.text(ContentText.back), findsNothing);

      await tester.tap(
        find.byKey(const ValueKey<String>('circle-shell-error-back')),
      );
      await tester.pump();
      expect(backCalled, isTrue);
    });

    testWidgets('Repository 异常错误态跟随来源页面 appearance', (tester) async {
      await _pumpShell(
        tester,
        circleQuery: _ErrorCircleQuery(),
        sourceAppearanceMode: UiErrorAppearanceMode.light,
      );
      var errorState = tester.widget<AppPageErrorState>(
        find.byType(AppPageErrorState),
      );
      expect(errorState.semantic.appearanceMode, UiErrorAppearanceMode.light);

      await _pumpShell(
        tester,
        circleQuery: _ErrorCircleQuery(),
        sourceAppearanceMode: UiErrorAppearanceMode.dark,
      );
      errorState = tester.widget<AppPageErrorState>(
        find.byType(AppPageErrorState),
      );
      expect(errorState.semantic.appearanceMode, UiErrorAppearanceMode.dark);
    });
  });
}

class _PrivateVisitorCircleQuery extends CircleQueryReaderTestDouble {
  @override
  Future<Circle> get(CircleDetailQuery query) async => buildCircleContract(
    circleId: query.circleId,
    name: '私密测试圈子',
    ownerId: 'fixture_user_owner',
    visibility: CircleVisibility.private,
  );
}

class _ApprovalVisitorCircleQuery extends CircleQueryReaderTestDouble {
  @override
  Future<Circle> get(CircleDetailQuery query) async => buildCircleContract(
    circleId: query.circleId,
    name: '审批测试圈子',
    ownerId: 'fixture_user_owner',
    visibility: CircleVisibility.public,
    joinPolicy: CircleJoinPolicy.approval,
  );
}

class _ImpactCircleQuery extends CircleQueryReaderTestDouble {
  @override
  Future<CircleImpactSummary> impact(CircleImpactQuery query) async {
    return CircleImpactSummary(
      circleId: query.circleId,
      total: 21,
      items: <CircleImpactItem>[
        buildCircleImpactItemContract(
          helpType: 'relationship',
          action: 'establish_connection',
          intersectionDimension: 'relationship',
          source: 'test',
          count: 12,
          primaryText: '12人在这里建立了新连接',
        ),
        buildCircleImpactItemContract(
          helpType: 'community',
          action: 'start_discussion',
          intersectionDimension: 'content',
          source: 'test',
          count: 5,
          primaryText: '5个讨论正在这里发生',
        ),
        buildCircleImpactItemContract(
          helpType: 'spread',
          action: 'active_participation',
          intersectionDimension: 'interest',
          source: 'test',
          count: 3,
          primaryText: '3人最近参与了这里',
        ),
        buildCircleImpactItemContract(
          helpType: 'spread',
          action: 'hidden',
          intersectionDimension: 'interest',
          source: 'test',
          count: 1,
          primaryText: '第4条不应显示',
        ),
      ],
    );
  }
}

class _EmptyImpactCircleQuery extends CircleQueryReaderTestDouble {
  @override
  Future<CircleImpactSummary> impact(CircleImpactQuery query) async =>
      CircleImpactSummary(
        circleId: query.circleId,
        total: 0,
        items: const <CircleImpactItem>[],
      );
}

class _ImpactErrorCircleQuery extends CircleQueryReaderTestDouble {
  @override
  Future<CircleImpactSummary> impact(CircleImpactQuery query) async {
    throw Exception('impact failed');
  }
}

class _ErrorCircleQuery extends CircleQueryReaderTestDouble {
  @override
  Future<Circle> get(CircleDetailQuery query) async {
    throw Exception('Network error');
  }

  @override
  Future<CircleStatsWire> stats(CircleStatsQuery query) async {
    throw Exception('Network error');
  }
}

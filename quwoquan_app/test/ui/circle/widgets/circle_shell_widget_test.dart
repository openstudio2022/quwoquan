import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_impact_item.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_impact_summary.g.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_stats_wire_dto.dart';
import 'package:quwoquan_app/cloud/runtime/models/circle_detail_payload.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/auth_login_result_dto.g.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/cloud/services/circle/mock/circle_mock_data.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/app_modal_surface.dart';
import 'package:quwoquan_app/ui/circle/widgets/circle_action_bar.dart';
import 'package:quwoquan_app/ui/circle/widgets/circle_shell.dart';

class _AuthedSessionStore implements AuthSessionStore {
  const _AuthedSessionStore();

  @override
  Future<StoredAuthSession> read() async => const StoredAuthSession(
    accessToken: 'access-token',
    refreshToken: 'refresh-token',
    ownerId: 'user_001',
    activeSubAccountId: 'user_001',
    accountState: 'active',
    identityOrigin: 'phone',
    installId: 'install-id',
    lastRefreshAtEpochMs: 0,
    lastForegroundAuthCheckAtEpochMs: 0,
    manualLoggedOut: false,
    launchPromptDismissed: true,
  );

  @override
  Future<void> saveLoginResult(
    AuthLoginResultDto result, {
    AuthRememberedLoginMethod rememberedLoginMethod =
        AuthRememberedLoginMethod.unknown,
    String? rememberedLoginMaskedIdentifier,
    String? rememberedLoginIdentifier,
  }) async {}

  @override
  Future<void> saveRefreshedTokens({
    required String accessToken,
    required String refreshToken,
  }) async {}

  @override
  Future<void> updateActiveSubAccount(String subAccountId) async {}

  @override
  Future<void> clearSession({required bool manualLogout}) async {}

  @override
  Future<void> softLogout() async {}

  @override
  Future<void> markLaunchPromptDismissed() async {}

  @override
  Future<void> markForegroundAuthCheckNow() async {}
}

Widget _scopedApp({CircleRepository? mock, VoidCallback? onBack}) {
  final repo = mock ?? MockCircleRepository();
  return ProviderScope(
    overrides: [
      circleRepositoryProvider.overrideWithValue(repo),
      authSessionStoreProvider.overrideWithValue(const _AuthedSessionStore()),
    ],
    child: MaterialApp.router(
      routerConfig: GoRouter(
        initialLocation: '/',
        routes: [
          GoRoute(
            path: '/',
            builder: (_, _) => Scaffold(
              body: CircleShell(
                circleId: 'fixture_circle_photo',
                onBack: onBack,
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
  CircleRepository? mock,
  VoidCallback? onBack,
}) async {
  // 对象主页改版后圈子壳层内容更长，默认 800x600 视口会触发 NestedScrollView
  // 的 pinned tab/吸顶层覆盖，导致动作栏命中测试失败。这里放大视口让壳层完整内联展示。
  tester.view.physicalSize = const Size(1080, 3600);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(_scopedApp(mock: mock, onBack: onBack));
  // CircleShell 不主动 watch 登录态，这里显式触发 auth session 构建并 hydrate，
  // 让加入/关注按钮的 requireLogin 在已登录态下放行。
  ProviderScope.containerOf(
    tester.element(find.byType(CircleShell)),
  ).read(authSessionControllerProvider);
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 350));
}

void main() {
  group('CircleShell - 渲染契约', () {
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
      // 圈子壳层一级 Tab 收敛为 内容 / 讨论 / 成员（与 §18「讨论」命名一致）。
      expect(
        find.descendant(
          of: find.byKey(
            const ValueKey<String>('circle-shell-primary-tabs-inline'),
          ),
          matching: find.text('内容'),
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

    testWidgets('圈子影响展示云侧 displayText，最多三条且不本地拼装', (tester) async {
      await _pumpShell(tester, mock: _ImpactCircleRepository());

      expect(find.text(UITextConstants.circleImpactTitle), findsOneWidget);
      expect(find.text('12人在这里建立了新连接'), findsOneWidget);
      expect(find.text('5个讨论正在这里发生'), findsOneWidget);
      expect(find.text('3人最近参与了这里'), findsOneWidget);
      expect(find.text('第4条不应显示'), findsNothing);
      expect(find.textContaining('条内容正在沉淀经验'), findsNothing);
    });

    testWidgets('圈子影响事实行可点开查看来源说明', (tester) async {
      await _pumpShell(tester, mock: _ImpactCircleRepository());

      await tester.tap(find.text('12人在这里建立了新连接'));
      await tester.pumpAndSettle();

      expect(find.text('12人在这里建立了新连接'), findsWidgets);
      expect(
        find.textContaining(UITextConstants.impactEnumerableHintCircle),
        findsOneWidget,
      );
    });

    testWidgets('圈子影响为空时整体收起', (tester) async {
      await _pumpShell(tester, mock: _EmptyImpactCircleRepository());

      expect(find.text(UITextConstants.circleImpactTitle), findsNothing);
    });

    testWidgets('圈子影响错误时不阻塞主页并收起影响卡', (tester) async {
      await _pumpShell(tester, mock: _ImpactErrorCircleRepository());

      expect(find.byType(CircleShell), findsOneWidget);
      expect(find.text(UITextConstants.circleImpactTitle), findsNothing);
    });

    testWidgets('私密圈子游客访问时显示内容门禁', (tester) async {
      await _pumpShell(tester, mock: _PrivateVisitorCircleRepository());

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

      await tester.tap(find.byIcon(CupertinoIcons.ellipsis));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.byType(AppBottomModalSurface), findsOneWidget);
      expect(find.text(UITextConstants.copyLink), findsOneWidget);

      await tester.tap(find.text(UITextConstants.copyLink));
      await tester.pumpAndSettle();
      await tester.pump(const Duration(seconds: 3));

      expect(copiedText, equals('fixture_circle_photo'));
    });

    testWidgets('审批加入后切换为待审核状态', (tester) async {
      await _pumpShell(tester, mock: _ApprovalVisitorCircleRepository());

      final joinFinder = find.descendant(
        of: find.byType(CircleActionBar),
        matching: find.text(UITextConstants.circleJoinApproval),
      );
      await tester.tap(joinFinder);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 350));

      expect(
        find.descendant(
          of: find.byType(CircleActionBar),
          matching: find.text(UITextConstants.joinPending),
        ),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: find.byType(CircleActionBar),
          matching: find.text(UITextConstants.profileDirectMessage),
        ),
        findsOneWidget,
      );
    });
  });

  group('CircleShell - 稳定性', () {
    testWidgets('Repository 异常时 Widget 不崩溃', (tester) async {
      await _pumpShell(tester, mock: _ErrorCircleRepository());

      expect(find.byType(CircleShell), findsOneWidget);
      expect(find.text('圈子信息暂不可用'), findsAtLeastNWidgets(1));
      expect(find.text(UITextConstants.tryAgain), findsOneWidget);
    });
  });
}

class _PrivateVisitorCircleRepository extends MockCircleRepository {
  @override
  Future<CircleDetailPayload> getCircle(String circleId) async {
    return CircleDetailPayload.fromWire(<String, dynamic>{
      ...CircleMockData.circleInfo,
      'id': circleId,
      'visibility': 'private',
      'role': 'visitor',
      'joinStatus': 'none',
      'isFollowed': false,
    });
  }
}

class _ApprovalVisitorCircleRepository extends MockCircleRepository {
  @override
  Future<CircleDetailPayload> getCircle(String circleId) async {
    return CircleDetailPayload.fromWire(<String, dynamic>{
      ...CircleMockData.circleInfo,
      'id': circleId,
      'visibility': 'public',
      'joinPolicy': 'approval',
      'role': 'visitor',
      'joinStatus': 'none',
      'isFollowed': false,
    });
  }
}

class _ImpactCircleRepository extends MockCircleRepository {
  @override
  Future<CircleImpactSummary> getCircleImpact(String circleId) async {
    return CircleImpactSummary(
      circleId: circleId,
      total: 21,
      items: <CircleImpactItem>[
        CircleImpactItem(
          helpType: 'relationship',
          action: 'establish_connection',
          intersectionDimension: 'relationship',
          source: 'test',
          count: 12,
          displayText: '12人在这里建立了新连接',
        ),
        CircleImpactItem(
          helpType: 'community',
          action: 'start_discussion',
          intersectionDimension: 'content',
          source: 'test',
          count: 5,
          displayText: '5个讨论正在这里发生',
        ),
        CircleImpactItem(
          helpType: 'spread',
          action: 'active_participation',
          intersectionDimension: 'interest',
          source: 'test',
          count: 3,
          displayText: '3人最近参与了这里',
        ),
        CircleImpactItem(
          helpType: 'spread',
          action: 'hidden',
          intersectionDimension: 'interest',
          source: 'test',
          count: 1,
          displayText: '第4条不应显示',
        ),
      ],
    );
  }
}

class _EmptyImpactCircleRepository extends MockCircleRepository {
  @override
  Future<CircleImpactSummary> getCircleImpact(String circleId) async {
    return CircleImpactSummary(circleId: circleId);
  }
}

class _ImpactErrorCircleRepository extends MockCircleRepository {
  @override
  Future<CircleImpactSummary> getCircleImpact(String circleId) async {
    throw Exception('impact failed');
  }
}

class _ErrorCircleRepository extends MockCircleRepository {
  @override
  Future<CircleDetailPayload> getCircle(String circleId) async {
    throw Exception('Network error');
  }

  @override
  Future<CircleStatsWireDto> getCircleStats(String circleId) async {
    throw Exception('Network error');
  }
}

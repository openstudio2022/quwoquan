import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/cloud/services/circle/mock/circle_mock_data.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/app_modal_surface.dart';
import 'package:quwoquan_app/ui/circle/widgets/circle_action_bar.dart';
import 'package:quwoquan_app/ui/circle/widgets/circle_shell.dart';

Widget _scopedApp({
  CircleRepository? mock,
  VoidCallback? onBack,
}) {
  final repo = mock ?? MockCircleRepository();
  return ProviderScope(
    overrides: [circleRepositoryProvider.overrideWithValue(repo)],
    child: MaterialApp.router(
      routerConfig: GoRouter(
        initialLocation: '/',
        routes: [
          GoRoute(
            path: '/',
            builder: (_, _) => Scaffold(
              body: CircleShell(
                circleId: 'circle_photo_01',
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
  await tester.pumpWidget(_scopedApp(mock: mock, onBack: onBack));
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
      expect(
        find.descendant(
          of: find.byKey(
            const ValueKey<String>('circle-shell-primary-tabs-inline'),
          ),
          matching: find.text(UITextConstants.circleWorksTab),
        ),
        findsOneWidget,
      );
    });

    testWidgets('私密圈子游客访问时显示内容门禁', (tester) async {
      await _pumpShell(tester, mock: _PrivateVisitorCircleRepository());

      expect(
        find.byKey(const ValueKey<String>('circle-shell-gate-content')),
        findsOneWidget,
      );

      await tester.tap(find.text(UITextConstants.circleAssetsTab).first);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));

      expect(
        find.byKey(const ValueKey<String>('circle-shell-gate-assets')),
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

      expect(copiedText, equals('circle_photo_01'));
    });

    testWidgets('审批加入后切换为待审核状态', (tester) async {
      await _pumpShell(tester, mock: _ApprovalVisitorCircleRepository());

      await tester.tap(
        find.descendant(
          of: find.byType(CircleActionBar),
          matching: find.text(UITextConstants.circleJoinApproval),
        ),
      );
      await tester.pump();

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
          matching: find.text(UITextConstants.followedCircle),
        ),
        findsOneWidget,
      );
    });
  });

  group('CircleShell - 稳定性', () {
    testWidgets('Repository 异常时 Widget 不崩溃', (tester) async {
      await _pumpShell(tester, mock: _ErrorCircleRepository());

      expect(find.byType(CircleShell), findsOneWidget);
      expect(find.text(UITextConstants.loadFailed), findsAtLeastNWidgets(1));
    });
  });
}

class _PrivateVisitorCircleRepository extends MockCircleRepository {
  @override
  Future<Map<String, dynamic>> getCircle(String circleId) async {
    return <String, dynamic>{
      ...CircleMockData.circleInfo,
      'id': circleId,
      'visibility': 'private',
      'role': 'visitor',
      'joinStatus': 'none',
      'isFollowed': false,
    };
  }
}

class _ApprovalVisitorCircleRepository extends MockCircleRepository {
  @override
  Future<Map<String, dynamic>> getCircle(String circleId) async {
    return <String, dynamic>{
      ...CircleMockData.circleInfo,
      'id': circleId,
      'visibility': 'public',
      'joinPolicy': 'approval',
      'role': 'visitor',
      'joinStatus': 'none',
      'isFollowed': false,
    };
  }
}

class _ErrorCircleRepository extends MockCircleRepository {
  @override
  Future<Map<String, dynamic>> getCircle(String circleId) async {
    throw Exception('Network error');
  }

  @override
  Future<Map<String, dynamic>> getCircleStats(String circleId) async {
    throw Exception('Network error');
  }
}

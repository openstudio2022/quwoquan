import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/cloud/user/generated/user_profile_ui_config.g.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_shell.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_circles_tab.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_interaction_tab.dart';

/// 在 UI 测试中使 capability 保持 null（legacy 关注/私信 布局）
class _ThrowingCapabilityRepository extends RelationshipCapabilityRepository {
  @override
  Future<RelationshipCapabilityDto> getCapability(String targetUserId) {
    return Future.error(StateError('capability unavailable in test'));
  }
}

Widget _scopedApp({
  required ProfileMode mode,
  String userId = 'nature_photographer',
  ThemeMode themeMode = ThemeMode.light,
  double textScaleFactor = 1.0,
}) {
  return ProviderScope(
    overrides: [
      userProfileRepositoryProvider.overrideWithValue(
        const MockUserProfileRepository(),
      ),
      relationshipCapabilityRepositoryProvider.overrideWithValue(
        _ThrowingCapabilityRepository(),
      ),
    ],
    child: MaterialApp(
      builder: (context, child) {
        final mediaQuery = MediaQuery.of(context);
        return MediaQuery(
          data: mediaQuery.copyWith(
            textScaler: TextScaler.linear(textScaleFactor),
          ),
          child: child ?? const SizedBox.shrink(),
        );
      },
      themeMode: themeMode,
      theme: ThemeData.light(),
      darkTheme: ThemeData.dark(),
      home: ProfileShell(mode: mode, userId: userId),
    ),
  );
}

Future<void> _pumpFrames(WidgetTester tester, {int count = 10}) async {
  for (var i = 0; i < count; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}

void _setPhoneSize(WidgetTester tester) {
  tester.view.physicalSize = const Size(1080, 2400);
  tester.view.devicePixelRatio = 3.0;
}

void main() {
  setUp(() {
    HttpOverrides.global = _NoNetworkHttpOverrides();
  });

  group('ProfileShell — 渲染契约', () {
    testWidgets('mine 模式渲染设置按钮', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester);
      expect(find.byIcon(CupertinoIcons.settings), findsOneWidget);
    });

    testWidgets('other 模式渲染返回和更多按钮', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.other));
      await _pumpFrames(tester);
      expect(find.byIcon(CupertinoIcons.back), findsOneWidget);
      expect(find.byIcon(CupertinoIcons.ellipsis), findsOneWidget);
    });

    testWidgets('渲染三个主 Tab', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester);
      expect(find.text('创作'), findsOneWidget);
      expect(_inlinePrimaryTab('圈子'), findsOneWidget);
      expect(find.text('互动'), findsOneWidget);
    });

    testWidgets('窄屏大字号下保持自适应不溢出', (tester) async {
      tester.view.physicalSize = const Size(320, 690);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final capturedErrors = <FlutterErrorDetails>[];
      final originalOnError = FlutterError.onError;
      FlutterError.onError = (details) {
        capturedErrors.add(details);
      };
      try {
        await tester.pumpWidget(
          _scopedApp(mode: ProfileMode.mine, textScaleFactor: 1.4),
        );
        await _pumpFrames(tester, count: 20);
      } finally {
        FlutterError.onError = originalOnError;
      }

      final overflowErrors = capturedErrors
          .map((details) => details.exceptionAsString())
          .where((message) => message.contains('A RenderFlex overflowed'))
          .toList(growable: false);

      expect(overflowErrors, isEmpty);
    });
  });

  group('ProfileShell — 几何与分层', () {
    testWidgets('ProfileHeader 不渲染 @username', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester);
      expect(find.textContaining('@'), findsNothing);
    });

    testWidgets('头像保持约 1/3 在背景、2/3 在资料区', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester);
      final backgroundFinder = find.byKey(
        const ValueKey<String>('profile-shell-background-layer'),
      );
      final summaryFinder = find.byKey(
        const ValueKey<String>('profile-shell-summary-card'),
      );
      final avatarFinder = find.byKey(
        const ValueKey<String>('profile-header-avatar'),
      );
      final backgroundBottom = tester.getBottomLeft(backgroundFinder).dy;
      final summaryTop = tester.getTopLeft(summaryFinder).dy;
      final avatarTop = tester.getTopLeft(avatarFinder).dy;
      final avatarBottom = tester.getBottomLeft(avatarFinder).dy;
      final avatarHeight = tester.getSize(avatarFinder).height;

      expect(summaryTop, closeTo(backgroundBottom, 2));
      final backgroundShare = (backgroundBottom - avatarTop) / avatarHeight;
      final summaryShare = (avatarBottom - backgroundBottom) / avatarHeight;
      expect(
        backgroundShare,
        closeTo(UserProfileUIConfig.headerLayout.avatarOverlapRatio, 0.08),
      );
      expect(summaryShare, closeTo(1 - backgroundShare, 0.08));
    });

    testWidgets('other 模式渲染等宽「关注」+主消息入口按钮', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.other));
      await _pumpFrames(tester);
      expect(find.text('关注'), findsAtLeastNWidgets(1));
      expect(
        find.text(UITextConstants.profileDirectMessage),
        findsAtLeastNWidgets(1),
      );
    });

    testWidgets('下拉时背景顶边固定，资料区与一级 tab 整体下移', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester);

      final backgroundFinder = find.byKey(
        const ValueKey<String>('profile-shell-background-layer'),
      );
      final summaryFinder = find.byKey(
        const ValueKey<String>('profile-shell-summary-card'),
      );
      final tabsFinder = find.byKey(
        const ValueKey<String>('profile-shell-primary-tabs-inline'),
      );

      final beforeBackgroundTop = tester.getTopLeft(backgroundFinder).dy;
      final beforeBackgroundHeight = tester.getSize(backgroundFinder).height;
      final beforeSummaryTop = tester.getTopLeft(summaryFinder).dy;
      final beforeTabsTop = tester.getTopLeft(tabsFinder).dy;

      await tester.drag(find.byType(CustomScrollView), const Offset(0, 180));
      await tester.pump();

      final afterBackgroundTop = tester.getTopLeft(backgroundFinder).dy;
      final afterBackgroundHeight = tester.getSize(backgroundFinder).height;
      final afterSummaryTop = tester.getTopLeft(summaryFinder).dy;
      final afterTabsTop = tester.getTopLeft(tabsFinder).dy;

      expect(afterBackgroundTop, closeTo(beforeBackgroundTop, 0.5));
      expect(afterBackgroundHeight, greaterThan(beforeBackgroundHeight));
      expect(afterSummaryTop, greaterThan(beforeSummaryTop));
      expect(afterTabsTop, greaterThan(beforeTabsTop));
    });
  });

  group('ProfileShell — 交互契约', () {
    testWidgets('切换到圈子 Tab 渲染 ProfileCirclesTab', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester);
      await tester.tap(_inlinePrimaryTab('圈子'));
      await _pumpFrames(tester, count: 20);
      expect(find.byType(ProfileCirclesTab), findsOneWidget);
    });

    testWidgets('切换到互动 Tab 渲染 ProfileInteractionTab', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester);
      await tester.tap(_inlinePrimaryTab('互动'));
      await _pumpFrames(tester, count: 20);
      expect(find.byType(ProfileInteractionTab), findsOneWidget);
    });

    testWidgets('互动二级 Tab 跟随内容滚动并可回显', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester);
      await tester.tap(_inlinePrimaryTab('互动'));
      await _pumpFrames(tester, count: 20);

      final subTabFinder = find.descendant(
        of: find.byKey(
          const ValueKey<String>('profile-interaction-secondary-tabs'),
        ),
        matching: find.text('赞'),
      );
      final before = tester.getTopLeft(subTabFinder);

      await tester.drag(find.byType(CustomScrollView), const Offset(0, -600));
      await tester.pumpAndSettle();
      final afterScrollUp = tester.getTopLeft(subTabFinder);
      expect(afterScrollUp.dy, lessThan(before.dy));

      await tester.drag(find.byType(CustomScrollView), const Offset(0, 260));
      await tester.pumpAndSettle();
      final afterScrollBack = tester.getTopLeft(subTabFinder);
      expect(afterScrollBack.dy, greaterThan(afterScrollUp.dy));
    });

    testWidgets('列表区左滑先切创作二级 Tab，越界后才切一级 Tab', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester, count: 20);

      final swipeSurface = find.byType(CustomScrollView);

      for (var i = 0; i < UserProfileUIConfig.creationSubTabs.length - 1; i++) {
        await tester.fling(
          swipeSurface,
          const Offset(-420, 0),
          1200,
          warnIfMissed: false,
        );
        await tester.pumpAndSettle();
        expect(find.byType(ProfileCirclesTab), findsNothing);
      }

      await tester.fling(
        swipeSurface,
        const Offset(-420, 0),
        1200,
        warnIfMissed: false,
      );
      await tester.pumpAndSettle();

      expect(find.byType(ProfileCirclesTab), findsOneWidget);
    });

    testWidgets('一级 tab 吸顶后切换圈子与互动不会把整页重置到 tab 下方', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester, count: 20);

      await tester.drag(find.byType(CustomScrollView), const Offset(0, -900));
      await tester.pumpAndSettle();

      final summaryFinder = find.byKey(
        const ValueKey<String>('profile-shell-summary-card'),
      );

      final summaryBefore = tester.getTopLeft(summaryFinder).dy;
      final circlesTab = _pinnedPrimaryTab('圈子').evaluate().isNotEmpty
          ? _pinnedPrimaryTab('圈子')
          : _inlinePrimaryTab('圈子');
      final interactionTab = _pinnedPrimaryTab('互动').evaluate().isNotEmpty
          ? _pinnedPrimaryTab('互动')
          : _inlinePrimaryTab('互动');

      await tester.tap(circlesTab);
      await tester.pumpAndSettle();
      final summaryAfterCircles = tester.getTopLeft(summaryFinder).dy;
      expect(summaryAfterCircles, closeTo(summaryBefore, 8));
      expect(find.text('极简摄影俱乐部'), findsOneWidget);

      await tester.tap(interactionTab);
      await tester.pumpAndSettle();
      final summaryAfterInteraction = tester.getTopLeft(summaryFinder).dy;
      expect(summaryAfterInteraction, closeTo(summaryBefore, 8));
      expect(find.byType(ProfileInteractionTab), findsOneWidget);
    });

    testWidgets('创作二级 tab 与列表首屏之间没有异常大留白', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester, count: 20);

      final tabsFinder = find.byKey(
        const ValueKey<String>('profile-works-secondary-tabs'),
      );
      final gridFinder = find.byKey(
        const ValueKey<String>('profile-works-grid'),
      );
      final gap =
          tester.getTopLeft(gridFinder).dy -
          tester.getBottomLeft(tabsFinder).dy;

      expect(gap, greaterThanOrEqualTo(0));
      expect(gap, lessThanOrEqualTo(24));
    });
  });

  group('ProfileShell — 暗色模式 (T61)', () {
    testWidgets('暗色模式下 mine 模式渲染不崩溃', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(
        _scopedApp(mode: ProfileMode.mine, themeMode: ThemeMode.dark),
      );
      await _pumpFrames(tester);
      expect(find.text('创作'), findsOneWidget);
      expect(find.byIcon(CupertinoIcons.settings), findsOneWidget);
    });

    testWidgets('暗色模式下 other 模式渲染不崩溃', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(
        _scopedApp(mode: ProfileMode.other, themeMode: ThemeMode.dark),
      );
      await _pumpFrames(tester);
      expect(find.text('关注'), findsAtLeastNWidgets(1));
      expect(
        find.text(UITextConstants.profileDirectMessage),
        findsAtLeastNWidgets(1),
      );
    });

    testWidgets('AnnotatedRegion 存在于渲染树', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester);
      expect(
        find.byWidgetPredicate(
          (w) => w is AnnotatedRegion<SystemUiOverlayStyle>,
        ),
        findsAtLeastNWidgets(1),
      );
    });
  });

  group('ProfileShell — 错误态渲染', () {
    testWidgets('空 userId 不崩溃', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine, userId: ''));
      await _pumpFrames(tester);
      expect(find.text('创作'), findsOneWidget);
    });
  });
}

class _NoNetworkHttpOverrides extends HttpOverrides {}

Finder _inlinePrimaryTab(String label) {
  return find.descendant(
    of: find.byKey(const ValueKey<String>('profile-shell-primary-tabs-inline')),
    matching: find.text(label),
  );
}

Finder _pinnedPrimaryTab(String label) {
  return find.descendant(
    of: find.byKey(const ValueKey<String>('profile-shell-primary-tabs-pinned')),
    matching: find.text(label),
  );
}

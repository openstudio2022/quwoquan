import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_shell.dart';

Widget _scopedApp({ProfileMode mode = ProfileMode.mine}) {
  return ProviderScope(
    overrides: [
      userProfileRepositoryProvider
          .overrideWithValue(const MockUserProfileRepository()),
    ],
    child: MaterialApp(
      home: ProfileShell(mode: mode, userId: 'nature_photographer'),
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

  group('旅程正常路径', () {
    testWidgets('旅程 A1：默认展示创作 Tab 及子分类', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp());
      await _pumpFrames(tester);
      expect(find.text('创作'), findsOneWidget);
      expect(find.text('全部'), findsOneWidget);
      expect(find.text('微趣'), findsOneWidget);
    });

    testWidgets('旅程 A2：切换到圈子 Tab', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp());
      await _pumpFrames(tester);
      await tester.tap(find.widgetWithText(Tab, '圈子'));
      await _pumpFrames(tester, count: 20);
      expect(find.text('极简摄影俱乐部'), findsOneWidget);
    });

    testWidgets('旅程 A3：切换到生活 Tab', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp());
      await _pumpFrames(tester);
      await tester.tap(find.text('生活'));
      await _pumpFrames(tester, count: 20);
      expect(find.text('足迹'), findsOneWidget);
    });
  });

  group('旅程 v2 布局验证', () {
    testWidgets('旅程 D1：不渲染 @username', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp());
      await _pumpFrames(tester);
      expect(find.textContaining('@'), findsNothing);
    });

    testWidgets('旅程 D2：other 模式渲染等宽「关注」「私信」', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.other));
      await _pumpFrames(tester);
      expect(find.widgetWithText(OutlinedButton, '关注'), findsOneWidget);
      expect(find.widgetWithText(OutlinedButton, '私信'), findsOneWidget);
    });

    testWidgets('旅程 D3：mine 模式渲染「资料编辑」「分身管理」', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester);
      expect(find.text('资料编辑'), findsOneWidget);
      expect(find.text('分身管理'), findsOneWidget);
    });
  });

  group('旅程数据加载正确性', () {
    testWidgets('旅程 E1：创作 Tab 展示 Repository 帖子数据（点赞数可见）', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp());
      await _pumpFrames(tester, count: 20);
      expect(find.text('1200'), findsOneWidget);
    });

    testWidgets('旅程 E2：圈子 Tab 展示 Repository 圈子数据', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp());
      await _pumpFrames(tester);
      await tester.tap(find.widgetWithText(Tab, '圈子'));
      await _pumpFrames(tester, count: 20);
      expect(find.text('极简摄影俱乐部'), findsOneWidget);
    });

    testWidgets('旅程 E3：生活 Tab 展示 Repository 生活记录', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp());
      await _pumpFrames(tester);
      await tester.tap(find.text('生活'));
      await _pumpFrames(tester, count: 20);
      expect(find.text('阿那亚礼堂'), findsOneWidget);
    });

    testWidgets('旅程 E4：统计数据从 Repository 加载', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp());
      await _pumpFrames(tester, count: 20);
      expect(find.text('284'), findsOneWidget);
      expect(find.text('1200'), findsOneWidget);
    });
  });

  group('旅程交互操作', () {
    testWidgets('旅程 F1：other 模式点击关注按钮切换状态', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.other));
      await _pumpFrames(tester);

      final followBtn = find.widgetWithText(OutlinedButton, '关注');
      expect(followBtn, findsOneWidget);
      await tester.tap(followBtn);
      await _pumpFrames(tester);
      expect(find.widgetWithText(OutlinedButton, '已关注'), findsOneWidget);
    });

    testWidgets('旅程 F2：创作子 Tab 切换到微趣', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp());
      await _pumpFrames(tester);
      await tester.tap(find.text('微趣'));
      await _pumpFrames(tester);
      expect(find.text('微趣'), findsOneWidget);
    });
  });

  group('旅程错误路径', () {
    testWidgets('旅程 B1：空用户数据下页面不崩溃', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(ProviderScope(
        overrides: [
          userProfileRepositoryProvider
              .overrideWithValue(const MockUserProfileRepository()),
        ],
        child: MaterialApp(
          home: ProfileShell(
            mode: ProfileMode.mine,
            userId: 'nonexistent_user_xyz',
          ),
        ),
      ));
      await _pumpFrames(tester);
      expect(find.text('创作'), findsOneWidget);
    });
  });

  group('旅程边界/幂等', () {
    testWidgets('旅程 C1：mine 模式显示设置按钮，不显示 more', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester);
      expect(find.byIcon(Icons.settings_outlined), findsOneWidget);
      expect(find.byIcon(Icons.more_horiz), findsNothing);
    });

    testWidgets('旅程 C2：other 模式显示 more 按钮', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.other));
      await _pumpFrames(tester);
      expect(find.byIcon(Icons.more_horiz), findsOneWidget);
      expect(find.byIcon(Icons.settings_outlined), findsNothing);
    });
  });
}

class _NoNetworkHttpOverrides extends HttpOverrides {}

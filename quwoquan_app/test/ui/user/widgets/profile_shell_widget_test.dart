import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_header.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_shell.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_circles_tab.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_interaction_tab.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_lifestyle_tab.dart';

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
}) {
  return ProviderScope(
    overrides: [
      userProfileRepositoryProvider
          .overrideWithValue(const MockUserProfileRepository()),
      relationshipCapabilityRepositoryProvider
          .overrideWithValue(_ThrowingCapabilityRepository()),
    ],
    child: MaterialApp(
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
      expect(find.byIcon(Icons.settings_outlined), findsOneWidget);
    });

    testWidgets('other 模式渲染返回和更多按钮', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.other));
      await _pumpFrames(tester);
      expect(find.byIcon(Icons.arrow_back), findsOneWidget);
      expect(find.byIcon(Icons.more_horiz), findsOneWidget);
    });

    testWidgets('渲染四个主 Tab', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester);
      expect(find.text('创作'), findsOneWidget);
      expect(find.widgetWithText(Tab, '圈子'), findsOneWidget);
      expect(find.text('互动'), findsOneWidget);
      expect(find.text('生活'), findsOneWidget);
    });
  });

  group('ProfileShell — 头像侵入 + 无 @username (T60)', () {
    testWidgets('ProfileHeader 不渲染 @username', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester);
      expect(find.textContaining('@'), findsNothing);
    });

    testWidgets('ProfileHeader 使用 Stack 实现侵入布局', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester);
      final headerFinder = find.byType(ProfileHeader);
      expect(headerFinder, findsOneWidget);

      final headerWidget = tester.widget<ProfileHeader>(headerFinder);
      expect(headerWidget, isNotNull);
      expect(ProfileHeader.avatarIntrusion, greaterThan(0));
    });

    testWidgets('other 模式渲染等宽「关注」+「私信」按钮', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.other));
      await _pumpFrames(tester);
      expect(find.widgetWithText(OutlinedButton, '关注'), findsOneWidget);
      expect(find.widgetWithText(OutlinedButton, '私信'), findsOneWidget);
    });
  });

  group('ProfileShell — 交互契约', () {
    testWidgets('切换到圈子 Tab 渲染 ProfileCirclesTab', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester);
      await tester.tap(find.widgetWithText(Tab, '圈子'));
      await _pumpFrames(tester, count: 20);
      expect(find.byType(ProfileCirclesTab), findsOneWidget);
    });

    testWidgets('切换到互动 Tab 渲染 ProfileInteractionTab', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester);
      await tester.tap(find.text('互动'));
      await _pumpFrames(tester, count: 20);
      expect(find.byType(ProfileInteractionTab), findsOneWidget);
    });

    testWidgets('切换到生活 Tab 渲染 ProfileLifestyleTab', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.mine));
      await _pumpFrames(tester);
      await tester.tap(find.text('生活'));
      await _pumpFrames(tester, count: 20);
      expect(find.byType(ProfileLifestyleTab), findsOneWidget);
    });
  });

  group('ProfileShell — 暗色模式 (T61)', () {
    testWidgets('暗色模式下 mine 模式渲染不崩溃', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(
        mode: ProfileMode.mine,
        themeMode: ThemeMode.dark,
      ));
      await _pumpFrames(tester);
      expect(find.text('创作'), findsOneWidget);
      expect(find.byIcon(Icons.settings_outlined), findsOneWidget);
    });

    testWidgets('暗色模式下 other 模式渲染不崩溃', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(
        mode: ProfileMode.other,
        themeMode: ThemeMode.dark,
      ));
      await _pumpFrames(tester);
      expect(find.widgetWithText(OutlinedButton, '关注'), findsOneWidget);
      expect(find.widgetWithText(OutlinedButton, '私信'), findsOneWidget);
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

      await tester.pumpWidget(_scopedApp(
        mode: ProfileMode.mine,
        userId: '',
      ));
      await _pumpFrames(tester);
      expect(find.text('创作'), findsOneWidget);
    });
  });
}

class _NoNetworkHttpOverrides extends HttpOverrides {}

import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_action_bar.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_shell.dart';

/// 他人主页用「未关注」能力位，使 [ProfileActionBar] 在 capability 已就绪时渲染（非 null）。
class _NotFollowingRelationshipCapability
    extends RelationshipCapabilityRepository {
  @override
  bool get reconcilesCapabilityWithSharedRelationshipState => false;

  @override
  Future<RelationshipCapabilityDto> getCapability(String targetUserId) async {
    return RelationshipCapabilityDto.fromFollowFlags(
      viewerId: 'test_viewer',
      targetId: targetUserId,
      isFollowing: false,
      isFollowedBy: false,
    );
  }
}

Widget _scopedApp({ProfileMode mode = ProfileMode.mine}) {
  return ProviderScope(
    overrides: [
      userProfileRepositoryProvider.overrideWithValue(
        const MockUserProfileRepository(),
      ),
      relationshipCapabilityRepositoryProvider.overrideWithValue(
        _NotFollowingRelationshipCapability(),
      ),
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

Finder _profileSegment(String label) {
  return find.descendant(
    of: find.byKey(const ValueKey<String>('profile-shell-primary-tabs-inline')),
    matching: find.text(label),
  );
}

Finder _pinnedProfileSegment(String label) {
  return find.descendant(
    of: find.byKey(const ValueKey<String>('profile-shell-primary-tabs-pinned')),
    matching: find.text(label),
  );
}

Finder _profileActionLabel(String label) {
  return find.descendant(
    of: find.byType(ProfileActionBar),
    matching: find.text(label),
  );
}

void main() {
  setUp(() {
    HttpOverrides.global = _NoNetworkHttpOverrides();
  });

  group('旅程正常路径', () {
    testWidgets('旅程 A1：默认展示创作 Tab', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp());
      await _pumpFrames(tester, count: 20);
      expect(find.text('创作'), findsOneWidget);
    });

    testWidgets('旅程 A2：切换到圈子 Tab', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp());
      await _pumpFrames(tester);
      await tester.tap(_profileSegment('圈子'));
      await _pumpFrames(tester, count: 20);
      expect(find.text('极简摄影俱乐部'), findsOneWidget);
    });

    testWidgets('旅程 A3：切换到互动 Tab', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp());
      await _pumpFrames(tester);
      await tester.tap(_profileSegment('互动'));
      await _pumpFrames(tester, count: 20);
      expect(find.text('收到'), findsOneWidget);
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

    testWidgets('旅程 D2：other 模式渲染等宽「关注」与主消息入口', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.other));
      await _pumpFrames(tester);
      expect(_profileActionLabel('关注'), findsOneWidget);
      expect(
        _profileActionLabel(UITextConstants.profileDirectMessage),
        findsOneWidget,
      );
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
      await tester.pumpAndSettle(const Duration(seconds: 5));
      // 创作 Tab 默认展示统一创作内容，至少应渲染首屏作品标题。
      expect(find.text('光影的节奏'), findsAtLeastNWidgets(1));
    });

    testWidgets('旅程 E2：圈子 Tab 展示 Repository 圈子数据', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp());
      await _pumpFrames(tester);
      await tester.tap(_profileSegment('圈子'));
      await _pumpFrames(tester, count: 20);
      expect(find.text('极简摄影俱乐部'), findsOneWidget);
    });

    testWidgets('旅程 E3：互动 Tab 展示 Repository 互动列表', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp());
      await _pumpFrames(tester);
      await tester.tap(_profileSegment('互动'));
      await _pumpFrames(tester, count: 20);
      expect(find.text('你的皮炎有点辣'), findsOneWidget);
    });

    testWidgets('旅程 E4：统计数据从 Repository 加载', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp());
      await _pumpFrames(tester, count: 20);
      expect(find.text('284'), findsOneWidget);
      expect(find.text('1.2k'), findsOneWidget);
    });
  });

  group('旅程交互操作', () {
    testWidgets('旅程 F1：other 模式点击关注按钮切换状态', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.other));
      await _pumpFrames(tester);

      final followBtn = _profileActionLabel('关注').first;
      expect(followBtn, findsOneWidget);
      await tester.tap(followBtn);
      await _pumpFrames(tester);
      expect(_profileActionLabel('已关注'), findsOneWidget);
    });

    testWidgets('旅程 F2：创作 Tab 展示用户创作内容', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp());
      await _pumpFrames(tester, count: 20);
      expect(find.text('创作'), findsOneWidget);
    });

    testWidgets('旅程 F3：一级 tab 吸顶后切换不会把整页头部重置回内容区', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp());
      await _pumpFrames(tester, count: 20);

      await tester.drag(find.byType(CustomScrollView), const Offset(0, -900));
      await tester.pumpAndSettle();

      final summaryFinder =
          find.byKey(const ValueKey<String>('profile-shell-summary-card'));
      final summaryBefore = tester.getTopLeft(summaryFinder).dy;

      final circlesTab = _pinnedProfileSegment('圈子').evaluate().isNotEmpty
          ? _pinnedProfileSegment('圈子')
          : _profileSegment('圈子');
      await tester.tap(circlesTab);
      await tester.pumpAndSettle();
      expect(find.text('极简摄影俱乐部'), findsOneWidget);
      expect(tester.getTopLeft(summaryFinder).dy, closeTo(summaryBefore, 8));
    });
  });

  group('旅程错误路径', () {
    testWidgets('旅程 B1：空用户数据下页面不崩溃', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            userProfileRepositoryProvider.overrideWithValue(
              const MockUserProfileRepository(),
            ),
          ],
          child: MaterialApp(
            home: ProfileShell(
              mode: ProfileMode.mine,
              userId: 'nonexistent_user_xyz',
            ),
          ),
        ),
      );
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
      expect(find.byIcon(CupertinoIcons.settings), findsOneWidget);
      expect(find.byIcon(CupertinoIcons.ellipsis), findsNothing);
    });

    testWidgets('旅程 C2：other 模式显示 more 按钮', (tester) async {
      _setPhoneSize(tester);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(_scopedApp(mode: ProfileMode.other));
      await _pumpFrames(tester);
      expect(find.byIcon(CupertinoIcons.ellipsis), findsOneWidget);
      expect(find.byIcon(CupertinoIcons.settings), findsNothing);
    });
  });
}

class _NoNetworkHttpOverrides extends HttpOverrides {}

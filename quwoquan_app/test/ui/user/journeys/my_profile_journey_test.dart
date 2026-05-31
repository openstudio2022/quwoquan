import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_circles_tab.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_interaction_tab.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_lifestyle_tab.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_shell.dart';

/// T4 旅程：我的主页一级 4 Tab（创作/圈子/互动/生活）端到端可达，
/// 生活 Tab 走 codegen 子页 + contract seed 渲染真实记录。
class _NoNetworkHttpOverrides extends HttpOverrides {}

class _ThrowingCapabilityRepository extends RelationshipCapabilityRepository {
  @override
  bool get reconcilesCapabilityWithSharedRelationshipState => false;

  @override
  Future<RelationshipCapabilityDto> getCapability(String targetUserId) {
    return Future.error(StateError('capability unavailable in test'));
  }
}

Widget _scopedApp() {
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
      theme: ThemeData.light(),
      home: const ProfileShell(
        mode: ProfileMode.mine,
        userId: 'nature_photographer',
      ),
    ),
  );
}

void _setPhoneSize(WidgetTester tester) {
  tester.view.physicalSize = const Size(1080, 2400);
  tester.view.devicePixelRatio = 3.0;
}

Future<void> _pumpFrames(WidgetTester tester, {int count = 20}) async {
  for (var i = 0; i < count; i++) {
    await tester.pump(const Duration(milliseconds: 80));
  }
}

Finder _inlinePrimaryTab(String label) {
  return find.descendant(
    of: find.byKey(const ValueKey<String>('profile-shell-primary-tabs-inline')),
    matching: find.text(label),
  );
}

void main() {
  setUp(() {
    HttpOverrides.global = _NoNetworkHttpOverrides();
  });

  testWidgets('我的主页可依次浏览 创作→圈子→互动→生活 四个一级 Tab', (tester) async {
    _setPhoneSize(tester);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(_scopedApp());
    await _pumpFrames(tester);

    // 默认创作 Tab：二级子页存在。
    expect(
      find.byKey(const ValueKey<String>('profile-works-secondary-tabs')),
      findsOneWidget,
    );

    await tester.tap(_inlinePrimaryTab('圈子'));
    await _pumpFrames(tester);
    expect(find.byType(ProfileCirclesTab), findsOneWidget);

    await tester.tap(_inlinePrimaryTab('互动'));
    await _pumpFrames(tester);
    expect(find.byType(ProfileInteractionTab), findsOneWidget);

    await tester.tap(_inlinePrimaryTab('生活'));
    await _pumpFrames(tester);
    expect(find.byType(ProfileLifestyleTab), findsOneWidget);
    expect(find.text('足迹'), findsOneWidget);
    expect(find.text('阿那亚礼堂'), findsOneWidget);
  });
}

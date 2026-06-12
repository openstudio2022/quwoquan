import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/cloud/user/generated/user_profile_ui_config.g.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_lifestyle_tab.dart';

/// 生活 Tab：codegen `lifestyleSubTabs` 驱动子页清单 + 按 `LifeItemCategory` 过滤。
/// 锁定 V5 契约：子页文案来自 metadata labelKey（无端侧硬编码），切换子页只显示对应分类记录。
class _NoNetworkHttpOverrides extends HttpOverrides {}

Widget _scoped({String userId = 'nature_photographer'}) {
  return ProviderScope(
    overrides: [
      userProfileRepositoryProvider.overrideWithValue(
        const MockUserProfileRepository(),
      ),
    ],
    child: MaterialApp(
      theme: ThemeData.light(),
      home: Scaffold(
        body: ProfileLifestyleTab(
          mode: ProfileMode.mine,
          userId: userId,
          isDark: false,
        ),
      ),
    ),
  );
}

Future<void> _pumpFrames(WidgetTester tester, {int count = 10}) async {
  for (var i = 0; i < count; i++) {
    await tester.pump(const Duration(milliseconds: 80));
  }
}

void main() {
  setUp(() {
    HttpOverrides.global = _NoNetworkHttpOverrides();
  });

  testWidgets('四个子页来自 codegen lifestyleSubTabs（无硬编码）', (tester) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    // codegen 契约：lifestyleSubTabs 恰为 footprint/soul/taste/private 四项且带 lifeCategory。
    expect(UserProfileUIConfig.lifestyleSubTabs.length, 4);
    expect(
      UserProfileUIConfig.lifestyleSubTabs.map((t) => t.lifeCategory).toList(),
      <String>['footprint', 'soul', 'taste', 'private'],
    );

    await tester.pumpWidget(_scoped());
    await _pumpFrames(tester);

    expect(find.text(UITextConstants.lifestyleSubFootprint), findsOneWidget);
    expect(find.text(UITextConstants.lifestyleSubSoul), findsOneWidget);
    expect(find.text(UITextConstants.lifestyleSubTaste), findsOneWidget);
    expect(find.text(UITextConstants.lifestyleSubPrivate), findsOneWidget);
  });

  testWidgets('默认显示 footprint 分类记录，切换子页只显示对应分类', (tester) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(_scoped());
    await _pumpFrames(tester);

    // 默认 footprint：只显示足迹记录，其他分类记录不在树中。
    expect(find.text('阿那亚礼堂'), findsOneWidget);
    expect(find.text('《摄影的哲学》'), findsNothing);

    // 切到「书影音」(soul)：只显示 soul 记录。
    await tester.tap(find.text(UITextConstants.lifestyleSubSoul));
    await _pumpFrames(tester);
    expect(find.text('《摄影的哲学》'), findsOneWidget);
    expect(find.text('阿那亚礼堂'), findsNothing);
  });
}

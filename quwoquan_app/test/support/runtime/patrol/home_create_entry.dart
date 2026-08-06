/// 共享 Patrol 辅助：到达首页壳 + 经底部导航「+」打开创作动作面板。
///
/// 背景：创作入口已从孤立的 DiscoveryPage（`discovery_page` / `discoveryCreateButton`
/// 已不在主导航 IndexedStack 中实例化）迁移到底部导航「+」（MainAppShell 的 create tab
/// → GlobalQuickActionSheet → CreateActionSheet）。债务用例原先等待 `discovery_page`
/// 并点击 `discoveryCreateButton`，在当前 App 结构下永远超时。此辅助统一指向现行入口。
///
/// 仅供 test/user_acceptance/journeys/** 复用，不进 lib、不改业务行为。
library;

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/l10n/copy/app_concept_constants.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';

/// 首页壳（HomePage = 底部导航落地 tab）的搜索 chrome key。
const homeSearchChromeKey = ValueKey<String>('home-search-chrome');

/// 等待首页壳就绪（落地后首帧路由完成）。
///
/// 顺序对齐已绿 journey 的 `_recoverToHomeFeed`：先等首页 chrome **出现在 widget 树**
/// （证明 HomePage 已构建，避免冷启动期误触发返回键把 App 退出），再仅在「存在但被
/// 全屏页/动作面板遮挡」时用原生返回键消解，最后等待其可见。
Future<void> waitForHomeShell(PatrolIntegrationTester $) async {
  bool existsInTree() => find.byKey(homeSearchChromeKey).evaluate().isNotEmpty;
  bool hittable() =>
      find.byKey(homeSearchChromeKey).hitTestable().evaluate().isNotEmpty;

  // 1) 先等首页 chrome 出现在树里（最多 30s，gamma 冷启动较慢）。
  final deadline = DateTime.now().add(const Duration(seconds: 30));
  while (!existsInTree() && DateTime.now().isBefore(deadline)) {
    await $.pump(const Duration(milliseconds: 400));
  }

  // 2) 已可见直接返回；否则仅在「存在但被遮挡」时用返回键消解遮挡层。
  for (var i = 0; i < 4; i++) {
    if (hittable()) {
      return;
    }
    if (!existsInTree()) {
      break;
    }
    await $.platform.android.pressBack();
    await $.pump(const Duration(milliseconds: 600));
  }

  await $(
    find.byKey(homeSearchChromeKey),
  ).waitUntilVisible(timeout: const Duration(seconds: 30));
}

/// 经底部导航「+」（语义标签「创作」）打开创作动作面板（动作优先入口）。
///
/// 打开后动作面板含 `createActionGallery` / `createActionWrite` /
/// `createActionCapture`，与旧 `discoveryCreateButton` 后的面板一致。
Future<void> openCreateActionSheet(PatrolIntegrationTester $) async {
  await waitForHomeShell($);
  await $(find.bySemanticsLabel(AppConceptConstants.create)).tap();
  await $(
    TestKeys.createActionGallery,
  ).waitUntilVisible(timeout: const Duration(seconds: 10));
}

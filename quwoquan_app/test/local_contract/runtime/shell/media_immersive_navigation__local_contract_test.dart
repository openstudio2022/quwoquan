// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-021
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/runtime/shell/web_main_app_shell.dart';
import 'package:quwoquan_app/runtime/shell/navigation/main_tab_registry.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';

import '../../../support/runtime/cloud_boundary_test_scope.dart';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/shell/shell_immersive_providers.dart';

void main() {
  testWidgets('Web基础hidden保留工具栏，媒体租约才隐藏且不重挂内容', (tester) async {
    tester.view.physicalSize = const Size(1280, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final container = ProviderContainer(
      overrides: sealedCloudBoundaryOverrides(),
    );
    addTearDown(container.dispose);
    final owner = container.read(bottomNavHiddenProvider.notifier);
    owner.setHidden(true);
    final contentKey = GlobalKey();
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp(
          home: WebMainAppShell(
            currentDestination: MainTabDestination.videoBook,
            currentLocation: AppRoutePaths.videoBook,
            backgroundColor: Colors.black,
            onPrimarySelected: (_) {},
            onGuestAuthGateOpened: () {},
            dependencies: WebMainAppShellDependencies(
              homeContextOptions: const [],
              buildContentFeed: ({
                required context,
                required ref,
                required isDark,
                required channelId,
                required onInitialContentPainted,
              }) => const SizedBox.shrink(),
              buildVideoBook: ({required onExitToHome}) =>
                  SizedBox(key: contentKey),
              buildChat: () => const SizedBox.shrink(),
              buildProfile: () => const SizedBox.shrink(),
              openCreate: (_, _) {},
              openStartGroupChat: (_, _) async {},
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    final contentElement = contentKey.currentContext;
    final header = find.byType(SliverPersistentHeader, skipOffstage: false);
    final originalExtent = tester
        .widget<SliverPersistentHeader>(header)
        .delegate
        .maxExtent;
    expect(originalExtent, greaterThan(0), reason: 'base hidden不隐藏Web工具栏');
    final first = owner.acquireMediaHidden();
    final second = owner.acquireMediaHidden();
    await tester.pump();
    expect(tester.widget<SliverPersistentHeader>(header).delegate.maxExtent, 0);
    expect(contentKey.currentContext, same(contentElement));
    first();
    first();
    await tester.pump();
    expect(tester.widget<SliverPersistentHeader>(header).delegate.maxExtent, 0);
    second();
    await tester.pump();
    expect(container.read(bottomNavHiddenProvider).hidden, isTrue);
    expect(
      tester.widget<SliverPersistentHeader>(header).delegate.maxExtent,
      originalExtent,
    );
    expect(contentKey.currentContext, same(contentElement));
    await tester.pumpWidget(const SizedBox.shrink());
    // 欢迎花瓣的既有35ms异步错峰在卸载后以mounted守卫终止。
    await tester.pump(const Duration(milliseconds: 35));
  });
  for (final initialHidden in [false, true]) {
    test('媒体隐藏租约恢复进入前 hidden=$initialHidden', () {
      final container = ProviderContainer();
      addTearDown(container.dispose);
      final owner = container.read(bottomNavHiddenProvider.notifier);
      owner.setHidden(initialHidden);
      expect(container.read(bottomNavHiddenProvider).baseHidden, initialHidden);
      expect(
        container.read(bottomNavHiddenProvider).mediaHidden,
        isFalse,
        reason: '基础底栏隐藏不隐藏Web欢迎区和工具栏',
      );
      final release = owner.acquireMediaHidden();
      expect(container.read(bottomNavHiddenProvider).mediaHidden, isTrue);
      expect(container.read(bottomNavHiddenProvider).hidden, isTrue);
      release();
      release();
      expect(container.read(bottomNavHiddenProvider).hidden, initialHidden);
      expect(container.read(bottomNavHiddenProvider).baseHidden, initialHidden);
      expect(container.read(bottomNavHiddenProvider).mediaHidden, isFalse);
    });
  }
  test('整个ProviderScope销毁后释放媒体租约无迟到通知', () {
    final container = ProviderContainer();
    final release = container
        .read(bottomNavHiddenProvider.notifier)
        .acquireMediaHidden();
    container.dispose();
    expect(release, returnsNormally);
    expect(release, returnsNormally);
  });

  test('旧媒体租约迟到释放不能覆盖新媒体或主壳状态', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);
    final owner = container.read(bottomNavHiddenProvider.notifier);
    final oldRelease = owner.acquireMediaHidden();
    final newRelease = owner.acquireMediaHidden();
    oldRelease();
    oldRelease();
    expect(container.read(bottomNavHiddenProvider).hidden, isTrue);
    expect(container.read(bottomNavHiddenProvider).mediaHidden, isTrue);
    owner.setHidden(true);
    newRelease();
    expect(container.read(bottomNavHiddenProvider).hidden, isTrue);
    expect(container.read(bottomNavHiddenProvider).baseHidden, isTrue);
    expect(container.read(bottomNavHiddenProvider).mediaHidden, isFalse);
    owner.setHidden(false);
    expect(container.read(bottomNavHiddenProvider).hidden, isFalse);
  });
}

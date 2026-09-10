// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/premium-stream-recommendation/spec.md#gwt-001.t2
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/page-layout-semantics/spec.md#gwt-003.t1
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/page-layout-semantics/spec.md#gwt-003.t2

import 'dart:ui' as ui;

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/icons/app_custom_icons.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/l10n/copy/app_concept_constants.dart';
import 'package:quwoquan_app/runtime/shell/bottom_navigation.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/immersive_engagement_bar.dart';

import '../../../support/runtime/bottom_navigation_test_host.dart';

void main() {
  test('视频书恢复原封面、页层、空心播放几何且各态等宽', () {
    for (final dimension in [24.0, 28.0, 32.0, 40.0]) {
      final size = Size.square(dimension);
      final scale = dimension / 24;
      expect(
        AppVideoBookIconGeometry.frontCoverRect(size),
        Rect.fromLTWH(3.75 * scale, 3 * scale, 14.25 * scale, 18 * scale),
      );
      expect(
        AppVideoBookIconGeometry.coverCornerRadius(size),
        closeTo(2.8 * scale, 0.0001),
      );
      final playBounds = AppVideoBookIconGeometry.playPath(size).getBounds();
      expect(playBounds.center.dy, closeTo(12 * scale, 0.01));
      expect(
        AppVideoBookIconGeometry.frontCoverRect(size)
            .contains(playBounds.topLeft),
        isTrue,
      );
      expect(
        AppVideoBookIconGeometry.rightPageLayerPath(size).getBounds().right,
        closeTo(20.2 * scale, 0.01),
      );
      for (final state in AppVideoBookIconState.values) {
        expect(
          AppVideoBookIconGeometry.strokeWidth(size, state: state),
          closeTo(1.24 * scale, 0.0001),
        );
      }
    }
  });

  testWidgets('视频书选中及禁用不填充、不加粗或改变轮廓', (tester) async {
    final painted = <List<int>>[];
    for (final state in AppVideoBookIconState.values) {
      final recorder = ui.PictureRecorder();
      AppVideoBookIconGeometry.paintIcon(
        Canvas(recorder),
        const Size.square(24),
        color: CupertinoColors.black,
        state: state,
      );
      final picture = recorder.endRecording();
      await tester.runAsync(() async {
        final image = await picture.toImage(24, 24);
        final bytes = await image.toByteData();
        painted.add(bytes!.buffer.asUint8List().toList());
        image.dispose();
        picture.dispose();
      });
    }
    expect(painted[1], painted[0]);
    expect(painted[2], painted[0]);
    // 封面内部与播放三角内部透明，防止恢复成实心书或实心播放。
    expect(painted[0][(6 * 24 + 6) * 4 + 3], 0);
    expect(painted[0][(12 * 24 + 10) * 4 + 3], 0);
  });

  for (final brightness in Brightness.values) {
    for (final width in [320.0, 393.0, 820.0]) {
      for (final bottomInset in [0.0, 34.0]) {
        for (final textScale in [1.0, 2.0]) {
          testWidgets(
            '底栏 ${brightness.name} w$width inset$bottomInset text$textScale 等分与热区',
            (tester) async {
              tester.view.physicalSize = Size(width, 900);
              tester.view.devicePixelRatio = 1;
              tester.view.viewPadding = FakeViewPadding(bottom: bottomInset);
              addTearDown(tester.view.reset);
              final semantics = tester.ensureSemantics();
              int? tapped;
              await tester.pumpWidget(
                bottomNavigationTestHost(
                  brightness: brightness,
                  textScale: textScale,
                  child: bottomNavigationUnderTest(
                    onTap: (index) => tapped = index,
                  ),
                ),
              );
              await tester.pumpAndSettle();

              final nav = find.byType(BottomNavigationWidget);
              final buttons = find.descendant(
                of: nav,
                matching: find.byType(CupertinoButton),
              );
              expect(buttons, findsNWidgets(5));
              final firstSize = tester.getSize(buttons.first);
              final centers = List.generate(
                5,
                (index) => tester.getCenter(buttons.at(index)),
              );
              for (var index = 0; index < 5; index++) {
                final hitSize = tester.getSize(buttons.at(index));
                expect(hitSize.width, closeTo(firstSize.width, 0.01));
                expect(
                  hitSize.height,
                  greaterThanOrEqualTo(index == 2 ? 48 : 44),
                );
                expect(
                  hitSize.width,
                  greaterThanOrEqualTo(index == 2 ? 48 : 44),
                );
                expect(centers[index].dy, closeTo(centers.first.dy, 0.01));
                if (index > 0) {
                  expect(
                    centers[index].dx - centers[index - 1].dx,
                    closeTo(firstSize.width, 0.01),
                  );
                }
              }
              expect(centers[2].dx, closeTo(width / 2, 0.01));
              final pill = find.descendant(
                of: buttons.at(2),
                matching: find.byType(Container),
              );
              expect(tester.getSize(pill), const Size(56, 40));
              expect(tester.getCenter(pill), centers[2]);
              final decoration =
                  tester.widget<Container>(pill).decoration! as BoxDecoration;
              expect(decoration.color, AppColors.primaryColor);
              expect(decoration.borderRadius, BorderRadius.circular(12));
              expect(decoration.boxShadow, isNull);
              expect(
                tester.widget<Icon>(find.byIcon(CupertinoIcons.plus)).size,
                22,
              );
              expect(find.byType(AppVideoBookIcon), findsOneWidget);
              expect(find.byIcon(CupertinoIcons.book), findsNothing);
              expect(find.text(AppConceptConstants.create), findsNothing);
              final createSemantic = find.bySemanticsLabel(
                AppConceptConstants.create,
              );
              expect(createSemantic, findsOneWidget);
              expect(
                tester.getSemantics(createSemantic),
                matchesSemantics(
                  label: AppConceptConstants.create,
                  isButton: true,
                  hasTapAction: true,
                  hasFocusAction: true,
                  isFocusable: true,
                ),
              );
              expect(tester.getSize(nav).height, 48 + bottomInset);
              expect(tester.takeException(), isNull);
              await tester.tap(buttons.at(2));
              expect(tapped, 2);
              semantics.dispose();
            },
          );
        }
      }
    }
  }

  testWidgets('主导航扩热区不改变沉浸互动栏高度', (tester) async {
    for (final entry in {
      320.0: 44.0,
      393.0: 46.0,
      820.0: 48.0,
      1200.0: 52.0,
    }.entries) {
      tester.view.physicalSize = Size(entry.key, 900);
      tester.view.devicePixelRatio = 1;
      for (final bottomInset in [0.0, 34.0]) {
        tester.view.viewPadding = FakeViewPadding(bottom: bottomInset);
        await tester.pumpWidget(
          bottomNavigationTestHost(child: bottomNavigationUnderTest()),
        );
        final context = tester.element(find.byType(BottomNavigationWidget));
        expect(
          AppSpacing.immersiveEngagementContentHeight(context),
          entry.value,
        );
        expect(
          AppSpacing.bottomNavBarHeight(context),
          greaterThanOrEqualTo(48),
        );
        expect(
          ImmersiveEngagementBar.reservedHeight(context),
          entry.value + bottomInset + AppSpacing.immersiveBottomChromeLift,
          reason: '检查真实互动栏消费者，不只验证未被使用的尺寸 token。',
        );
      }
    }
    addTearDown(tester.view.reset);
  });
}

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/content/media/filter_catalog_release/presentation/image_editor_page.dart';
import 'package:quwoquan_app/content/media/media_upload_session/presentation/media_reorderable_view.dart';
import 'package:quwoquan_app/core/constants/design_semantic_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';

/// 图片编辑器缩略图条接入统一拖拽组件后的回归守卫。
///
/// 守护两条「再次违规」红线：
/// 1. 结构：缩略图条必须由 [MediaReorderableView]（横条布局）承载，杜绝回退到不可重排的
///    ListView / ReorderableListView；
/// 2. 行为：长按缩略图拖动应提交重排，且重排时保持「当前预览图」不变——
///    把当前预览的首图拖到末尾后，顶栏 `位置文案` 由 `1/3` 变为 `3/3`。
void main() {
  Widget buildEditor({required void Function(Object?) onDone}) {
    return ProviderScope(
      child: MaterialApp(
        home: ImageEditorPage(
          initialPath: '/tmp/a.jpg',
          source: 'test',
          index: 0,
          total: 3,
          imagePaths: const <String>['/tmp/a.jpg', '/tmp/b.jpg', '/tmp/c.jpg'],
          onDone: onDone,
        ),
      ),
    );
  }

  testWidgets('缩略图条由统一拖拽组件承载且不回退到不可重排实现', (tester) async {
    await tester.pumpWidget(buildEditor(onDone: (_) {}));
    await tester.pumpAndSettle();

    expect(find.byType(MediaReorderableView), findsOneWidget);
    expect(find.byType(ReorderableListView), findsNothing);
  });

  testWidgets('缩略图条左对齐，切页仅 reveal 当前图而不再强制居中', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      ProviderScope(
        child: MaterialApp(
          home: ImageEditorPage(
            initialPath: '/tmp/0.jpg',
            source: 'test',
            index: 0,
            total: 10,
            imagePaths: List<String>.generate(10, (index) => '/tmp/$index.jpg'),
            onDone: (_) {},
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final horizontalPad =
        AppSpacing.semantic[DesignSemanticConstants
            .container]?[DesignSemanticConstants.sm] ??
        AppSpacing.containerSm;
    final stripRect = tester.getRect(find.byType(MediaReorderableView));
    final firstThumbRect = tester.getRect(
      find.byKey(const ValueKey<String>('image-editor-thumb-/tmp/0.jpg')),
    );
    expect(firstThumbRect.left, closeTo(stripRect.left + horizontalPad, 1));

    for (var i = 0; i < 6; i++) {
      await tester.drag(find.byType(PageView), const Offset(-390, 0));
      await tester.pumpAndSettle();
    }

    final stripScrollable = tester.state<ScrollableState>(
      find.descendant(
        of: find.byType(MediaReorderableView),
        matching: find.byType(Scrollable),
      ),
    );
    final thumbStride = AppSpacing.bottomNavHeight + AppSpacing.intraGroupSm;
    final revealOffset =
        (horizontalPad + (6 * thumbStride) + AppSpacing.bottomNavHeight) -
        stripScrollable.position.viewportDimension +
        horizontalPad;
    final centeredOffset =
        (6 * thumbStride) -
        stripScrollable.position.viewportDimension / 2 +
        thumbStride / 2;
    expect(
      stripScrollable.position.pixels,
      closeTo(
        revealOffset.clamp(0.0, stripScrollable.position.maxScrollExtent),
        1,
      ),
    );
    expect(
      stripScrollable.position.pixels,
      lessThan(centeredOffset - 40),
      reason: '切页应仅滚到可见，不再把选中缩略图强制停靠到正中',
    );
  });

  testWidgets('长按缩略图悬停时兄弟项先让位，松手后提交重排并保持当前预览图', (tester) async {
    await tester.pumpWidget(buildEditor(onDone: (_) {}));
    await tester.pumpAndSettle();

    // 初始预览首图，顶栏位置文案为 1/3。
    expect(find.text('1/3'), findsOneWidget);

    final firstThumbRectBefore = tester.getRect(
      find.byKey(const ValueKey<String>('image-editor-thumb-/tmp/a.jpg')),
    );
    final secondThumbRectBefore = tester.getRect(
      find.byKey(const ValueKey<String>('image-editor-thumb-/tmp/b.jpg')),
    );
    final thirdThumbCenterBefore = tester.getCenter(
      find.byKey(const ValueKey<String>('image-editor-thumb-/tmp/c.jpg')),
    );
    final start = tester.getCenter(
      find.byKey(const ValueKey<String>('image-editor-thumb-/tmp/a.jpg')),
    );

    final gesture = await tester.startGesture(start);
    await tester.pump(kLongPressTimeout + const Duration(milliseconds: 80));
    // 向右越过其余缩略图，落点钳制到末尾槽位。
    await gesture.moveBy(
      (thirdThumbCenterBefore - start) + const Offset(30, 0),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 220));

    final bRect = tester.getRect(
      find.byKey(const ValueKey<String>('image-editor-thumb-/tmp/b.jpg')),
    );
    final cRect = tester.getRect(
      find.byKey(const ValueKey<String>('image-editor-thumb-/tmp/c.jpg')),
    );
    expect(bRect.left, closeTo(firstThumbRectBefore.left, 1));
    expect(cRect.left, closeTo(secondThumbRectBefore.left, 1));

    await gesture.up();
    await tester.pumpAndSettle();

    // 当前预览仍是原首图（a），但其顺序已移动到末尾 → 位置文案变为 3/3。
    expect(find.text('3/3'), findsOneWidget);
    expect(find.text('1/3'), findsNothing);
  });
}

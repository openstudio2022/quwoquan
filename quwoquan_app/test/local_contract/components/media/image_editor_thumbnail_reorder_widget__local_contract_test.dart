import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/media/image/editor/image_editor_page.dart';
import 'package:quwoquan_app/components/media/reorderable/media_reorderable_view.dart';

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

  testWidgets('长按缩略图拖到末尾会提交重排并保持当前预览图', (tester) async {
    await tester.pumpWidget(buildEditor(onDone: (_) {}));
    await tester.pumpAndSettle();

    // 初始预览首图，顶栏位置文案为 1/3。
    expect(find.text('1/3'), findsOneWidget);

    final strip = find.byType(MediaReorderableView);
    final firstThumb = find
        .descendant(of: strip, matching: find.byType(AnimatedPositioned))
        .first;
    final start = tester.getCenter(firstThumb);

    final gesture = await tester.startGesture(start);
    await tester.pump(kLongPressTimeout + const Duration(milliseconds: 80));
    // 向右越过其余缩略图，落点钳制到末尾槽位。
    await gesture.moveBy(const Offset(260, 0));
    await tester.pump(const Duration(milliseconds: 40));
    await gesture.up();
    await tester.pumpAndSettle();

    // 当前预览仍是原首图（a），但其顺序已移动到末尾 → 位置文案变为 3/3。
    expect(find.text('3/3'), findsOneWidget);
    expect(find.text('1/3'), findsNothing);
  });
}

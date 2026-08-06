import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/presentation/media_reorderable_view.dart';

/// L1 合约测试：MediaReorderableView 长按拖拽重排的索引语义（唯一交互真相源）。
///
/// 覆盖：横条正向/反向、网格二维、末尾占位「移到末尾」、禁用/单项不触发。
/// onReorder 采用 Flutter 标准 (oldIndex, newIndex) 约定。
Future<void> _pumpView(
  WidgetTester tester, {
  required int itemCount,
  required MediaReorderableLayout layout,
  required void Function(int, int) onReorder,
  int crossAxisCount = 1,
  bool enabled = true,
  Widget? trailing,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: Align(
          alignment: Alignment.topLeft,
          child: SizedBox(
            width: 400,
            height: 400,
            child: MediaReorderableView(
              itemCount: itemCount,
              layout: layout,
              crossAxisCount: crossAxisCount,
              spacing: 0,
              runSpacing: 0,
              enabled: enabled,
              itemSize: const Size(60, 60),
              trailing: trailing,
              onReorder: onReorder,
              itemBuilder: (context, index, isDragging) => Container(
                key: ValueKey<String>('item-$index'),
                color: Colors.blue,
                alignment: Alignment.center,
                child: Text('$index'),
              ),
            ),
          ),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> _dragBy(WidgetTester tester, int fromIndex, Offset delta) async {
  final start = tester.getCenter(
    find.byKey(ValueKey<String>('item-$fromIndex')),
  );
  final gesture = await tester.startGesture(start);
  // 触发 onLongPressStart。
  await tester.pump(kLongPressTimeout + const Duration(milliseconds: 30));
  await gesture.moveBy(delta);
  await tester.pump();
  await gesture.up();
  await tester.pumpAndSettle();
}

Future<TestGesture> _startLongPressDrag(
  WidgetTester tester,
  int fromIndex,
) async {
  final start = tester.getCenter(
    find.byKey(ValueKey<String>('item-$fromIndex')),
  );
  final gesture = await tester.startGesture(start);
  await tester.pump(kLongPressTimeout + const Duration(milliseconds: 30));
  return gesture;
}

void main() {
  testWidgets('横条 正向：item0 拖到 slot2 → onReorder(0, 3)', (tester) async {
    (int, int)? result;
    await _pumpView(
      tester,
      itemCount: 4,
      layout: MediaReorderableLayout.strip,
      onReorder: (o, n) => result = (o, n),
    );
    // 60px 一格、无间距：移到第 2 槽中心 = +120px。
    await _dragBy(tester, 0, const Offset(120, 0));
    expect(result, (0, 3));
  });

  testWidgets('横条内容少于视口时首项仍贴左起始，不会视觉居中', (tester) async {
    await _pumpView(
      tester,
      itemCount: 3,
      layout: MediaReorderableLayout.strip,
      onReorder: (_, _) {},
    );

    final stripRect = tester.getRect(find.byType(MediaReorderableView));
    final firstRect = tester.getRect(
      find.byKey(const ValueKey<String>('item-0')),
    );
    expect(firstRect.left, closeTo(stripRect.left, 0.5));
  });

  testWidgets('横条拖拽悬停到第 4 槽位时，后续兄弟项会在松手前即时前移让位', (tester) async {
    (int, int)? result;
    await _pumpView(
      tester,
      itemCount: 4,
      layout: MediaReorderableLayout.strip,
      onReorder: (o, n) => result = (o, n),
    );

    final item0RectBefore = tester.getRect(
      find.byKey(const ValueKey<String>('item-0')),
    );
    final item1RectBefore = tester.getRect(
      find.byKey(const ValueKey<String>('item-1')),
    );
    final item2RectBefore = tester.getRect(
      find.byKey(const ValueKey<String>('item-2')),
    );
    final item3CenterBefore = tester.getCenter(
      find.byKey(const ValueKey<String>('item-3')),
    );
    final gesture = await _startLongPressDrag(tester, 0);
    await gesture.moveBy(
      (item3CenterBefore - item0RectBefore.center) + const Offset(30, 0),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 220));

    final item1Rect = tester.getRect(
      find.byKey(const ValueKey<String>('item-1')),
    );
    final item2Rect = tester.getRect(
      find.byKey(const ValueKey<String>('item-2')),
    );
    final item3Rect = tester.getRect(
      find.byKey(const ValueKey<String>('item-3')),
    );
    expect(item1Rect.left, closeTo(item0RectBefore.left, 0.5));
    expect(item2Rect.left, closeTo(item1RectBefore.left, 0.5));
    expect(item3Rect.left, closeTo(item2RectBefore.left, 0.5));
    expect(result, isNull, reason: '悬停让位阶段不应提前提交最终顺序');

    await gesture.up();
    await tester.pumpAndSettle();
    expect(result, (0, 4));
  });

  testWidgets('横条拖拽悬停到第 1 槽位时，前方区间兄弟项会在松手前整体后移', (tester) async {
    (int, int)? result;
    await _pumpView(
      tester,
      itemCount: 4,
      layout: MediaReorderableLayout.strip,
      onReorder: (o, n) => result = (o, n),
    );

    final item1RectBefore = tester.getRect(
      find.byKey(const ValueKey<String>('item-1')),
    );
    final item2RectBefore = tester.getRect(
      find.byKey(const ValueKey<String>('item-2')),
    );
    final item3RectBefore = tester.getRect(
      find.byKey(const ValueKey<String>('item-3')),
    );
    final item0RectBefore = tester.getRect(
      find.byKey(const ValueKey<String>('item-0')),
    );
    final item0CenterBefore = item0RectBefore.center;
    final gesture = await _startLongPressDrag(tester, 3);
    await gesture.moveBy(
      (item0CenterBefore - item3RectBefore.center) - const Offset(30, 0),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 220));

    final item0Rect = tester.getRect(
      find.byKey(const ValueKey<String>('item-0')),
    );
    final item1Rect = tester.getRect(
      find.byKey(const ValueKey<String>('item-1')),
    );
    final item2Rect = tester.getRect(
      find.byKey(const ValueKey<String>('item-2')),
    );
    expect(item0Rect.left, closeTo(item1RectBefore.left, 0.5));
    expect(item1Rect.left, closeTo(item2RectBefore.left, 0.5));
    expect(item2Rect.left, closeTo(item3RectBefore.left, 0.5));
    expect(result, isNull, reason: '悬停让位阶段不应提前提交最终顺序');

    await gesture.up();
    await tester.pumpAndSettle();
    expect(result, (3, 0));
  });

  testWidgets('横条 反向：item3 拖到 slot1 → onReorder(3, 1)', (tester) async {
    (int, int)? result;
    await _pumpView(
      tester,
      itemCount: 4,
      layout: MediaReorderableLayout.strip,
      onReorder: (o, n) => result = (o, n),
    );
    await _dragBy(tester, 3, const Offset(-120, 0));
    expect(result, (3, 1));
  });

  testWidgets('网格 2 列：item0 拖到 slot3 → onReorder(0, 4)', (tester) async {
    (int, int)? result;
    await _pumpView(
      tester,
      itemCount: 4,
      layout: MediaReorderableLayout.grid,
      crossAxisCount: 2,
      onReorder: (o, n) => result = (o, n),
    );
    // 槽位中心：0=(30,30), 3=(90,90)；位移 (60,60)。
    await _dragBy(tester, 0, const Offset(60, 60));
    expect(result, (0, 4));
  });

  testWidgets('末尾占位：拖到末尾占位区域 → 移到最后', (tester) async {
    (int, int)? result;
    await _pumpView(
      tester,
      itemCount: 3,
      layout: MediaReorderableLayout.strip,
      trailing: const SizedBox(width: 60, height: 60),
      onReorder: (o, n) => result = (o, n),
    );
    // item0 向右拖过末尾占位（slot3 区域，x>180）。
    await _dragBy(tester, 0, const Offset(220, 0));
    // rest = itemCount-1 = 2，d=0 → newIndex = 3。
    expect(result, (0, 3));
  });

  testWidgets('禁用时不触发重排', (tester) async {
    (int, int)? result;
    await _pumpView(
      tester,
      itemCount: 4,
      layout: MediaReorderableLayout.strip,
      enabled: false,
      onReorder: (o, n) => result = (o, n),
    );
    await _dragBy(tester, 0, const Offset(120, 0));
    expect(result, isNull);
  });

  testWidgets('单项时不触发重排', (tester) async {
    (int, int)? result;
    await _pumpView(
      tester,
      itemCount: 1,
      layout: MediaReorderableLayout.strip,
      onReorder: (o, n) => result = (o, n),
    );
    await _dragBy(tester, 0, const Offset(120, 0));
    expect(result, isNull);
  });
}

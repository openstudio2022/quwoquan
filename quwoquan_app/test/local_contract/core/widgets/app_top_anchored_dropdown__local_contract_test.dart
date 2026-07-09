import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/widgets/app_top_anchored_dropdown.dart';

/// [showAppTopAnchoredDropdown] 行为契约回归。
///
/// 守护「顶部锚定 + 自适应封顶 + 亮度层外点关闭」三条语义，防止后续误改回贴底浮层或丢失封顶。
void main() {
  const panelKey = ValueKey<String>('dropdown-panel');
  const optionKey = ValueKey<String>('dropdown-option');

  Future<BuildContext> pumpHost(WidgetTester tester) async {
    late BuildContext hostContext;
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) {
            hostContext = context;
            return const Scaffold(body: SizedBox.expand());
          },
        ),
      ),
    );
    return hostContext;
  }

  testWidgets('浮层锚定在 anchorTop，点击亮度层区域关闭并返回 null', (tester) async {
    final host = await pumpHost(tester);
    Object? result = 'unset';
    showAppTopAnchoredDropdown<String>(
      context: host,
      anchorTop: 120,
      scrimColor: const Color(0x66000000),
      barrierLabel: 'dismiss',
      builder: (context) =>
          Container(key: panelKey, height: 200, color: const Color(0xFF222222)),
    ).then((value) => result = value);
    await tester.pumpAndSettle();

    expect(find.byKey(panelKey), findsOneWidget);
    expect(tester.getTopLeft(find.byKey(panelKey)).dy, closeTo(120, 0.5));

    // 点击浮层下方的亮度层区域应关闭。
    await tester.tapAt(const Offset(10, 560));
    await tester.pumpAndSettle();
    expect(find.byKey(panelKey), findsNothing);
    expect(result, isNull);
  });

  testWidgets('浮层内选择经 Navigator.pop 回传结果', (tester) async {
    final host = await pumpHost(tester);
    Object? result = 'unset';
    showAppTopAnchoredDropdown<String>(
      context: host,
      anchorTop: 80,
      scrimColor: const Color(0x66000000),
      barrierLabel: 'dismiss',
      builder: (context) => Material(
        child: ListTile(
          key: optionKey,
          title: const Text('option'),
          onTap: () => Navigator.of(context).pop('picked'),
        ),
      ),
    ).then((value) => result = value);
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(optionKey));
    await tester.pumpAndSettle();
    expect(result, 'picked');
  });

  testWidgets('浮层高度封顶到 anchorTop 以下的可用区', (tester) async {
    tester.view.physicalSize = const Size(400, 600);
    tester.view.devicePixelRatio = 1;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    final host = await pumpHost(tester);
    const anchorTop = 500.0;
    showAppTopAnchoredDropdown<String>(
      context: host,
      anchorTop: anchorTop,
      scrimColor: const Color(0x66000000),
      barrierLabel: 'dismiss',
      builder: (context) => Container(
        key: panelKey,
        height: 1000,
        color: const Color(0xFF222222),
      ),
    );
    await tester.pumpAndSettle();

    final panelRect = tester.getRect(find.byKey(panelKey));
    // 内容想要 1000，但应被封顶到 600 - 500 = 100 的可用区内。
    expect(panelRect.height, lessThanOrEqualTo(100.5));
    expect(panelRect.bottom, lessThanOrEqualTo(600.5));
  });
}

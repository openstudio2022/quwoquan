// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/error-permission-display-semantics/spec.md#gwt-009

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/layout/app_terminal_viewport.dart';

void main() {
  testWidgets('终态按扣除底部遮挡后的真实可见视口居中', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      const CupertinoApp(
        home: AppViewportObstructionScope(
          obstruction: EdgeInsets.only(bottom: 100),
          child: AppTerminalViewport(
            padding: EdgeInsets.all(16),
            child: SizedBox(
              key: ValueKey<String>('terminal-body'),
              width: 120,
              height: 120,
            ),
          ),
        ),
      ),
    );

    expect(
      tester.getCenter(find.byKey(const ValueKey<String>('terminal-body'))).dy,
      moreOrLessEquals((844 - 100) / 2, epsilon: 0.1),
    );
  });

  testWidgets('无外层遮挡的详情页仍按完整 body 居中', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      const CupertinoApp(
        home: AppTerminalViewport(
          padding: EdgeInsets.all(16),
          child: SizedBox(
            key: ValueKey<String>('terminal-body'),
            width: 120,
            height: 120,
          ),
        ),
      ),
    );

    expect(
      tester.getCenter(find.byKey(const ValueKey<String>('terminal-body'))).dy,
      moreOrLessEquals(844 / 2, epsilon: 0.1),
    );
  });

  testWidgets('动态字体导致内容高于可见区域时仍可滚动访问', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 300));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      const CupertinoApp(
        home: AppViewportObstructionScope(
          obstruction: EdgeInsets.only(bottom: 80),
          child: AppTerminalViewport(
            padding: EdgeInsets.all(16),
            child: SizedBox(
              key: ValueKey<String>('tall-terminal-body'),
              width: 120,
              height: 420,
            ),
          ),
        ),
      ),
    );

    expect(find.byType(SingleChildScrollView), findsOneWidget);
    await tester.drag(
      find.byType(SingleChildScrollView),
      const Offset(0, -160),
    );
    await tester.pump();
    expect(
      tester
          .getTopLeft(find.byKey(const ValueKey<String>('tall-terminal-body')))
          .dy,
      lessThan(16),
    );
  });
}

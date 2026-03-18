import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/navigation/centered_scrollable_tab_bar.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_tab_page.dart';

Widget _buildApp() {
  return const ProviderScope(child: MaterialApp(home: AssistantTabPage()));
}

Future<void> _pumpFrames(WidgetTester tester, {int count = 12}) async {
  for (var i = 0; i < count; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}

void main() {
  testWidgets('私助列表区右滑可切回上一一级 Tab', (tester) async {
    await tester.pumpWidget(_buildApp());
    await _pumpFrames(tester);

    final swipeTarget = find.byType(ListView).evaluate().isNotEmpty
        ? find.byType(ListView).first
        : find.byType(CenteredScrollableTabBar);

    await tester.fling(swipeTarget, const Offset(420, 0), 1200);
    await _pumpFrames(tester, count: 6);

    expect(find.text('待办事项'), findsOneWidget);
  });
}

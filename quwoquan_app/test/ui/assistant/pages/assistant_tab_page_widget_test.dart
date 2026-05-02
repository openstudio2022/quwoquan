import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/navigation/centered_scrollable_tab_bar.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_tab_page.dart';
import 'package:quwoquan_app/ui/assistant/providers/personal_assistant_stream_controller.dart';

import '../../../common/assistant/assistant_scenario_fixtures.dart';

Widget _buildApp({AssistantScenarioPack? scenarioPack}) {
  return ProviderScope(
    overrides: [
      if (scenarioPack != null)
        assistantRepositoryProvider.overrideWithValue(
          ScenarioMockAssistantRepository(pack: scenarioPack),
        ),
    ],
    child: const MaterialApp(home: AssistantTabPage()),
  );
}

Future<void> _pumpFrames(WidgetTester tester, {int count = 12}) async {
  for (var i = 0; i < count; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}

void main() {
  testWidgets('端侧 alpha 找私助 stub stream 渲染后找小趣入口仍可回归', (tester) async {
    expect(CloudRuntimeConfig.appRuntimeEnv, 'alpha');
    expect(CloudRuntimeConfig.isValidAppRuntimeEnv, isTrue);
    final scenarioPack = loadAssistantScenarioPack();
    final scenario = scenarioPack
        .assistantTurnScenariosFor('alpha')
        .firstWhere((item) => item.id == 'weather_trip_basic');

    await tester.binding.setSurfaceSize(const Size(900, 1200));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(_buildApp(scenarioPack: scenarioPack));
    await _pumpFrames(tester);

    expect(find.text('找小趣'), findsOneWidget);
    expect(find.text('找私助'), findsOneWidget);

    await tester.tap(find.text('找私助'));
    await _pumpFrames(tester);
    expect(find.byKey(TestKeys.assistantChatInputField), findsOneWidget);
    expect(find.text('主动订阅'), findsNothing);
    expect(find.text('主动消息'), findsNothing);

    await tester.enterText(
      find.byKey(TestKeys.assistantChatInputField),
      scenario.question,
    );
    await tester.pump();
    await tester.tap(find.byKey(TestKeys.assistantSendButton));
    await _pumpFrames(tester, count: 12);

    expect(find.text(scenario.alphaMockStream.finalAnswer), findsWidgets);
    expect(find.textContaining('已完成处理'), findsWidgets);
    expect(find.textContaining('检索'), findsWidgets);
    final context = tester.element(find.byType(AssistantTabPage));
    final state = ProviderScope.containerOf(
      context,
    ).read(personalAssistantStreamControllerProvider);
    expect(
      state.events.map((event) => event.eventType),
      containsAll(scenario.expectedEvents),
    );

    await tester.tap(find.text('找小趣'));
    await _pumpFrames(tester, count: 8);

    expect(find.byKey(TestKeys.assistantDialogPage), findsOneWidget);
  });

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

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:quwoquan_app/assistant/transcript/persisted_timeline/persisted_timeline_turn_codec.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import '../common/assistant/assistant_eval_scenario_fixtures.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_tab_page.dart';
import 'package:quwoquan_app/ui/assistant/providers/personal_assistant_stream_controller.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('21 skill alpha/beta comparison evidence collector', (
    tester,
  ) async {
    final scenarioPack = loadAssistantEvalScenarioPack();
    final runtimeEnv = CloudRuntimeConfig.appRuntimeEnv;
    final scenarios = scenarioPack.assistantTurnScenariosFor(runtimeEnv);
    expect(scenarios, hasLength(21));

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          if (runtimeEnv == 'alpha')
            assistantRepositoryProvider.overrideWithValue(
              ScenarioEvalMockAssistantRepository(pack: scenarioPack),
            ),
        ],
        child: const MaterialApp(home: AssistantTabPage()),
      ),
    );
    await _pumpFrames(tester);
    _expectScreenClass(tester);

    await tester.tap(find.text('找私助'));
    await _pumpFrames(tester);
    expect(find.byKey(TestKeys.assistantChatInputField), findsOneWidget);

    final container = ProviderScope.containerOf(
      tester.element(find.byType(AssistantTabPage)),
    );
    final mode = container.read(appDataSourceModeProvider);

    for (final scenario in scenarios) {
      final started = DateTime.now();
      await container
          .read(personalAssistantStreamControllerProvider.notifier)
          .send(scenario.question);
      await _pumpUntilStreamSettled(tester);

      final context = tester.element(find.byType(AssistantTabPage));
      final state = ProviderScope.containerOf(
        context,
      ).read(personalAssistantStreamControllerProvider);
      final durationMs = DateTime.now().difference(started).inMilliseconds;
      final eventTypes = state.events
          .map((event) => event.eventType)
          .toList(growable: false);
      final selectedSkillIds = <String>{
        for (final event in state.events)
          if (_looksLikeSkillSelection(event.payload))
            (event.payload['skillId'] ?? '').toString(),
      }..remove('');
      final toolNames = <String>{
        for (final event in state.events) _toolNameForEvent(event.payload),
      }..remove('');
      final transcript = state.transcript
          .map(PersistedTimelineTurnCodec.encode)
          .toList(growable: false);

      _printEvalResult(<String, dynamic>{
        'env': runtimeEnv,
        'repositoryMode': mode.name,
        'scenarioId': scenario.id,
        'skillId': scenario.skillId,
        'domainId': scenario.domainId,
        'question': scenario.question,
        'answer': state.answer,
        'answerLength': state.answer.length,
        'errorMessage': state.errorMessage,
        'running': state.running,
        'durationMs': durationMs,
        'eventTypes': eventTypes,
        'eventCount': state.events.length,
        'selectedSkillIds': selectedSkillIds.toList(growable: false),
        'toolNames': toolNames.toList(growable: false),
        'transcript': transcript,
        'turnId': state.turnId,
        'conversationId': state.conversationId,
      });
    }
  });
}

Future<void> _pumpUntilStreamSettled(WidgetTester tester) async {
  for (var i = 0; i < 240; i++) {
    await tester.pump(const Duration(milliseconds: 100));
    final context = tester.element(find.byType(AssistantTabPage));
    final state = ProviderScope.containerOf(
      context,
    ).read(personalAssistantStreamControllerProvider);
    if (!state.running && state.answer.isNotEmpty) {
      return;
    }
  }
  await tester.pump(const Duration(milliseconds: 100));
}

Future<void> _pumpFrames(WidgetTester tester, {int count = 12}) async {
  for (var i = 0; i < count; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}

void _expectScreenClass(WidgetTester tester) {
  const expected = String.fromEnvironment(
    'VALIDATION_SCREEN_CLASS',
    defaultValue: 'any',
  );
  final logicalSize = tester.view.physicalSize / tester.view.devicePixelRatio;
  final shortestSide = logicalSize.shortestSide;
  final longestSide = logicalSize.longestSide;
  switch (expected) {
    case 'phone':
      expect(shortestSide, lessThan(700));
    case 'tablet':
      expect(longestSide, greaterThanOrEqualTo(700));
      expect(shortestSide, greaterThanOrEqualTo(500));
    case 'any':
      expect(shortestSide, greaterThan(0));
    default:
      fail('未知 VALIDATION_SCREEN_CLASS=$expected');
  }
}

String _toolNameForEvent(Map<String, dynamic> payload) {
  final raw = payload['toolUse'];
  if (raw is Map) {
    return (raw['toolName'] ?? raw['tool_name'] ?? '').toString();
  }
  return '';
}

bool _looksLikeSkillSelection(Map<String, dynamic> payload) {
  return payload.containsKey('skillId') &&
      payload.containsKey('domainId') &&
      payload.containsKey('promptPolicy');
}

void _printEvalResult(Map<String, dynamic> result) {
  // ignore: avoid_print
  print('ASSISTANT_SKILL_EVAL_RESULT_JSON:${jsonEncode(result)}');
}

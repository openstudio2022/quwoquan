import 'dart:convert';

import 'package:quwoquan_app/assistant/generated/contracts/assistant_conversation.g.dart';
import 'package:quwoquan_app/assistant/generated/contracts/assistant_stream_event.g.dart';
import 'package:quwoquan_app/assistant/generated/contracts/assistant_turn_envelope.g.dart';
import 'package:quwoquan_app/assistant/generated/contracts/tool_use.g.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';

const String _assistantScenarioFixtureJsonBase64 = String.fromEnvironment(
  'ASSISTANT_SCENARIO_FIXTURE_JSON_B64',
);

class AssistantEvalScenarioPack {
  const AssistantEvalScenarioPack({
    required this.scenarios,
    required this.qualityStandards,
  });

  final List<AssistantEvalScenario> scenarios;
  final Map<String, AssistantEvalQualityStandard> qualityStandards;

  factory AssistantEvalScenarioPack.fromJson(Map<String, dynamic> json) {
    return AssistantEvalScenarioPack(
      scenarios: ((json['scenarios'] as List?) ?? const <dynamic>[])
          .whereType<Map>()
          .map((item) => AssistantEvalScenario.fromJson(item.cast()))
          .toList(growable: false),
      qualityStandards:
          ((json['qualityStandards'] as Map?) ?? const <String, dynamic>{}).map(
            (key, value) => MapEntry(
              key.toString(),
              AssistantEvalQualityStandard.fromJson(
                (value as Map?)?.cast<String, dynamic>() ??
                    const <String, dynamic>{},
              ),
            ),
          ),
    );
  }

  List<AssistantEvalScenario> assistantTurnScenariosFor(String env) {
    return scenarios
        .where((scenario) => scenario.type == 'assistant_turn')
        .where((scenario) => scenario.isEnabledFor(env))
        .toList(growable: false);
  }
}

class AssistantEvalScenario {
  const AssistantEvalScenario({
    required this.id,
    required this.type,
    required this.skillId,
    required this.domainId,
    required this.question,
    required this.seedRefs,
    required this.expectedAnswerFragments,
    required this.expectedEvents,
    required this.expectedToolNames,
    required this.remoteExpectations,
    required this.alphaMockStream,
    required this.environments,
    required this.qualityStandardRef,
  });

  final String id;
  final String type;
  final String skillId;
  final String domainId;
  final String question;
  final List<String> seedRefs;
  final List<String> expectedAnswerFragments;
  final List<String> expectedEvents;
  final List<String> expectedToolNames;
  final AssistantEvalRemoteExpectations remoteExpectations;
  final AssistantEvalAlphaMockStream alphaMockStream;
  final Map<String, AssistantEvalScenarioEnvironment> environments;
  final String qualityStandardRef;

  factory AssistantEvalScenario.fromJson(Map<String, dynamic> json) {
    return AssistantEvalScenario(
      id: (json['id'] ?? '').toString(),
      type: (json['type'] ?? '').toString(),
      skillId: (json['skillId'] ?? '').toString(),
      domainId: (json['domainId'] ?? '').toString(),
      question: (json['question'] ?? '').toString(),
      seedRefs: _stringList(json['seedRefs']),
      expectedAnswerFragments: _stringList(json['expectedAnswerFragments']),
      expectedEvents: _stringList(json['expectedEvents']),
      expectedToolNames: _stringList(json['expectedToolNames']),
      remoteExpectations: AssistantEvalRemoteExpectations.fromJson(
        (json['remoteExpectations'] as Map?)?.cast<String, dynamic>() ??
            const <String, dynamic>{},
      ),
      alphaMockStream: AssistantEvalAlphaMockStream.fromJson(
        (json['alphaMockStream'] as Map?)?.cast<String, dynamic>() ??
            const <String, dynamic>{},
      ),
      environments:
          ((json['environments'] as Map?) ?? const <String, dynamic>{}).map(
            (key, value) => MapEntry(
              key.toString(),
              AssistantEvalScenarioEnvironment.fromJson(
                (value as Map?)?.cast<String, dynamic>() ??
                    const <String, dynamic>{},
              ),
            ),
          ),
      qualityStandardRef: (json['qualityStandardRef'] ?? '').toString(),
    );
  }

  bool isEnabledFor(String env) => environments[env]?.enabled ?? false;
}

class AssistantEvalRemoteExpectations {
  const AssistantEvalRemoteExpectations({
    required this.answerFragments,
    required this.eventTypes,
  });

  final List<String> answerFragments;
  final List<String> eventTypes;

  factory AssistantEvalRemoteExpectations.fromJson(Map<String, dynamic> json) {
    return AssistantEvalRemoteExpectations(
      answerFragments: _stringList(json['answerFragments']),
      eventTypes: _stringList(json['eventTypes']),
    );
  }
}

class AssistantEvalQualityStandard {
  const AssistantEvalQualityStandard({
    required this.minimumTotalScore,
    required this.mustCover,
    required this.mustAvoid,
    required this.authorityPolicy,
  });

  final double minimumTotalScore;
  final List<String> mustCover;
  final List<String> mustAvoid;
  final List<String> authorityPolicy;

  factory AssistantEvalQualityStandard.fromJson(Map<String, dynamic> json) {
    return AssistantEvalQualityStandard(
      minimumTotalScore: (json['minimumTotalScore'] as num?)?.toDouble() ?? 0,
      mustCover: _stringList(json['mustCover']),
      mustAvoid: _stringList(json['mustAvoid']),
      authorityPolicy: _stringList(json['authorityPolicy']),
    );
  }
}

class AssistantEvalAlphaMockStream {
  const AssistantEvalAlphaMockStream({
    required this.finalAnswer,
    required this.toolName,
    required this.toolSummary,
  });

  final String finalAnswer;
  final String toolName;
  final String toolSummary;

  factory AssistantEvalAlphaMockStream.fromJson(Map<String, dynamic> json) {
    return AssistantEvalAlphaMockStream(
      finalAnswer: (json['finalAnswer'] ?? '').toString(),
      toolName: (json['toolName'] ?? '').toString(),
      toolSummary: (json['toolSummary'] ?? '').toString(),
    );
  }
}

class AssistantEvalScenarioEnvironment {
  const AssistantEvalScenarioEnvironment({required this.enabled});

  final bool enabled;

  factory AssistantEvalScenarioEnvironment.fromJson(Map<String, dynamic> json) {
    return AssistantEvalScenarioEnvironment(enabled: json['enabled'] == true);
  }
}

AssistantEvalScenarioPack loadAssistantEvalScenarioPack() {
  if (_assistantScenarioFixtureJsonBase64.trim().isEmpty) {
    throw StateError('ASSISTANT_SCENARIO_FIXTURE_JSON_B64 is required');
  }
  final raw = utf8.decode(base64Decode(_assistantScenarioFixtureJsonBase64));
  return AssistantEvalScenarioPack.fromJson(
    jsonDecode(raw) as Map<String, dynamic>,
  );
}

class ScenarioEvalMockAssistantRepository extends MockAssistantRepository {
  ScenarioEvalMockAssistantRepository({required AssistantEvalScenarioPack pack})
    : _scenarios = {
        for (final scenario in pack.assistantTurnScenariosFor('alpha'))
          scenario.question: scenario,
      };

  final Map<String, AssistantEvalScenario> _scenarios;
  final Map<String, AssistantEvalScenario> _turnScenarios =
      <String, AssistantEvalScenario>{};

  @override
  Future<AssistantConversationWire> createAssistantConversation({
    String summary = '',
  }) async {
    final now = DateTime.now().toUtc().toIso8601String();
    return AssistantConversationWire(
      conversationId: 'acv_eval_personal_assistant',
      userId: 'eval-user',
      summary: summary,
      createdAt: now,
      updatedAt: now,
    );
  }

  @override
  Future<AssistantTurnEnvelopeWire> createAssistantTurn({
    required String conversationId,
    required String text,
    String turnType = 'user',
    String skillId = '',
    String domainId = '',
  }) async {
    final scenario = _scenarios[text.trim()] ?? _scenarios.values.first;
    final turnId = 'atn_eval_${scenario.id}';
    _turnScenarios[turnId] = scenario;
    return AssistantTurnEnvelopeWire(
      turnId: turnId,
      conversationId: conversationId,
      turnType: turnType,
      skillId: skillId.isEmpty ? scenario.skillId : skillId,
      domainId: domainId.isEmpty ? scenario.domainId : domainId,
      input: <String, dynamic>{'text': text},
      trigger: const <String, dynamic>{'type': 'user_message'},
      traceId: 'trace_eval_${scenario.id}',
      createdAt: DateTime.now().toUtc().toIso8601String(),
    );
  }

  @override
  Stream<AssistantStreamEventWire> streamAssistantTurn({
    required String turnId,
  }) async* {
    final scenario = _turnScenarios[turnId] ?? _scenarios.values.first;
    final createdAt = DateTime.now().toUtc().toIso8601String();
    final toolName = scenario.alphaMockStream.toolName.isEmpty
        ? 'mock_search'
        : scenario.alphaMockStream.toolName;
    final toolUse = ToolUseWire(
      toolUseId: 'tu_eval_${scenario.id}',
      turnId: turnId,
      toolName: toolName,
      input: <String, dynamic>{'query': scenario.question},
      status: 'requested',
      createdAt: createdAt,
    );
    final completedToolUse = ToolUseWire(
      toolUseId: toolUse.toolUseId,
      turnId: turnId,
      toolName: toolName,
      input: toolUse.input,
      status: 'completed',
      result: <String, dynamic>{
        'provider': 'eval_fixture',
        'summary': scenario.alphaMockStream.toolSummary,
        'seedRefs': scenario.seedRefs,
      },
      createdAt: createdAt,
      completedAt: createdAt,
    );

    yield AssistantStreamEventWire(
      eventId: '$turnId:assistant.turn.started',
      conversationId: 'acv_eval_personal_assistant',
      turnId: turnId,
      seq: 1,
      eventType: 'turn_started',
      payload: const <String, dynamic>{'status': 'running'},
      createdAt: createdAt,
    );
    yield AssistantStreamEventWire(
      eventId: '$turnId:assistant.tool.requested',
      conversationId: 'acv_eval_personal_assistant',
      turnId: turnId,
      seq: 2,
      eventType: 'tool_use_requested',
      payload: <String, dynamic>{'toolUse': toolUse.toJson()},
      createdAt: createdAt,
    );
    yield AssistantStreamEventWire(
      eventId: '$turnId:assistant.tool.completed',
      conversationId: 'acv_eval_personal_assistant',
      turnId: turnId,
      seq: 3,
      eventType: 'tool_result_received',
      payload: <String, dynamic>{'toolUse': completedToolUse.toJson()},
      createdAt: createdAt,
    );
    yield AssistantStreamEventWire(
      eventId: '$turnId:assistant.observation.assessed',
      conversationId: 'acv_eval_personal_assistant',
      turnId: turnId,
      seq: 4,
      eventType: 'observation_assessed',
      payload: <String, dynamic>{
        'retrievalProcessing': <String, dynamic>{
          'searchedDocumentCount': 5,
          'processedDocumentCount': 5,
          'acceptedDocumentCount': 3,
          'processingSummary':
              '已围绕 ${scenario.domainId} 核对模拟器证据，覆盖 ${scenario.expectedAnswerFragments.join('、')}。',
          'selectedKeyPoints': <String>[
            '命中技能：${scenario.skillId}',
            '工具路径：$toolName',
            '答案需覆盖：${scenario.expectedAnswerFragments.join('、')}',
          ],
          'acceptedReferences': <Map<String, dynamic>>[
            <String, dynamic>{
              'title': '${scenario.skillId} 验收质量标准',
              'source': 'assistant_skill_eval_scenarios',
              'snippet': scenario.alphaMockStream.toolSummary,
              'rank': 1,
            },
            <String, dynamic>{
              'title': '${scenario.skillId} 工具观测',
              'source': 'eval_fixture',
              'snippet': scenario.alphaMockStream.toolSummary,
              'rank': 2,
            },
            <String, dynamic>{
              'title': '${scenario.skillId} 预期答案片段',
              'source': 'eval_expectation',
              'snippet': scenario.expectedAnswerFragments.join('、'),
              'rank': 3,
            },
          ],
        },
      },
      createdAt: createdAt,
    );
    yield AssistantStreamEventWire(
      eventId: '$turnId:assistant.answer.final',
      conversationId: 'acv_eval_personal_assistant',
      turnId: turnId,
      seq: 5,
      eventType: 'final_answer',
      payload: <String, dynamic>{'text': scenario.alphaMockStream.finalAnswer},
      createdAt: createdAt,
    );
  }
}

List<String> _stringList(Object? value) {
  return ((value as List?) ?? const <dynamic>[])
      .map((item) => item.toString())
      .where((item) => item.trim().isNotEmpty)
      .toList(growable: false);
}

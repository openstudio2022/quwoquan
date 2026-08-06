import 'dart:convert';

import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import 'assistant_facets_typed_double.dart';

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

class ScenarioEvalMockAssistantRepository extends InMemoryAssistantFacets {
  ScenarioEvalMockAssistantRepository({required AssistantEvalScenarioPack pack})
    : _scenarios = {
        for (final scenario in pack.assistantTurnScenariosFor('alpha'))
          scenario.question: scenario,
      };

  final Map<String, AssistantEvalScenario> _scenarios;
  final Map<String, AssistantEvalScenario> _turnScenarios =
      <String, AssistantEvalScenario>{};

  @override
  Future<AssistantSessionWire> createAssistantSession({
    String summary = '',
    required String clientRequestId,
  }) async {
    final now = DateTime.now().toUtc().toIso8601String();
    return AssistantSessionWire(
      sessionId: 'asn_eval_personal_assistant',
      userId: 'eval-user',
      summary: summary,
      createdAt: now,
      updatedAt: now,
    );
  }

  @override
  Future<AssistantRunEnvelopeWire> startAssistantRun({
    required String sessionId,
    required String text,
    required String clientRequestId,
    String turnType = 'user',
    String skillId = '',
    String domainId = '',
    List<AssistantIntersectionEvidenceRef> intersectionEvidenceRefs =
        const <AssistantIntersectionEvidenceRef>[],
  }) async {
    final scenario = _scenarios[text.trim()] ?? _scenarios.values.first;
    final runId = 'arn_eval_${scenario.id}';
    _turnScenarios[runId] = scenario;
    return AssistantRunEnvelopeWire(
      runId: runId,
      sessionId: sessionId,
      goal: text,
      traceId: 'trace_eval_${scenario.id}',
      createdAt: DateTime.now().toUtc().toIso8601String(),
    );
  }

  @override
  Stream<AssistantStreamEventWire> watchAssistantRunEvents({
    required String runId,
    String lastEventId = '',
  }) async* {
    final scenario = _turnScenarios[runId] ?? _scenarios.values.first;
    final createdAt = DateTime.now().toUtc().toIso8601String();
    final toolName = scenario.alphaMockStream.toolName.isEmpty
        ? 'mock_search'
        : scenario.alphaMockStream.toolName;
    yield AssistantStreamEventWire(
      schema: 'assistant_stream_event',
      eventId: '$runId:run_started',
      sessionId: 'asn_eval_personal_assistant',
      runId: runId,
      seq: 1,
      eventType: AssistantStreamEventType.runStarted,
      payload: const <String, dynamic>{'status': 'running', 'restarted': false},
      createdAt: createdAt,
    );
    yield AssistantStreamEventWire(
      schema: 'assistant_stream_event',
      eventId: '$runId:process_replace',
      sessionId: 'asn_eval_personal_assistant',
      runId: runId,
      seq: 2,
      eventType: AssistantStreamEventType.processReplace,
      payload: const <String, dynamic>{'processes': <Object?>[]},
      createdAt: createdAt,
    );
    yield AssistantStreamEventWire(
      schema: 'assistant_stream_event',
      eventId: '$runId:classifying',
      sessionId: 'asn_eval_personal_assistant',
      runId: runId,
      seq: 3,
      eventType: AssistantStreamEventType.processAppend,
      payload: <String, dynamic>{
        'process': <String, dynamic>{
          'processId': 'classifying',
          'scope': 'skill',
          'stage': 'classifying',
          'status': 'completed',
          'order': 1,
          'summary': '已选择${scenario.skillId}处理本次请求。',
          'skillId': scenario.skillId,
          'domainId': scenario.domainId,
        },
      },
      createdAt: createdAt,
    );
    yield AssistantStreamEventWire(
      schema: 'assistant_stream_event',
      eventId: '$runId:searching',
      sessionId: 'asn_eval_personal_assistant',
      runId: runId,
      seq: 4,
      eventType: AssistantStreamEventType.processAppend,
      payload: <String, dynamic>{
        'process': <String, dynamic>{
          'processId': 'searching',
          'scope': 'skill',
          'stage': 'searching',
          'status': 'completed',
          'order': 2,
          'summary': scenario.alphaMockStream.toolSummary,
          'skillId': scenario.skillId,
          'domainId': scenario.domainId,
          'toolName': toolName,
        },
      },
      createdAt: createdAt,
    );
    yield AssistantStreamEventWire(
      schema: 'assistant_stream_event',
      eventId: '$runId:assessing',
      sessionId: 'asn_eval_personal_assistant',
      runId: runId,
      seq: 5,
      eventType: AssistantStreamEventType.processCommit,
      payload: <String, dynamic>{
        'process': <String, dynamic>{
          'processId': 'assessing',
          'scope': 'aggregation',
          'stage': 'assessing',
          'status': 'completed',
          'order': 3,
          'summary':
              '已核对模拟验收证据，覆盖${scenario.expectedAnswerFragments.join('、')}。',
          'searchedDocumentCount': 5,
          'processedDocumentCount': 5,
          'acceptedDocumentCount': 3,
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
      schema: 'assistant_stream_event',
      eventId: '$runId:answering',
      sessionId: 'asn_eval_personal_assistant',
      runId: runId,
      seq: 6,
      eventType: AssistantStreamEventType.processAppend,
      payload: const <String, dynamic>{
        'process': <String, dynamic>{
          'processId': 'answering',
          'scope': 'root',
          'stage': 'answering',
          'status': 'active',
          'order': 4,
        },
      },
      createdAt: createdAt,
    );
    yield AssistantStreamEventWire(
      schema: 'assistant_stream_event',
      eventId: '$runId:answer_delta',
      sessionId: 'asn_eval_personal_assistant',
      runId: runId,
      seq: 7,
      eventType: AssistantStreamEventType.answerDelta,
      payload: <String, dynamic>{'text': scenario.alphaMockStream.finalAnswer},
      createdAt: createdAt,
    );
    yield AssistantStreamEventWire(
      schema: 'assistant_stream_event',
      eventId: '$runId:answering_complete',
      sessionId: 'asn_eval_personal_assistant',
      runId: runId,
      seq: 8,
      eventType: AssistantStreamEventType.processCommit,
      payload: const <String, dynamic>{
        'process': <String, dynamic>{
          'processId': 'answering',
          'scope': 'root',
          'stage': 'answering',
          'status': 'completed',
          'order': 4,
        },
      },
      createdAt: createdAt,
    );
    yield AssistantStreamEventWire(
      schema: 'assistant_stream_event',
      eventId: '$runId:completed',
      sessionId: 'asn_eval_personal_assistant',
      runId: runId,
      seq: 9,
      eventType: AssistantStreamEventType.completed,
      payload: <String, dynamic>{
        'status': 'completed',
        'finalAnswer': scenario.alphaMockStream.finalAnswer,
      },
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

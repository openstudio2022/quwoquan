import 'dart:convert';
import 'dart:io';

import 'package:quwoquan_app/cloud/services/assistant/assistant_facets.dart';

import '../../cloud_services/assistant_facets_mock.dart';

const String assistantScenarioFixtureName =
    'quwoquan_service/services/assistant-service/tests/support/contract_fixtures/scenarios/assistant_scenarios.json';
const String _assistantScenarioFixtureJsonBase64 = String.fromEnvironment(
  'ASSISTANT_SCENARIO_FIXTURE_JSON_B64',
);

class AssistantScenarioPack {
  const AssistantScenarioPack({
    required this.schema,
    required this.repositoryExpectations,
    required this.seedSets,
    required this.scenarios,
  });

  final String schema;
  final Map<String, String> repositoryExpectations;
  final Map<String, dynamic> seedSets;
  final List<AssistantScenario> scenarios;

  factory AssistantScenarioPack.fromJson(Map<String, dynamic> json) {
    return AssistantScenarioPack(
      schema: (json['schema'] ?? '').toString(),
      repositoryExpectations:
          (json['repositoryExpectations'] as Map? ?? const <String, dynamic>{})
              .map((key, value) => MapEntry(key.toString(), value.toString())),
      seedSets:
          (json['seedSets'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
      scenarios: ((json['scenarios'] as List?) ?? const <dynamic>[])
          .whereType<Map>()
          .map((item) => AssistantScenario.fromJson(item.cast()))
          .toList(growable: false),
    );
  }

  List<AssistantScenario> assistantTurnScenariosFor(String env) {
    return scenarios
        .where((scenario) => scenario.type == 'assistant_turn')
        .where((scenario) => scenario.isEnabledFor(env))
        .toList(growable: false);
  }
}

class AssistantScenario {
  const AssistantScenario({
    required this.id,
    required this.title,
    required this.type,
    required this.skillId,
    required this.domainId,
    required this.question,
    required this.seedRefs,
    required this.expectedAnswerFragments,
    required this.expectedEvents,
    required this.alphaMockStream,
    required this.remoteExpectations,
    required this.environments,
  });

  final String id;
  final String title;
  final String type;
  final String skillId;
  final String domainId;
  final String question;
  final List<String> seedRefs;
  final List<String> expectedAnswerFragments;
  final List<String> expectedEvents;
  final AssistantAlphaMockStream alphaMockStream;
  final AssistantRemoteExpectations remoteExpectations;
  final Map<String, AssistantScenarioEnvironment> environments;

  factory AssistantScenario.fromJson(Map<String, dynamic> json) {
    return AssistantScenario(
      id: (json['id'] ?? '').toString(),
      title: (json['title'] ?? '').toString(),
      type: (json['type'] ?? '').toString(),
      skillId: (json['skillId'] ?? '').toString(),
      domainId: (json['domainId'] ?? '').toString(),
      question: (json['question'] ?? '').toString(),
      seedRefs: _stringList(json['seedRefs']),
      expectedAnswerFragments: _stringList(json['expectedAnswerFragments']),
      expectedEvents: _stringList(json['expectedEvents']),
      alphaMockStream: AssistantAlphaMockStream.fromJson(
        (json['alphaMockStream'] as Map?)?.cast<String, dynamic>() ??
            const <String, dynamic>{},
      ),
      remoteExpectations: AssistantRemoteExpectations.fromJson(
        (json['remoteExpectations'] as Map?)?.cast<String, dynamic>() ??
            const <String, dynamic>{},
      ),
      environments:
          ((json['environments'] as Map?) ?? const <String, dynamic>{}).map(
            (key, value) => MapEntry(
              key.toString(),
              AssistantScenarioEnvironment.fromJson(
                (value as Map?)?.cast<String, dynamic>() ??
                    const <String, dynamic>{},
              ),
            ),
          ),
    );
  }

  bool isEnabledFor(String env) => environments[env]?.enabled ?? false;

  List<String> answerFragmentsFor(String env) {
    if (env == 'alpha') {
      return expectedAnswerFragments
          .where((fragment) => alphaMockStream.finalAnswer.contains(fragment))
          .toList(growable: false);
    }
    return remoteExpectations.answerFragments.isEmpty
        ? expectedAnswerFragments
        : remoteExpectations.answerFragments;
  }

  List<String> eventTypesFor(String env) {
    if (env == 'alpha') {
      return expectedEvents;
    }
    return remoteExpectations.eventTypes.isEmpty
        ? expectedEvents
        : remoteExpectations.eventTypes;
  }
}

class AssistantAlphaMockStream {
  const AssistantAlphaMockStream({
    required this.finalAnswer,
    required this.toolName,
    required this.toolSummary,
  });

  final String finalAnswer;
  final String toolName;
  final String toolSummary;

  factory AssistantAlphaMockStream.fromJson(Map<String, dynamic> json) {
    return AssistantAlphaMockStream(
      finalAnswer: (json['finalAnswer'] ?? '').toString(),
      toolName: (json['toolName'] ?? '').toString(),
      toolSummary: (json['toolSummary'] ?? '').toString(),
    );
  }
}

class AssistantRemoteExpectations {
  const AssistantRemoteExpectations({
    required this.answerFragments,
    required this.eventTypes,
  });

  final List<String> answerFragments;
  final List<String> eventTypes;

  factory AssistantRemoteExpectations.fromJson(Map<String, dynamic> json) {
    return AssistantRemoteExpectations(
      answerFragments: _stringList(json['answerFragments']),
      eventTypes: _stringList(json['eventTypes']),
    );
  }
}

class AssistantScenarioEnvironment {
  const AssistantScenarioEnvironment({
    required this.enabled,
    required this.repository,
    required this.requiresSeedReset,
  });

  final bool enabled;
  final String repository;
  final bool requiresSeedReset;

  factory AssistantScenarioEnvironment.fromJson(Map<String, dynamic> json) {
    return AssistantScenarioEnvironment(
      enabled: json['enabled'] == true,
      repository: (json['repository'] ?? '').toString(),
      requiresSeedReset: json['requiresSeedReset'] == true,
    );
  }
}

AssistantScenarioPack loadAssistantScenarioPack() {
  final decoded = _loadContractFixtureObject(assistantScenarioFixtureName);
  return AssistantScenarioPack.fromJson(decoded);
}

Future<AssistantScenarioPack> loadAssistantScenarioPackAsync() async {
  final decoded = _loadContractFixtureObject(assistantScenarioFixtureName);
  return AssistantScenarioPack.fromJson(decoded);
}

class ScenarioMockAssistantRepository extends AlphaAssistantFacets {
  ScenarioMockAssistantRepository({required AssistantScenarioPack pack})
    : _scenarios = {
        for (final scenario in pack.assistantTurnScenariosFor('alpha'))
          scenario.question: scenario,
      };

  final Map<String, AssistantScenario> _scenarios;
  final Map<String, AssistantScenario> _turnScenarios =
      <String, AssistantScenario>{};

  @override
  Future<AssistantSessionWire> createAssistantSession({
    String summary = '',
    required String clientRequestId,
  }) async {
    final now = DateTime.now().toUtc().toIso8601String();
    return AssistantSessionWire(
      sessionId: 'asn_fixture_personal_assistant',
      userId: 'fixture-user',
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
    final runId = 'arn_fixture_${scenario.id}';
    _turnScenarios[runId] = scenario;
    return AssistantRunEnvelopeWire(
      runId: runId,
      sessionId: sessionId,
      goal: text,
      traceId: 'trace_fixture_${scenario.id}',
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
      sessionId: 'asn_fixture_personal_assistant',
      runId: runId,
      seq: 1,
      eventType: AssistantStreamEventType.runStarted,
      payload: const <String, dynamic>{'status': 'running', 'restarted': false},
      createdAt: createdAt,
    );
    yield AssistantStreamEventWire(
      schema: 'assistant_stream_event',
      eventId: '$runId:process_replace',
      sessionId: 'asn_fixture_personal_assistant',
      runId: runId,
      seq: 2,
      eventType: AssistantStreamEventType.processReplace,
      payload: const <String, dynamic>{'processes': <Object?>[]},
      createdAt: createdAt,
    );
    yield AssistantStreamEventWire(
      schema: 'assistant_stream_event',
      eventId: '$runId:planning',
      sessionId: 'asn_fixture_personal_assistant',
      runId: runId,
      seq: 3,
      eventType: AssistantStreamEventType.processAppend,
      payload: <String, dynamic>{
        'process': <String, dynamic>{
          'processId': 'planning',
          'scope': 'root',
          'stage': 'planning',
          'status': 'completed',
          'order': 1,
          'summary': '已确定需要核对的公开信息。',
          'skillId': scenario.skillId,
          'domainId': scenario.domainId,
        },
      },
      createdAt: createdAt,
    );
    yield AssistantStreamEventWire(
      schema: 'assistant_stream_event',
      eventId: '$runId:searching',
      sessionId: 'asn_fixture_personal_assistant',
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
      sessionId: 'asn_fixture_personal_assistant',
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
          'summary': '已从已验证的结果整理证据。',
          'searchedDocumentCount': 1,
          'processedDocumentCount': 1,
          'acceptedDocumentCount': 1,
          'acceptedReferences': <Object?>[],
        },
      },
      createdAt: createdAt,
    );
    yield AssistantStreamEventWire(
      schema: 'assistant_stream_event',
      eventId: '$runId:answering',
      sessionId: 'asn_fixture_personal_assistant',
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
      sessionId: 'asn_fixture_personal_assistant',
      runId: runId,
      seq: 7,
      eventType: AssistantStreamEventType.answerDelta,
      payload: <String, dynamic>{'text': scenario.alphaMockStream.finalAnswer},
      createdAt: createdAt,
    );
    yield AssistantStreamEventWire(
      schema: 'assistant_stream_event',
      eventId: '$runId:answering_complete',
      sessionId: 'asn_fixture_personal_assistant',
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
      sessionId: 'asn_fixture_personal_assistant',
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

Map<String, dynamic> _loadContractFixtureObject(String metadataRelativePath) {
  if (metadataRelativePath == assistantScenarioFixtureName &&
      _assistantScenarioFixtureJsonBase64.isNotEmpty) {
    final raw = utf8.decode(base64Decode(_assistantScenarioFixtureJsonBase64));
    return jsonDecode(raw) as Map<String, dynamic>;
  }
  final file = _tryContractFixtureFile(metadataRelativePath);
  if (file == null) {
    throw StateError(
      'contract fixture 缺失: $metadataRelativePath, cwd=${Directory.current.path}',
    );
  }
  return jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
}

File? _tryContractFixtureFile(String repositoryOrMetadataPath) {
  final suffix = repositoryOrMetadataPath.startsWith('quwoquan_service/')
      ? repositoryOrMetadataPath
      : 'quwoquan_service/contracts/metadata/$repositoryOrMetadataPath';
  final candidates = <File>[
    File('../$suffix'),
    File(suffix),
    File('../../$suffix'),
  ];
  for (final candidate in candidates) {
    if (candidate.existsSync()) {
      return candidate;
    }
  }
  return null;
}

import 'dart:convert';
import 'dart:io';

import 'package:quwoquan_app/assistant/generated/contracts/assistant_conversation.g.dart';
import 'package:quwoquan_app/assistant/generated/contracts/assistant_stream_event.g.dart';
import 'package:quwoquan_app/assistant/generated/contracts/assistant_turn_envelope.g.dart';
import 'package:quwoquan_app/assistant/generated/contracts/tool_use.g.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';

const String assistantScenarioFixtureName =
    'assistant/test_fixtures/scenarios/assistant_scenarios.json';
const String _assistantScenarioFixtureJsonBase64 = String.fromEnvironment(
  'ASSISTANT_SCENARIO_FIXTURE_JSON_B64',
);

class AssistantScenarioPack {
  const AssistantScenarioPack({
    required this.schemaVersion,
    required this.repositoryExpectations,
    required this.seedSets,
    required this.scenarios,
  });

  final String schemaVersion;
  final Map<String, String> repositoryExpectations;
  final Map<String, dynamic> seedSets;
  final List<AssistantScenario> scenarios;

  factory AssistantScenarioPack.fromJson(Map<String, dynamic> json) {
    return AssistantScenarioPack(
      schemaVersion: (json['schemaVersion'] ?? '').toString(),
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

AppDataSourceMode expectedRepositoryModeForRuntimeEnv(
  AssistantScenarioPack pack,
  String env,
) {
  final expected = pack.repositoryExpectations[env];
  if (expected == 'remote') {
    return AppDataSourceMode.remote;
  }
  return AppDataSourceMode.mock;
}

AppDataSourceMode expectedRepositoryModeForCurrentRuntimeEnv(
  AssistantScenarioPack pack,
) {
  return expectedRepositoryModeForRuntimeEnv(
    pack,
    CloudRuntimeConfig.appRuntimeEnv,
  );
}

class ScenarioMockAssistantRepository extends MockAssistantRepository {
  ScenarioMockAssistantRepository({required AssistantScenarioPack pack})
    : _scenarios = {
        for (final scenario in pack.assistantTurnScenariosFor('alpha'))
          scenario.question: scenario,
      };

  final Map<String, AssistantScenario> _scenarios;
  final Map<String, AssistantScenario> _turnScenarios =
      <String, AssistantScenario>{};

  @override
  Future<AssistantConversationWire> createAssistantConversation({
    String summary = '',
  }) async {
    final now = DateTime.now().toUtc().toIso8601String();
    return AssistantConversationWire(
      conversationId: 'acv_fixture_personal_assistant',
      userId: 'fixture-user',
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
    final turnId = 'atn_fixture_${scenario.id}';
    _turnScenarios[turnId] = scenario;
    return AssistantTurnEnvelopeWire(
      turnId: turnId,
      conversationId: conversationId,
      turnType: turnType,
      skillId: skillId.isEmpty ? scenario.skillId : skillId,
      domainId: domainId.isEmpty ? scenario.domainId : domainId,
      input: <String, dynamic>{'text': text},
      trigger: const <String, dynamic>{'type': 'user_message'},
      traceId: 'trace_fixture_${scenario.id}',
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
      toolUseId: 'tu_fixture_${scenario.id}',
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
        'provider': 'fixture',
        'summary': scenario.alphaMockStream.toolSummary,
        'seedRefs': scenario.seedRefs,
      },
      createdAt: createdAt,
      completedAt: createdAt,
    );

    yield AssistantStreamEventWire(
      eventId: '$turnId:assistant.turn.started',
      conversationId: 'acv_fixture_personal_assistant',
      turnId: turnId,
      seq: 1,
      eventType: 'turn_started',
      payload: const <String, dynamic>{'status': 'running'},
      createdAt: createdAt,
    );
    yield AssistantStreamEventWire(
      eventId: '$turnId:assistant.plan.updated',
      conversationId: 'acv_fixture_personal_assistant',
      turnId: turnId,
      seq: 2,
      eventType: 'plan_updated',
      payload: <String, dynamic>{
        'iteration': 1,
        'skillId': scenario.skillId,
        'understandingSnapshot': <String, dynamic>{
          'userFacingSummary':
              'fixture：理解「${scenario.question}」的核心关注点。',
          'retrievalDesignNarrative':
              'fixture：说明检索方向与需要核验的外部信息。',
        },
      },
      createdAt: createdAt,
    );
    yield AssistantStreamEventWire(
      eventId: '$turnId:assistant.tool.requested',
      conversationId: 'acv_fixture_personal_assistant',
      turnId: turnId,
      seq: 3,
      eventType: 'tool_use_requested',
      payload: <String, dynamic>{'toolUse': toolUse.toJson()},
      createdAt: createdAt,
    );
    yield AssistantStreamEventWire(
      eventId: '$turnId:assistant.tool.completed',
      conversationId: 'acv_fixture_personal_assistant',
      turnId: turnId,
      seq: 4,
      eventType: 'tool_result_received',
      payload: <String, dynamic>{'toolUse': completedToolUse.toJson()},
      createdAt: createdAt,
    );
    yield AssistantStreamEventWire(
      eventId: '$turnId:assistant.observation.assessed',
      conversationId: 'acv_fixture_personal_assistant',
      turnId: turnId,
      seq: 5,
      eventType: 'observation_assessed',
      payload: <String, dynamic>{
        'iteration': 1,
        'skillId': scenario.skillId,
        'retrievalProcessing': <String, dynamic>{
          'processingSummary': 'fixture：已从工具结果整理证据叙事。',
          'selectedKeyPoints': <String>['fixture 要点'],
          'acceptedReferences': <dynamic>[],
        },
      },
      createdAt: createdAt,
    );
    yield AssistantStreamEventWire(
      eventId: '$turnId:assistant.answer.final',
      conversationId: 'acv_fixture_personal_assistant',
      turnId: turnId,
      seq: 6,
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

File? _tryContractFixtureFile(String metadataRelativePath) {
  final candidates = <File>[
    File('../quwoquan_service/contracts/metadata/$metadataRelativePath'),
    File('quwoquan_service/contracts/metadata/$metadataRelativePath'),
    File('../../quwoquan_service/contracts/metadata/$metadataRelativePath'),
  ];
  for (final candidate in candidates) {
    if (candidate.existsSync()) {
      return candidate;
    }
  }
  return null;
}

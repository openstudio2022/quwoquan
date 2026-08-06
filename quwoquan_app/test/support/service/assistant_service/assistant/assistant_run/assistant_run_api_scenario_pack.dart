import 'dart:convert';

const _scenarioJsonBase64 = String.fromEnvironment(
  'ASSISTANT_SCENARIO_FIXTURE_JSON_B64',
);

final class AssistantRunApiScenarioPack {
  const AssistantRunApiScenarioPack({
    required this.scenarios,
    required this.qualityStandards,
  });

  factory AssistantRunApiScenarioPack.fromEnvironment() {
    if (_scenarioJsonBase64.trim().isEmpty) {
      throw StateError('ASSISTANT_SCENARIO_FIXTURE_JSON_B64 is required');
    }
    final decoded = jsonDecode(utf8.decode(base64Decode(_scenarioJsonBase64)));
    if (decoded is! Map) {
      throw const FormatException('Assistant scenario pack must be an object');
    }
    final json = decoded.cast<String, dynamic>();
    return AssistantRunApiScenarioPack(
      scenarios: ((json['scenarios'] as List?) ?? const <Object?>[])
          .whereType<Map>()
          .map(
            (item) =>
                AssistantRunApiScenario.fromJson(item.cast<String, dynamic>()),
          )
          .toList(growable: false),
      qualityStandards:
          ((json['qualityStandards'] as Map?) ?? const <String, dynamic>{}).map(
            (key, value) => MapEntry(
              key.toString(),
              AssistantRunApiQualityStandard.fromJson(
                (value as Map?)?.cast<String, dynamic>() ??
                    const <String, dynamic>{},
              ),
            ),
          ),
    );
  }

  final List<AssistantRunApiScenario> scenarios;
  final Map<String, AssistantRunApiQualityStandard> qualityStandards;

  List<AssistantRunApiScenario> scenariosFor(String environment) => scenarios
      .where((scenario) => scenario.type == 'assistant_turn')
      .where((scenario) => scenario.enabledEnvironments.contains(environment))
      .toList(growable: false);
}

final class AssistantRunApiScenario {
  const AssistantRunApiScenario({
    required this.id,
    required this.type,
    required this.skillId,
    required this.domainId,
    required this.question,
    required this.expectedAnswerFragments,
    required this.expectedEventTypes,
    required this.expectedToolNames,
    required this.enabledEnvironments,
    required this.qualityStandardRef,
  });

  factory AssistantRunApiScenario.fromJson(Map<String, dynamic> json) {
    final remoteExpectations =
        (json['remoteExpectations'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final environments =
        (json['environments'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    return AssistantRunApiScenario(
      id: (json['id'] ?? '').toString(),
      type: (json['type'] ?? '').toString(),
      skillId: (json['skillId'] ?? '').toString(),
      domainId: (json['domainId'] ?? '').toString(),
      question: (json['question'] ?? '').toString(),
      expectedAnswerFragments: _strings(
        remoteExpectations['answerFragments'],
        fallback: _strings(json['expectedAnswerFragments']),
      ),
      expectedEventTypes: _strings(
        remoteExpectations['eventTypes'],
        fallback: _strings(json['expectedEvents']),
      ),
      expectedToolNames: _strings(json['expectedToolNames']),
      enabledEnvironments: <String>{
        for (final entry in environments.entries)
          if (entry.value is Map &&
              ((entry.value as Map)['enabled'] as bool? ?? false))
            entry.key,
      },
      qualityStandardRef: (json['qualityStandardRef'] ?? '').toString(),
    );
  }

  final String id;
  final String type;
  final String skillId;
  final String domainId;
  final String question;
  final List<String> expectedAnswerFragments;
  final List<String> expectedEventTypes;
  final List<String> expectedToolNames;
  final Set<String> enabledEnvironments;
  final String qualityStandardRef;
}

final class AssistantRunApiQualityStandard {
  const AssistantRunApiQualityStandard({
    required this.minimumTotalScore,
    required this.mustAvoid,
  });

  factory AssistantRunApiQualityStandard.fromJson(Map<String, dynamic> json) {
    return AssistantRunApiQualityStandard(
      minimumTotalScore: (json['minimumTotalScore'] as num?)?.toDouble() ?? 0,
      mustAvoid: _strings(json['mustAvoid']),
    );
  }

  final double minimumTotalScore;
  final List<String> mustAvoid;
}

List<String> _strings(Object? value, {List<String> fallback = const []}) {
  final result = (value as List? ?? const <Object?>[])
      .map((item) => item.toString().trim())
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
  return result.isEmpty ? fallback : result;
}

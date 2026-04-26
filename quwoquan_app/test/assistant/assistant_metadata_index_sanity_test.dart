import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:yaml/yaml.dart';

/// 与 `loadAssistantContractIndex` 同构的轻量校验：带 dart_class 的 schema 可被解析且含关键键。
void main() {
  test('assistant schema.yaml 可被 YAML 解析且索引键完整', () {
    final base = Directory('../quwoquan_service/contracts/metadata/assistant');
    expect(base.existsSync(), isTrue);

    final schemas = base
        .listSync()
        .whereType<Directory>()
        .where((d) => !d.path.split('/').last.startsWith('_'))
        .map((d) => File('${d.path}/schema.yaml'))
        .where((f) => f.existsSync())
        .toList(growable: false);

    expect(schemas.length, 21);

    for (final file in schemas) {
      final doc = loadYaml(file.readAsStringSync());
      expect(doc, isA<YamlMap>(), reason: file.path);
      final m = doc as YamlMap;
      expect(m['dart_class'], isNotNull, reason: file.path);
      expect(m['library_path'], isNotNull, reason: file.path);
      expect(m['output_path'], isNotNull, reason: file.path);
      expect(m['fields'], isNotNull, reason: file.path);
    }

    final turn = loadYaml(
          File('${base.path}/assistant_turn/schema.yaml').readAsStringSync(),
        )
        as YamlMap;
    expect(turn['subcontracts'], isNotNull);
    final sub = turn['subcontracts'] as YamlMap;
    expect(sub.containsKey('decision'), isTrue);
    expect(sub.containsKey('tool_call'), isTrue);
    expect(sub.containsKey('evidence_item'), isTrue);
    expect(turn['fields'], isA<YamlList>());
    final fields = turn['fields'] as YamlList;
    final names = fields
        .whereType<YamlMap>()
        .map((e) => e['name']?.toString() ?? '')
        .toSet();
    expect(names.contains('journey'), isTrue);
    expect(names.contains('contractId'), isTrue);
    expect(names.contains('understandingResult'), isTrue);
    expect(names.contains('taskGraph'), isTrue);

    final turnRaw =
        File('${base.path}/assistant_turn/schema.yaml').readAsStringSync();
    expect(turnRaw, isNot(contains('uiProcessTimeline')));
    expect(turnRaw, isNot(contains('processSummary')));

    final journeyYaml = loadYaml(
          File('${base.path}/assistant_journey/schema.yaml').readAsStringSync(),
        )
        as YamlMap;
    final jStr = journeyYaml.toString();
    expect(jStr, contains('AssistantJourney'));
    expect(jStr, contains('JourneyStageId'));
    expect(jStr, contains('referenceSummary'));

    final runYaml = loadYaml(
          File('${base.path}/run_artifacts/schema.yaml').readAsStringSync(),
        )
        as YamlMap;
    final subs = runYaml['subcontracts'] as YamlMap?;
    expect(subs, isNotNull);
    expect(subs!.containsKey('slot_value'), isTrue);
    expect(subs.containsKey('slot_state'), isTrue);
    expect(subs.containsKey('policy_bundle'), isTrue);
    final runFields = runYaml['fields'] as YamlList?;
    expect(runFields, isNotNull);
    final runNames = runFields!
        .whereType<YamlMap>()
        .map((e) => e['name']?.toString() ?? '')
        .toSet();
    expect(runNames.contains('journey'), isTrue);
  });
}

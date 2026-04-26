import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';

void main() {
  test('tool catalog should define every skill domain mapping', () {
    final manifestFile = File('assets/assistant/tools/manifest.json');
    expect(manifestFile.existsSync(), isTrue);

    final manifest = jsonDecode(manifestFile.readAsStringSync());
    expect(manifest, isA<Map>());
    final catalogPath = (manifest as Map)['catalogPath']?.toString() ?? '';
    expect(catalogPath, isNotEmpty);

    final catalogFile = File(catalogPath);
    expect(catalogFile.existsSync(), isTrue);
    final catalog = jsonDecode(catalogFile.readAsStringSync());
    expect(catalog, isA<Map>());

    final tools = ((catalog as Map)['tools'] as List?) ?? const <dynamic>[];
    final toolNames = tools
        .whereType<Map>()
        .map((item) => item['toolName']?.toString() ?? '')
        .where((name) => name.isNotEmpty)
        .toSet();
    expect(toolNames.contains('web_search'), isTrue);
    expect(toolNames.contains('search'), isTrue);

    final domainMatrix =
        (catalog['domainToolMatrix'] as List?) ?? const <dynamic>[];
    final matrixByDomain = <String, Set<String>>{
      for (final item in domainMatrix.whereType<Map>())
        if ((item['domainId']?.toString().trim() ?? '').isNotEmpty)
          item['domainId'].toString().trim():
              ((item['allowedTools'] as List?) ?? const <dynamic>[])
                  .whereType<String>()
                  .map((tool) => tool.trim())
                  .where((tool) => tool.isNotEmpty)
                  .toSet(),
    };
    final skillAllowedToolsByDomain = _skillAllowedToolsByDomain();
    expect(
      matrixByDomain.keys.toSet(),
      equals(skillAllowedToolsByDomain.keys.toSet()),
      reason: 'domainToolMatrix must stay aligned with bundled SKILL.md domains',
    );
    for (final entry in skillAllowedToolsByDomain.entries) {
      expect(
        matrixByDomain[entry.key],
        equals(entry.value),
        reason: '${entry.key} allowed tools must come from SKILL.md',
      );
    }

    final divination = domainMatrix.whereType<Map>().firstWhere(
      (item) => item['domainId']?.toString() == 'divination_fortune',
      orElse: () => <String, dynamic>{},
    );
    expect(divination.isNotEmpty, isTrue);
    final allowed =
        (divination['allowedTools'] as List?)?.whereType<String>().toList() ??
        const <String>[];
    expect(allowed.contains('search'), isTrue);
    expect(allowed.contains('web_search'), isTrue);

    final weather = domainMatrix.whereType<Map>().firstWhere(
      (item) => item['domainId']?.toString() == 'weather',
      orElse: () => <String, dynamic>{},
    );
    expect(weather.isNotEmpty, isTrue);
    final weatherAllowed =
        (weather['allowedTools'] as List?)?.whereType<String>().toList() ??
        const <String>[];
    expect(weatherAllowed.contains('search'), isTrue);
    expect(weatherAllowed.contains('web_search'), isTrue);
    expect(weatherAllowed.contains('memory_search'), isTrue);

    final fallback = domainMatrix.whereType<Map>().firstWhere(
      (item) => item['domainId']?.toString() == 'fallback_general_search',
      orElse: () => <String, dynamic>{},
    );
    expect(fallback.isNotEmpty, isTrue);
    final fallbackAllowed =
        (fallback['allowedTools'] as List?)?.whereType<String>().toList() ??
        const <String>[];
    expect(fallbackAllowed.contains('search'), isTrue);
  });

  test('search tool public schema stays aligned with generated metadata', () {
    final manifestFile = File('assets/assistant/tools/manifest.json');
    final manifest = jsonDecode(manifestFile.readAsStringSync()) as Map;
    final catalogPath = (manifest['catalogPath'] as String?)?.trim() ?? '';
    final catalogFile = File(catalogPath);
    final catalog = jsonDecode(catalogFile.readAsStringSync()) as Map;
    final tools = (catalog['tools'] as List?)?.whereType<Map>().toList() ??
        const <Map>[];
    final search = tools.firstWhere(
      (item) => item['toolName']?.toString() == 'search',
      orElse: () => <String, dynamic>{},
    );
    expect(search.isNotEmpty, isTrue);

    final routing =
        (search['routing'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final internalOnlyParameters =
        (routing['internalOnlyParameters'] as List?)
                ?.whereType<String>()
                .toList(growable: false) ??
            const <String>[];
    expect(
      internalOnlyParameters,
      equals(SearchToolContract.internalOptionalFields),
    );

    final parameterSummaryNames =
        (search['parameterSummary'] as List?)
                ?.whereType<Map>()
                .map((item) => item['name']?.toString() ?? '')
                .where((name) => name.isNotEmpty)
                .toSet() ??
            const <String>{};
    expect(
      parameterSummaryNames,
      equals(<String>{
        ...SearchToolContract.requiredFields,
        ...SearchToolContract.optionalFields,
      }),
    );
    expect(
      parameterSummaryNames.contains(SearchToolFieldNames.searchPlans),
      isFalse,
    );
    expect(
      parameterSummaryNames.contains(SearchToolFieldNames.queryVariants),
      isFalse,
    );

    final openAiFunction =
        (search['openAiFunction'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final parameters =
        (openAiFunction['parameters'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final properties =
        (parameters['properties'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final required =
        (parameters['required'] as List?)?.whereType<String>().toList() ??
        const <String>[];
    expect(required, equals(SearchToolContract.requiredFields));
    expect(
      properties.keys.toSet(),
      equals(<String>{
        ...SearchToolContract.requiredFields,
        ...SearchToolContract.optionalFields,
      }),
    );
    expect(properties.containsKey(SearchToolFieldNames.searchPlans), isFalse);
    expect(properties.containsKey(SearchToolFieldNames.queryVariants), isFalse);

    final modeSchema =
        (properties[SearchToolFieldNames.mode] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    expect(
      (modeSchema['enum'] as List?)?.whereType<String>().toList(),
      equals(
        SearchMode.values.map((item) => item.wireValue).toList(growable: false),
      ),
    );

    final objectTypesSchema =
        (properties[SearchToolFieldNames.objectTypes] as Map?)
                ?.cast<String, dynamic>() ??
            const <String, dynamic>{};
    final objectTypeItems =
        (objectTypesSchema['items'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    expect(
      (objectTypeItems['enum'] as List?)?.whereType<String>().toList(),
      equals(
        SearchObjectType.values
            .map((item) => item.wireValue)
            .toList(growable: false),
      ),
    );

    final conversationTypeSchema =
        (properties[SearchToolFieldNames.conversationType] as Map?)
                ?.cast<String, dynamic>() ??
            const <String, dynamic>{};
    expect(
      (conversationTypeSchema['enum'] as List?)?.whereType<String>().toList(),
      equals(SearchToolContract.conversationTypes),
    );

    final contentTypesSchema =
        (properties[SearchToolFieldNames.contentTypes] as Map?)
                ?.cast<String, dynamic>() ??
            const <String, dynamic>{};
    final contentTypeItems =
        (contentTypesSchema['items'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    expect(
      (contentTypeItems['enum'] as List?)?.whereType<String>().toList(),
      equals(SearchToolContract.contentTypes),
    );
  });
}

Map<String, Set<String>> _skillAllowedToolsByDomain() {
  final result = <String, Set<String>>{};
  final skillsDir = Directory('assets/assistant/skills');
  for (final dir in skillsDir.listSync().whereType<Directory>()) {
    final skillFile = File('${dir.path}/SKILL.md');
    if (!skillFile.existsSync()) continue;
    final raw = skillFile.readAsStringSync();
    final domain = _frontmatterValue(raw, 'domain');
    final allowedTools = _frontmatterValue(raw, 'allowed_tools')
        .split(RegExp(r'[\s,]+'))
        .map((tool) => tool.trim())
        .where((tool) => tool.isNotEmpty)
        .toSet();
    if (domain.isNotEmpty) {
      result[domain] = allowedTools;
    }
  }
  return result;
}

String _frontmatterValue(String raw, String key) {
  final pattern = RegExp('^$key:\\s*(.+)\$', multiLine: true);
  final match = pattern.firstMatch(raw);
  return match?.group(1)?.trim() ?? '';
}

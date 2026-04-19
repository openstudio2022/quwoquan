import 'dart:convert';
import 'dart:io';

import 'package:test/test.dart';

void main() {
  test('manifest uses md+meta pairs with frozen meta contract', () {
    final manifest = File('assets/assistant/prompts/manifest.json');
    expect(manifest.existsSync(), isTrue);
    final decoded = jsonDecode(manifest.readAsStringSync()) as Map;
    final templates =
        (decoded['templates'] as List?)?.whereType<Map>().toList() ??
        const <Map>[];
    expect(templates.length, greaterThanOrEqualTo(10));

    for (final item in templates) {
      final metaPath = (item['metaPath'] as String?) ?? '';
      final contentPath = (item['contentPath'] as String?) ?? '';
      expect(metaPath.endsWith('.meta.json'), isTrue);
      expect(contentPath.endsWith('.md'), isTrue);
      final metaFile = File(metaPath);
      final contentFile = File(contentPath);
      expect(metaFile.existsSync(), isTrue, reason: 'missing $metaPath');
      expect(contentFile.existsSync(), isTrue, reason: 'missing $contentPath');
      final meta = jsonDecode(metaFile.readAsStringSync()) as Map;
      expect((meta['templateId'] as String?)?.isNotEmpty, isTrue);
      final version = (meta['version'] as String?)?.trim() ?? '';
      expect(version, isNotEmpty, reason: 'version 字段不得为空');
      expect(
        RegExp(r'^\d{4}\.\d{2}\.\d{2}$').hasMatch(version),
        isTrue,
        reason: 'version 格式应为 YYYY.MM.DD，实际为: $version',
      );
      expect((meta['stage'] as String?)?.isNotEmpty, isTrue);
      expect((meta['requiredVariables'] as List?)?.isNotEmpty, isTrue);
      expect((meta['outputContract'] as String?)?.isNotEmpty, isTrue);
      expect((meta['selfCheckRules'] as List?)?.isNotEmpty, isTrue);
    }
  });

  test('global prompt placeholders align with meta requiredVariables', () {
    final pairs = <Map<String, String>>[
      <String, String>{
        'meta': 'assets/assistant/prompts/global/planner.global_plan.meta.json',
        'md': 'assets/assistant/prompts/global/planner.global_plan.md',
      },
      <String, String>{
        'meta': 'assets/assistant/prompts/global/synthesizer.final_answer.meta.json',
        'md': 'assets/assistant/prompts/global/synthesizer.final_answer.md',
      },
      <String, String>{
        'meta': 'assets/assistant/prompts/global/evidence_digest.meta.json',
        'md': 'assets/assistant/prompts/global/evidence_digest.md',
      },
      <String, String>{
        'meta': 'assets/assistant/prompts/global/stack.persona.meta.json',
        'md': 'assets/assistant/prompts/global/stack.persona.md',
      },
      <String, String>{
        'meta': 'assets/assistant/prompts/global/stack.tool_policy.meta.json',
        'md': 'assets/assistant/prompts/global/stack.tool_policy.md',
      },
    ];

    final placeholderRe = RegExp(r'\{\{\s*([A-Za-z0-9_.]+)\s*\}\}');

    for (final pair in pairs) {
      final metaFile = File(pair['meta']!);
      final contentFile = File(pair['md']!);
      expect(metaFile.existsSync(), isTrue, reason: 'missing ${pair['meta']}');
      expect(
        contentFile.existsSync(),
        isTrue,
        reason: 'missing ${pair['md']}',
      );

      final meta = jsonDecode(metaFile.readAsStringSync()) as Map;
      final requiredVariables = ((meta['requiredVariables'] as List?) ?? const [])
          .whereType<String>()
          .map((item) => item.trim())
          .where((item) => item.isNotEmpty)
          .toSet();

      final content = contentFile.readAsStringSync();
      final placeholders = placeholderRe
          .allMatches(content)
          .map((match) => match.group(1)!.trim())
          .where((item) => item.isNotEmpty)
          .toSet();

      expect(
        placeholders,
        equals(requiredVariables),
        reason:
            '${pair['md']} 占位符与 ${pair['meta']} requiredVariables 不一致。\n'
            'placeholders=$placeholders\nrequiredVariables=$requiredVariables',
      );
    }
  });
}

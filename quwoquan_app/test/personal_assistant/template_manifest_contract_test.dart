import 'dart:convert';
import 'dart:io';

import 'package:test/test.dart';

void main() {
  test('manifest uses md+meta pairs with frozen meta contract', () {
    final manifest = File('assets/personal_assistant/prompts/manifest.json');
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
}


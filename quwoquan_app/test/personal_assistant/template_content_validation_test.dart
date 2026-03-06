import 'dart:convert';
import 'dart:io';

import 'package:quwoquan_app/personal_assistant/template_runtime/template_validator.dart';
import 'package:test/test.dart';

/// 对 manifest.json 中每个模板文件运行真实 TemplateValidator 校验。
/// 此测试确保：
///   1. 每个模板文件能从磁盘正常读取
///   2. 每个模板通过 TemplateValidator.validate() 校验（不会被 TemplateRegistry 静默跳过）
///   3. 任何模板更新后都必须保证校验通过，否则 TemplateRegistry 不会加载该模板
void main() {
  const validator = TemplateValidator();
  const manifestPath = 'assets/personal_assistant/prompts/manifest.json';

  late List<_TemplateEntry> templateEntries;

  setUpAll(() {
    final manifest = File(manifestPath);
    expect(manifest.existsSync(), isTrue, reason: 'manifest.json 必须存在');
    final decoded = jsonDecode(manifest.readAsStringSync()) as Map;
    final templates =
        (decoded['templates'] as List?)?.whereType<Map>().toList() ??
        const <Map>[];
    expect(templates, isNotEmpty, reason: 'manifest 至少包含 1 个模板');
    templateEntries = templates.map((item) {
      return _TemplateEntry(
        metaPath: (item['metaPath'] as String?) ?? '',
        contentPath: (item['contentPath'] as String?) ?? '',
      );
    }).toList(growable: false);
  });

  group('manifest 所有模板通过 TemplateValidator 校验', () {
    test('每个模板文件可读取且通过校验', () {
      final failures = <String>[];
      for (final entry in templateEntries) {
        if (entry.metaPath.isEmpty || entry.contentPath.isEmpty) {
          failures.add(
            '条目缺少 metaPath 或 contentPath: $entry',
          );
          continue;
        }
        final contentFile = File(entry.contentPath);
        if (!contentFile.existsSync()) {
          failures.add('文件不存在: ${entry.contentPath}');
          continue;
        }
        final metaFile = File(entry.metaPath);
        if (!metaFile.existsSync()) {
          failures.add('meta 文件不存在: ${entry.metaPath}');
          continue;
        }
        final meta = jsonDecode(metaFile.readAsStringSync()) as Map;
        final templateId = (meta['templateId'] as String?)?.trim() ?? '';
        if (templateId.isEmpty) {
          failures.add('templateId 为空: ${entry.metaPath}');
          continue;
        }
        final content = contentFile.readAsStringSync();
        final result = validator.validate(templateId: templateId, content: content);
        if (!result.isValid) {
          failures.add(
            '$templateId (${entry.contentPath}) 校验失败:\n'
            '  ${result.errors.join('\n  ')}',
          );
        }
      }
      expect(
        failures,
        isEmpty,
        reason:
            '以下模板校验失败，将被 TemplateRegistry 静默跳过导致运行时错误:\n'
            '${failures.join('\n')}',
      );
    });

    test('每个模板 templateId 唯一', () {
      final ids = <String>[];
      final duplicates = <String>[];
      for (final entry in templateEntries) {
        if (entry.metaPath.isEmpty) continue;
        final metaFile = File(entry.metaPath);
        if (!metaFile.existsSync()) continue;
        final meta = jsonDecode(metaFile.readAsStringSync()) as Map;
        final id = (meta['templateId'] as String?)?.trim() ?? '';
        if (id.isEmpty) continue;
        if (ids.contains(id)) {
          duplicates.add(id);
        } else {
          ids.add(id);
        }
      }
      expect(
        duplicates,
        isEmpty,
        reason: '以下 templateId 重复注册，会导致版本覆盖: $duplicates',
      );
    });

    test('planner.global_plan 无重复数据块', () {
      const plannerContentPath =
          'assets/personal_assistant/prompts/global/planner.global_plan.md';
      final content = File(plannerContentPath).readAsStringSync();
      final startCount =
          RegExp(r'=== CONTEXT_DATA_START ===').allMatches(content).length;
      final endCount =
          RegExp(r'=== CONTEXT_DATA_END ===').allMatches(content).length;
      expect(startCount, 1,
          reason:
              'planner.global_plan.md 有 $startCount 个 CONTEXT_DATA_START，应为 1（无重复内容）');
      expect(endCount, 1,
          reason:
              'planner.global_plan.md 有 $endCount 个 CONTEXT_DATA_END，应为 1（无重复内容）');
    });
  });
}

class _TemplateEntry {
  const _TemplateEntry({required this.metaPath, required this.contentPath});
  final String metaPath;
  final String contentPath;

  @override
  String toString() => 'meta=$metaPath content=$contentPath';
}

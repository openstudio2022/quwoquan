import 'dart:io';

import 'package:test/test.dart';

void main() {
  group('Skill standard contract', () {
    final skillRoot = Directory('assets/personal_assistant/skills');
    final bannedTokens = <String>[
      'unified_retrieval',
      'region_geocode_api',
      'machine track',
      'user track',
      'OpenClaw',
      'Agent Skills',
    ];
    final requiredFrontmatterKeys = <String>[
      'name',
      'description',
      'domain',
      'allowed_tools',
      'trigger_keywords',
      'output_contract',
      'tool_observation_contract',
      'reference_docs',
      'script_guides',
      'dialogue_state_docs',
    ];
    final forbiddenFrontmatterKeys = <String>['version', 'owner', 'risk_level'];
    final requiredSections = <String>[
      '## 目标',
      '## 工具调用策略',
      '## 触发与禁用条件',
      '## 双轨输出契约',
      '## Markdown 卡片结构',
      '## 参考资料',
      '## 脚本指引',
      '## 轮次状态定义',
    ];
    const allowedToolSet = <String>{
      'web_search',
      'web_fetch',
      'memory_search',
      'local_context',
      'media_gallery',
      'intent_bridge',
      'scheduler',
      'deep_link',
      'app_action',
    };

    Map<String, String> parseFrontmatter(String raw) {
      final normalized = raw.replaceAll('\r\n', '\n');
      if (!normalized.startsWith('---\n')) return const <String, String>{};
      final end = normalized.indexOf('\n---\n', 4);
      if (end < 0) return const <String, String>{};
      final fm = normalized.substring(4, end).trim();
      final out = <String, String>{};
      for (final line in fm.split('\n')) {
        final trimmed = line.trim();
        if (trimmed.isEmpty || trimmed.startsWith('#')) continue;
        final sep = trimmed.indexOf(':');
        if (sep <= 0) continue;
        out[trimmed.substring(0, sep).trim()] =
            trimmed.substring(sep + 1).trim();
      }
      return out;
    }

    List<String> parseSpaceList(String rawValue) {
      return rawValue
          .split(RegExp(r'\s+'))
          .map((item) => item.trim())
          .where((item) => item.isNotEmpty)
          .toList(growable: false);
    }

    test('all SKILL.md files should follow baseline standard', () {
      expect(skillRoot.existsSync(), isTrue);
      final skillFiles = skillRoot
          .listSync(recursive: true)
          .whereType<File>()
          .where((f) => f.path.endsWith('/SKILL.md'))
          .toList(growable: false);
      expect(skillFiles, isNotEmpty);

      for (final file in skillFiles) {
        final raw = file.readAsStringSync();
        final frontmatter = parseFrontmatter(raw);
        final normalizedPath = file.path.replaceAll('\\', '/');

        for (final key in requiredFrontmatterKeys) {
          expect(
            frontmatter.containsKey(key),
            isTrue,
            reason: '$normalizedPath 缺少 frontmatter 字段: $key',
          );
          expect(
            (frontmatter[key] ?? '').trim().isNotEmpty,
            isTrue,
            reason: '$normalizedPath frontmatter 字段为空: $key',
          );
        }

        for (final forbidden in forbiddenFrontmatterKeys) {
          expect(
            frontmatter.containsKey(forbidden),
            isFalse,
            reason: '$normalizedPath 包含禁止字段: $forbidden',
          );
        }

        final allowedTools = parseSpaceList(frontmatter['allowed_tools'] ?? '');
        expect(allowedTools, isNotEmpty, reason: '$normalizedPath allowed_tools 为空');
        for (final tool in allowedTools) {
          expect(
            allowedToolSet.contains(tool),
            isTrue,
            reason: '$normalizedPath 包含未注册工具: $tool',
          );
        }
        if (allowedTools.contains('local_context')) {
          expect(
            raw.contains('local_context_v1'),
            isTrue,
            reason: '$normalizedPath 使用 local_context 时必须声明 local_context_v1',
          );
          expect(
            raw.contains('media.included') ||
                raw.contains('"media": {"included": false}') ||
                raw.contains('"media":{"included":false}'),
            isTrue,
            reason: '$normalizedPath 使用 local_context 时必须声明不含相册数据',
          );
        }

        final triggerKeywords = frontmatter['trigger_keywords'] ?? '';
        expect(
          RegExp(r'[A-Za-z]').hasMatch(triggerKeywords),
          isFalse,
          reason: '$normalizedPath trigger_keywords 需中文，不应包含英文',
        );

        for (final section in requiredSections) {
          expect(
            raw.contains(section),
            isTrue,
            reason: '$normalizedPath 缺少章节: $section',
          );
        }

        expect(
          raw.contains('assistant_turn_v2'),
          isTrue,
          reason: '$normalizedPath 缺少 assistant_turn_v2',
        );
        expect(
          raw.contains('tool_observation_v1'),
          isTrue,
          reason: '$normalizedPath 缺少 tool_observation_v1',
        );

        for (final token in bannedTokens) {
          expect(
            raw.contains(token),
            isFalse,
            reason: '$normalizedPath 包含禁用词: $token',
          );
        }

        final dir = file.parent;
        for (final rel in parseSpaceList(frontmatter['reference_docs'] ?? '')) {
          final target = File('${dir.path}/$rel');
          expect(
            target.existsSync(),
            isTrue,
            reason: '$normalizedPath 引用不存在的 reference: $rel',
          );
        }
        for (final rel in parseSpaceList(frontmatter['script_guides'] ?? '')) {
          final target = File('${dir.path}/$rel');
          expect(
            target.existsSync(),
            isTrue,
            reason: '$normalizedPath 引用不存在的 script: $rel',
          );
        }
        for (final rel
            in parseSpaceList(frontmatter['dialogue_state_docs'] ?? '')) {
          final target = File('${dir.path}/$rel');
          expect(
            target.existsSync(),
            isTrue,
            reason: '$normalizedPath 引用不存在的 dialogue state doc: $rel',
          );
        }
      }
    });
  });
}

import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:quwoquan_app/personal_assistant/skills/skill_markdown_parser.dart';
import 'package:quwoquan_app/personal_assistant/skills/skill_manifest.dart';
import 'package:yaml/yaml.dart';

class PersonalAssistantSkillLoader {
  const PersonalAssistantSkillLoader();

  Future<List<PersonalAssistantSkillManifest>> loadBundledSkills() async {
    final List<PersonalAssistantSkillManifest> skills =
        <PersonalAssistantSkillManifest>[];
    const markdownParser = SkillMarkdownParser();
    final bundledSkillAssets = await _discoverBundledSkillAssets();
    for (final path in bundledSkillAssets) {
      try {
        var content = '';
        try {
          content = await rootBundle.loadString(path);
        } catch (_) {
          final file = File(path);
          if (await file.exists()) {
            content = await file.readAsString();
          }
        }
        if (content.isEmpty) continue;
        if (path.toLowerCase().endsWith('.md')) {
          final parsed = markdownParser.parse(content);
          final map = <String, dynamic>{
            'id': (parsed.frontmatter['name'] ?? 'unknown_skill')
                .toString()
                .trim(),
            'name': (parsed.frontmatter['name'] ?? 'Unknown Skill')
                .toString()
                .trim(),
            'description': (parsed.frontmatter['description'] ?? '')
                .toString()
                .trim(),
            'version': (parsed.frontmatter['version'] ?? '1.0.0')
                .toString()
                .trim(),
            'executionTarget': 'tool_chain',
            'parametersSchema': const <String, dynamic>{'type': 'object'},
            'visibility': 'both',
            'category': 'domain',
            'tier': 'free',
            'channelScopes': const <String>['app', 'openclaw', 'feishu'],
            'deviceScopes': const <String>['mobile', 'tablet', 'pc'],
            'versionPolicy': 'semver',
            'defaultEnabled': true,
            'domain': (parsed.frontmatter['domain'] ?? '').toString().trim(),
            'allowed_tools': _toStringList(parsed.frontmatter['allowed_tools']),
            'trigger_keywords': _toStringList(
              parsed.frontmatter['trigger_keywords'],
            ),
            'frontmatter': parsed.frontmatter,
            'skill_markdown': parsed.body,
          };
          final manifest = PersonalAssistantSkillManifest.fromMap(map);
          if (manifest.validate().isEmpty) skills.add(manifest);
          continue;
        }
        final yaml = loadYaml(content);
        if (yaml is YamlMap) {
          final map = _yamlMapToDartMap(yaml);
          final manifest = PersonalAssistantSkillManifest.fromMap(map);
          if (manifest.validate().isEmpty) {
            skills.add(manifest);
          }
        }
      } catch (_) {
        // Skip invalid skill files to keep runtime robust.
      }
    }
    return skills;
  }

  Future<List<String>> _discoverBundledSkillAssets() async {
    final assets = <String>{};
    try {
      final manifestContent = await rootBundle.loadString('AssetManifest.json');
      final decoded = jsonDecode(manifestContent);
      if (decoded is Map<String, dynamic>) {
        for (final key in decoded.keys) {
          final path = key.toString();
          if (!path.startsWith('assets/personal_assistant/skills/')) continue;
          if (path.endsWith('/SKILL.md') || path.endsWith('.skill.yaml')) {
            assets.add(path);
          }
        }
      }
    } catch (_) {
      // Fallback for local tests where AssetManifest may be unavailable.
    }
    // Always merge filesystem scan in tests/dev to avoid missing markdown
    // assets when AssetManifest omits uppercase `SKILL.md`.
    final dir = Directory('assets/personal_assistant/skills');
    if (await dir.exists()) {
      await for (final entity in dir.list(recursive: true)) {
        if (entity is! File) continue;
        final path = entity.path.replaceAll('\\', '/');
        if (path.endsWith('/SKILL.md') || path.endsWith('.skill.yaml')) {
          assets.add(path);
        }
      }
    }
    final sorted = assets.toList()..sort();
    return sorted;
  }

  List<String> _toStringList(dynamic value) {
    if (value is List) {
      return value
          .map((item) => item.toString().trim())
          .where((item) => item.isNotEmpty)
          .toList(growable: false);
    }
    if (value is String) {
      return value
          .split(RegExp(r'\s+'))
          .map((item) => item.trim())
          .where((item) => item.isNotEmpty)
          .toList(growable: false);
    }
    return const <String>[];
  }

  Map<String, dynamic> _yamlMapToDartMap(YamlMap map) {
    final result = <String, dynamic>{};
    for (final entry in map.entries) {
      final key = entry.key.toString();
      final value = entry.value;
      if (value is YamlMap) {
        result[key] = _yamlMapToDartMap(value);
      } else if (value is YamlList) {
        result[key] = value.map((e) {
          if (e is YamlMap) {
            return _yamlMapToDartMap(e);
          }
          return e;
        }).toList();
      } else {
        result[key] = value;
      }
    }
    return result;
  }
}

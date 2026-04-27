import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:quwoquan_app/assistant/skill/domain/skill_manifest.dart';
import 'package:quwoquan_app/assistant/skill/loading/skill_markdown_parser.dart';
import 'package:yaml/yaml.dart';

class PersonalAssistantSkillLoader {
  const PersonalAssistantSkillLoader();

  Future<List<PersonalAssistantSkillManifest>> loadBundledSkills() async {
    final skills = <PersonalAssistantSkillManifest>[];
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
          final retrievalPolicy = await _loadSiblingJson(
            skillAssetPath: path,
            relativePath: 'config/retrieval_policy.json',
          );
          final skillName = (parsed.frontmatter['name'] ?? 'unknown_skill')
              .toString()
              .trim();
          final frontmatterDomain = (parsed.frontmatter['domain'] ?? '')
              .toString()
              .trim();
          final pathDomain = _domainIdFromSkillAssetPath(path);
          final domainId = frontmatterDomain.isNotEmpty
              ? frontmatterDomain
              : pathDomain.isNotEmpty
              ? pathDomain
              : _domainIdFromSkillName(skillName);
          final map = <String, dynamic>{
            'id': skillName,
            'name': (parsed.frontmatter['name'] ?? 'Unknown Skill')
                .toString()
                .trim(),
            'description': (parsed.frontmatter['description'] ?? '')
                .toString()
                .trim(),
            'version': (parsed.frontmatter['version'] ?? '1.0.0')
                .toString()
                .trim(),
            'executionTarget':
                (parsed.frontmatter['execution_target'] ?? 'tool_chain')
                    .toString()
                    .trim(),
            'parametersSchema': const <String, dynamic>{'type': 'object'},
            'visibility': 'both',
            'category': 'domain',
            'tier': 'free',
            'channelScopes': const <String>['app', 'openclaw', 'feishu'],
            'deviceScopes': const <String>['mobile', 'tablet', 'pc'],
            'versionPolicy': 'semver',
            'defaultEnabled': true,
            'domain': domainId,
            'allowed_tools': _toStringList(parsed.frontmatter['allowed_tools']),
            'frontmatter': parsed.frontmatter,
            'retrievalPolicy': retrievalPolicy,
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
      final manifest = await AssetManifest.loadFromAssetBundle(rootBundle);
      for (final key in manifest.listAssets()) {
        final path = key.trim();
        if (!path.startsWith('assets/assistant/skills/')) {
          continue;
        }
        if (path.endsWith('/SKILL.md') || path.endsWith('.skill.yaml')) {
          assets.add(path);
        }
      }
    } catch (_) {
      // Fallback for tests or packaging paths where the bundle manifest is unavailable.
    }
    // Always merge filesystem scan in tests/dev to avoid missing markdown
    // assets when AssetManifest omits uppercase `SKILL.md`.
    final dir = Directory('assets/assistant/skills');
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

  String _domainIdFromSkillAssetPath(String path) {
    final normalized = path.replaceAll('\\', '/');
    final segments = normalized.split('/');
    final skillsIndex = segments.indexOf('skills');
    if (skillsIndex < 0 || skillsIndex + 1 >= segments.length) {
      return '';
    }
    return segments[skillsIndex + 1].trim();
  }

  String _domainIdFromSkillName(String name) {
    final normalized = name
        .trim()
        .toLowerCase()
        .replaceAll(RegExp(r'[^a-z0-9]+'), '_')
        .replaceAll(RegExp(r'_+'), '_')
        .replaceAll(RegExp(r'^_|_$'), '');
    return normalized == 'unknown_skill' ? '' : normalized;
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

  Future<Map<String, dynamic>> _loadSiblingJson({
    required String skillAssetPath,
    required String relativePath,
  }) async {
    final normalizedPath = skillAssetPath.replaceAll('\\', '/');
    final slashIndex = normalizedPath.lastIndexOf('/');
    if (slashIndex < 0) return const <String, dynamic>{};
    final basePath = normalizedPath.substring(0, slashIndex);
    final candidate = '$basePath/$relativePath';
    try {
      final content = await rootBundle.loadString(candidate);
      final decoded = jsonDecode(content);
      if (decoded is Map<String, dynamic>) {
        return decoded;
      }
      if (decoded is Map) {
        return decoded.cast<String, dynamic>();
      }
    } catch (_) {
      final file = File(candidate);
      if (await file.exists()) {
        try {
          final decoded = jsonDecode(await file.readAsString());
          if (decoded is Map<String, dynamic>) {
            return decoded;
          }
          if (decoded is Map) {
            return decoded.cast<String, dynamic>();
          }
        } catch (_) {
          return const <String, dynamic>{};
        }
      }
    }
    return const <String, dynamic>{};
  }

  Map<String, dynamic> _yamlMapToDartMap(YamlMap map) {
    final result = <String, dynamic>{};
    for (final entry in map.entries) {
      final key = entry.key.toString();
      final value = entry.value;
      if (value is YamlMap) {
        result[key] = _yamlMapToDartMap(value);
      } else if (value is YamlList) {
        result[key] = value.map((item) {
          if (item is YamlMap) {
            return _yamlMapToDartMap(item);
          }
          return item;
        }).toList();
      } else {
        result[key] = value;
      }
    }
    return result;
  }
}

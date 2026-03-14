import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:quwoquan_app/assistant/skills/skill_manifest.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:yaml/yaml.dart';

class SkillMarkdownParseResult {
  const SkillMarkdownParseResult({
    required this.frontmatter,
    required this.body,
  });

  final Map<String, dynamic> frontmatter;
  final String body;
}

class SkillMarkdownParser {
  const SkillMarkdownParser();

  SkillMarkdownParseResult parse(String raw) {
    final text = raw.replaceAll('\r\n', '\n');
    if (!text.startsWith('---\n')) {
      return SkillMarkdownParseResult(
        frontmatter: const <String, dynamic>{},
        body: text.trim(),
      );
    }
    final end = text.indexOf('\n---\n', 4);
    if (end < 0) {
      return SkillMarkdownParseResult(
        frontmatter: const <String, dynamic>{},
        body: text.trim(),
      );
    }
    final fmRaw = text.substring(4, end).trim();
    final body = text.substring(end + 5).trim();
    return SkillMarkdownParseResult(
      frontmatter: _parseFrontmatter(fmRaw),
      body: body,
    );
  }

  Map<String, dynamic> _parseFrontmatter(String raw) {
    try {
      final yaml = loadYaml(raw);
      if (yaml is YamlMap) {
        return _yamlMapToDartMap(yaml);
      }
    } catch (_) {
      // Fall through to the permissive parser.
    }
    final out = <String, dynamic>{};
    final lines = raw.split('\n');
    for (final line in lines) {
      final trimmed = line.trim();
      if (trimmed.isEmpty || trimmed.startsWith('#')) continue;
      final sep = trimmed.indexOf(':');
      if (sep <= 0) continue;
      final key = trimmed.substring(0, sep).trim();
      final valueRaw = trimmed.substring(sep + 1).trim();
      out[key] = _parseValue(valueRaw);
    }
    return out;
  }

  dynamic _parseValue(String raw) {
    if (raw.isEmpty) return '';
    if (raw.startsWith('[') && raw.endsWith(']')) {
      final inside = raw.substring(1, raw.length - 1).trim();
      if (inside.isEmpty) return const <String>[];
      return inside
          .split(',')
          .map((item) => _stripQuotes(item.trim()))
          .where((item) => item.isNotEmpty)
          .toList(growable: false);
    }
    return _stripQuotes(raw);
  }

  String _stripQuotes(String value) {
    final v = value.trim();
    if (v.length >= 2 &&
        ((v.startsWith('"') && v.endsWith('"')) ||
            (v.startsWith("'") && v.endsWith("'")))) {
      return v.substring(1, v.length - 1).trim();
    }
    return v;
  }

  Map<String, dynamic> _yamlMapToDartMap(YamlMap map) {
    final result = <String, dynamic>{};
    for (final entry in map.entries) {
      final key = entry.key.toString();
      final value = entry.value;
      if (value is YamlMap) {
        result[key] = _yamlMapToDartMap(value);
      } else if (value is YamlList) {
        result[key] = value
            .map((item) {
              if (item is YamlMap) return _yamlMapToDartMap(item);
              if (item is YamlList) return item.toList(growable: false);
              return item;
            })
            .toList(growable: false);
      } else {
        result[key] = value;
      }
    }
    return result;
  }
}

class SkillSubscriptionStore {
  static const String _key = 'personal_' 'assistant_enabled_skills';

  Future<Set<String>> loadEnabledSkillIds() async {
    final prefs = await SharedPreferences.getInstance();
    final values = prefs.getStringList(_key) ?? <String>[];
    return values.toSet();
  }

  Future<void> setSkillEnabled(String skillId, bool enabled) async {
    final prefs = await SharedPreferences.getInstance();
    final current = (prefs.getStringList(_key) ?? <String>[]).toSet();
    if (enabled) {
      current.add(skillId);
    } else {
      current.remove(skillId);
    }
    await prefs.setStringList(_key, current.toList(growable: false));
  }
}

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
            'domain': (parsed.frontmatter['domain'] ?? '').toString().trim(),
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
      final manifestContent = await rootBundle.loadString('AssetManifest.json');
      final decoded = jsonDecode(manifestContent);
      if (decoded is Map<String, dynamic>) {
        for (final key in decoded.keys) {
          final path = key.toString();
          if (!path.startsWith('assets/personal_' 'assistant/skills/')) {
            continue;
          }
          if (path.endsWith('/SKILL.md') || path.endsWith('.skill.yaml')) {
            assets.add(path);
          }
        }
      }
    } catch (_) {
      // Fallback for local tests where AssetManifest may be unavailable.
    }
    final dir = Directory('assets/personal_' 'assistant/skills');
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

class AssistantSkillMarketService {
  AssistantSkillMarketService({
    PersonalAssistantSkillLoader? loader,
    SkillSubscriptionStore? subscriptionStore,
  }) : _loader = loader ?? const PersonalAssistantSkillLoader(),
       _subscriptionStore = subscriptionStore ?? SkillSubscriptionStore();

  final PersonalAssistantSkillLoader _loader;
  final SkillSubscriptionStore _subscriptionStore;
  List<PersonalAssistantSkillInfo>? _cachedSkills;

  Future<List<PersonalAssistantSkillInfo>> listSkills() async {
    final cached = _cachedSkills;
    if (cached != null) return cached;
    return refreshSkills();
  }

  Future<List<PersonalAssistantSkillInfo>> refreshSkills() async {
    final manifests = await _loader.loadBundledSkills();
    final enabledIds = await _subscriptionStore.loadEnabledSkillIds();
    final result = manifests
        .map(
          (m) => PersonalAssistantSkillInfo(
            manifest: m,
            enabled: m.defaultEnabled || enabledIds.contains(m.id),
            source: 'bundled',
            version: m.version,
            category: m.category,
            tier: m.tier,
            isDefaultFree: m.tier == 'free' && m.defaultEnabled,
          ),
        )
        .toList(growable: false);
    _cachedSkills = result;
    return result;
  }

  Future<void> setSkillEnabled(String skillId, bool enabled) async {
    await _subscriptionStore.setSkillEnabled(skillId, enabled);
    _cachedSkills = null;
  }
}

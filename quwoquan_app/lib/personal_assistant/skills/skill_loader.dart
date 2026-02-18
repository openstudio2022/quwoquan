import 'dart:io';

import 'package:flutter/services.dart';
import 'package:quwoquan_app/personal_assistant/skills/skill_manifest.dart';
import 'package:yaml/yaml.dart';

class PersonalAssistantSkillLoader {
  const PersonalAssistantSkillLoader();

  static const List<String> bundledSkillAssets = <String>[
    'assets/personal_assistant/skills/knowledge_qa.skill.yaml',
    'assets/personal_assistant/skills/photo.organize.skill.yaml',
    'assets/personal_assistant/skills/web.quick_search.skill.yaml',
    'assets/personal_assistant/skills/reminder.intent.skill.yaml',
  ];

  Future<List<PersonalAssistantSkillManifest>> loadBundledSkills() async {
    final List<PersonalAssistantSkillManifest> skills = <PersonalAssistantSkillManifest>[];
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

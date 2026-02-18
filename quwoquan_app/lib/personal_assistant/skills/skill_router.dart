import 'package:quwoquan_app/personal_assistant/skills/skill_manifest.dart';

class PersonalAssistantSkillRouter {
  const PersonalAssistantSkillRouter();

  PersonalAssistantSkillManifest? resolveSkill(
    String userText,
    List<PersonalAssistantSkillManifest> skills,
  ) {
    final normalized = userText.toLowerCase();
    final knowledgeKeywords = <String>[
      '搜索',
      'search',
      '财经',
      '天气',
      '出行',
      '旅行',
      '情感',
      '疾病',
      '健康',
      '易经',
      '卜卦',
      '百科',
      '知识',
    ];
    if (knowledgeKeywords.any(normalized.contains)) {
      for (final skill in skills) {
        final id = skill.id.toLowerCase();
        if (id == 'knowledge_qa' || id.contains('quick_search')) {
          return skill;
        }
      }
    }
    for (final skill in skills) {
      final skillName = skill.name.toLowerCase();
      final skillId = skill.id.toLowerCase();
      if (normalized.contains(skillName) || normalized.contains(skillId)) {
        return skill;
      }
    }
    if (normalized.contains('搜索') || normalized.contains('search')) {
      for (final skill in skills) {
        if (skill.id.toLowerCase().contains('search')) {
          return skill;
        }
      }
    }
    return null;
  }
}

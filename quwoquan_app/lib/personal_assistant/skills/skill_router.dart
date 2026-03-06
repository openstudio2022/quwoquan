import 'package:quwoquan_app/personal_assistant/skills/skill_manifest.dart';

class PersonalAssistantSkillRouter {
  const PersonalAssistantSkillRouter();

  PersonalAssistantSkillManifest? resolveSkill(
    String userText,
    List<PersonalAssistantSkillManifest> skills,
  ) {
    final normalized = userText.toLowerCase();
    final matchedByTrigger = _matchByTriggerKeywords(normalized, skills);
    if (matchedByTrigger != null) return matchedByTrigger;
    for (final skill in skills) {
      final skillName = skill.name.toLowerCase();
      final skillId = skill.id.toLowerCase();
      if (normalized.contains(skillName) || normalized.contains(skillId)) {
        return skill;
      }
    }
    return null;
  }

  PersonalAssistantSkillManifest? resolveSkillForDomain({
    required String userText,
    required String domainId,
    required List<PersonalAssistantSkillManifest> skills,
  }) {
    final normalized = userText.toLowerCase();
    final inDomain = skills
        .where((skill) => skill.domainId.trim() == domainId.trim())
        .toList(growable: false);
    if (inDomain.isNotEmpty) {
      final byTrigger = _matchByTriggerKeywords(normalized, inDomain);
      if (byTrigger != null) return byTrigger;
      return inDomain.first;
    }
    return resolveSkill(userText, skills);
  }

  PersonalAssistantSkillManifest? _matchByTriggerKeywords(
    String normalizedUserText,
    List<PersonalAssistantSkillManifest> skills,
  ) {
    for (final skill in skills) {
      if (skill.triggerKeywords.isEmpty) continue;
      for (final keyword in skill.triggerKeywords) {
        final token = keyword.trim().toLowerCase();
        if (token.isEmpty) continue;
        if (normalizedUserText.contains(token)) {
          return skill;
        }
      }
    }
    return null;
  }
}

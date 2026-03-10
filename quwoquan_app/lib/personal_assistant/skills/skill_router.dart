import 'package:quwoquan_app/personal_assistant/contracts/recall_result.dart';
import 'package:quwoquan_app/personal_assistant/skills/skill_manifest.dart';

class PersonalAssistantSkillRouter {
  const PersonalAssistantSkillRouter();

  PersonalAssistantSkillManifest? resolveSkill(
    String userText,
    List<PersonalAssistantSkillManifest> skills,
  ) {
    final normalized = _normalizeForMatch(userText);
    final matchedByTrigger = _matchByTriggerKeywords(normalized, skills);
    if (matchedByTrigger != null) return matchedByTrigger;
    for (final skill in skills) {
      final skillName = _normalizeForMatch(skill.name);
      final skillId = _normalizeForMatch(skill.id);
      if (normalized.contains(skillName) || normalized.contains(skillId)) {
        return skill;
      }
    }
    return null;
  }

  /// Resolve skill using recall results — preferred path when a recall layer
  /// has already pre-filtered the catalog.
  PersonalAssistantSkillManifest? resolveFromRecall({
    required RecallResult recallResult,
    required List<PersonalAssistantSkillManifest> allSkills,
  }) {
    if (recallResult.isEmpty) return null;
    final topDomainId = recallResult.topK.first.domainId;
    for (final skill in allSkills) {
      if (skill.domainId == topDomainId) return skill;
    }
    return null;
  }

  PersonalAssistantSkillManifest? resolveSkillForDomain({
    required String userText,
    required String domainId,
    required List<PersonalAssistantSkillManifest> skills,
  }) {
    final normalized = _normalizeForMatch(userText);
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
        final token = _normalizeForMatch(keyword);
        if (token.isEmpty) continue;
        if (normalizedUserText.contains(token)) {
          return skill;
        }
      }
    }
    return null;
  }

  String _normalizeForMatch(String raw) {
    final lower = raw.toLowerCase().trim();
    if (lower.isEmpty) return '';
    return lower.replaceAll(RegExp(r'[\s_\-.,，。！？!?/\\]+'), '');
  }
}

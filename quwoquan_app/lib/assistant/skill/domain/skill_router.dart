import 'package:quwoquan_app/assistant/contracts/recall_result.dart';
import 'package:quwoquan_app/assistant/skill/domain/skill_manifest.dart';

class PersonalAssistantSkillRouter {
  const PersonalAssistantSkillRouter();

  PersonalAssistantSkillManifest? resolveSkill(
    String userText,
    List<PersonalAssistantSkillManifest> skills,
  ) {
    final normalized = _normalizeForMatch(userText);
    for (final skill in skills) {
      final domainId = _normalizeForMatch(skill.domainId);
      final skillId = _normalizeForMatch(skill.id);
      if ((domainId.isNotEmpty && normalized == domainId) ||
          (skillId.isNotEmpty && normalized == skillId)) {
        return skill;
      }
    }
    return null;
  }

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
    final inDomain = skills
        .where((skill) => skill.domainId.trim() == domainId.trim())
        .toList(growable: false);
    if (inDomain.isNotEmpty) {
      return inDomain.first;
    }
    return resolveSkill(userText, skills);
  }

  String _normalizeForMatch(String raw) {
    final lower = raw.toLowerCase().trim();
    if (lower.isEmpty) return '';
    return lower.replaceAll(RegExp(r'[\s_\-.,，。！？!?/\\]+'), '');
  }
}

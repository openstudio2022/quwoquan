import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/internal_legacy/skills/skill_manifest.dart';
import 'package:quwoquan_app/assistant/internal_legacy/skills/skill_router.dart';

void main() {
  group('PersonalAssistantSkillRouter', () {
    const router = PersonalAssistantSkillRouter();
    final weatherSkill = PersonalAssistantSkillManifest(
      id: 'weather',
      name: 'weather-realtime',
      description: '天气技能',
      version: '1.0.0',
      executionTarget: 'local',
      parametersSchema: const <String, dynamic>{},
      domainId: 'weather',
      triggerKeywords: const <String>['天气', 'weather', 'tianqi', 'tian qi'],
    );
    final fallbackSkill = PersonalAssistantSkillManifest(
      id: 'fallback_general_search',
      name: 'fallback',
      description: '兜底技能',
      version: '1.0.0',
      executionTarget: 'local',
      parametersSchema: const <String, dynamic>{},
      domainId: 'fallback_general_search',
    );

    test('仅在显式 domainId 或 skillId 命中时解析技能', () {
      final resolved = router.resolveSkill(
        'weather',
        <PersonalAssistantSkillManifest>[weatherSkill, fallbackSkill],
      );

      expect(resolved?.domainId, equals('weather'));
    });

    test('域内解析直接返回同域技能，不再依赖 trigger keyword', () {
      final resolved = router.resolveSkillForDomain(
        userText: 'what is the weather in shenzhen',
        domainId: 'weather',
        skills: <PersonalAssistantSkillManifest>[weatherSkill, fallbackSkill],
      );

      expect(resolved?.domainId, equals('weather'));
    });
  });
}

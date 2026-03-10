import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/personal_assistant/skills/skill_manifest.dart';
import 'package:quwoquan_app/personal_assistant/skills/skill_router.dart';

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

    test('可识别带空格的拼音天气问法', () {
      final resolved = router.resolveSkill(
        'Shenzhen tian qi',
        <PersonalAssistantSkillManifest>[weatherSkill, fallbackSkill],
      );

      expect(resolved?.domainId, equals('weather'));
    });

    test('域内匹配时优先使用归一化 trigger keyword', () {
      final resolved = router.resolveSkillForDomain(
        userText: 'what is the weather in shenzhen',
        domainId: 'weather',
        skills: <PersonalAssistantSkillManifest>[weatherSkill, fallbackSkill],
      );

      expect(resolved?.domainId, equals('weather'));
    });
  });
}

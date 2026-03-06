import 'package:quwoquan_app/personal_assistant/skills/skill_loader.dart';
import 'package:quwoquan_app/personal_assistant/skills/skill_router.dart';
import 'package:test/test.dart';

void main() {
  group('Skill loader commercial fields', () {
    test('loads all vertical SKILL.md assets dynamically', () async {
      final loader = const PersonalAssistantSkillLoader();
      final skills = await loader.loadBundledSkills();
      final domainSkills = skills
          .where(
            (s) =>
                s.id != 'knowledge_qa' &&
                s.id != 'photo.organize' &&
                s.id != 'web.quick_search' &&
                s.id != 'reminder.intent',
          )
          .toList(growable: false);
      expect(domainSkills.length, greaterThanOrEqualTo(19));
      final domains = domainSkills.map((s) => s.domainId).toSet();
      expect(domains.contains('divination_fortune'), isTrue);
      expect(domains.contains('relationship_matchmaking'), isTrue);
      expect(domains.contains('weather'), isTrue);
    });

    test('includes knowledge_qa and commercial governance fields', () async {
      final loader = const PersonalAssistantSkillLoader();
      final skills = await loader.loadBundledSkills();
      final knowledge = skills.where((s) => s.id == 'knowledge_qa').toList();
      expect(knowledge, isNotEmpty);
      final skill = knowledge.first;
      expect(skill.tier, equals('free'));
      expect(skill.channelScopes, contains('feishu'));
      expect(skill.deviceScopes, contains('pc'));
      expect(skill.defaultEnabled, isTrue);
    });

    test('loads weather skill from SKILL.md with instruction body', () async {
      final loader = const PersonalAssistantSkillLoader();
      final skills = await loader.loadBundledSkills();
      final weather = skills.where((s) => s.id == 'weather-realtime').toList();
      expect(weather, isNotEmpty);
      final skill = weather.first;
      expect(skill.domainId, equals('weather'));
      expect(skill.allowedTools, contains('web_search'));
      expect(
        skill.skillInstructionMarkdown,
        allOf(
          contains('assistant_turn_v2'),
          contains('tool_observation_v1'),
          contains('双轨输出契约'),
        ),
      );
    });

    test('loads fortune skill from SKILL.md and routes by trigger', () async {
      final loader = const PersonalAssistantSkillLoader();
      final router = const PersonalAssistantSkillRouter();
      final skills = await loader.loadBundledSkills();
      final fortune = skills.where((s) => s.id == 'fortune-daily').toList();
      expect(fortune, isNotEmpty);
      final skill = fortune.first;
      expect(skill.domainId, equals('divination_fortune'));
      expect(skill.allowedTools, contains('web_search'));
      final matched = router.resolveSkillForDomain(
        userText: '今天的运势怎么样？',
        domainId: 'divination_fortune',
        skills: skills,
      );
      expect(matched?.id, equals('fortune-daily'));
    });
  });
}

import 'package:quwoquan_app/personal_assistant/skills/skill_loader.dart';
import 'package:test/test.dart';

void main() {
  group('Skill loader commercial fields', () {
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
  });
}


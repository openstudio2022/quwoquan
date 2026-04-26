import 'package:quwoquan_app/assistant/skill/domain/skill_router.dart';
import 'package:quwoquan_app/assistant/skills/assistant_skill_runtime.dart';
import 'package:quwoquan_app/assistant/conversation/explainability/dialogue_state_runtime.dart';
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
      expect(skill.allowedTools, contains('search'));
      expect(skill.allowedTools.first, equals('search'));
    });

    test('loads weather skill from SKILL.md with instruction body', () async {
      final loader = const PersonalAssistantSkillLoader();
      final skills = await loader.loadBundledSkills();
      final weather = skills.where((s) => s.id == 'weather-realtime').toList();
      expect(weather, isNotEmpty);
      final skill = weather.first;
      expect(skill.domainId, equals('weather'));
      expect(skill.allowedTools, contains('search'));
      expect(skill.allowedTools, contains('web_search'));
      expect(
        skill.allowedTools.indexOf('search'),
        lessThan(skill.allowedTools.indexOf('web_search')),
      );
      expect(skill.retrievalPolicy['domainId'], equals('weather'));
      expect(skill.executionShell.problemClass, equals('realtime_info'));
      expect(skill.executionShell.variantBudget, equals(0));
      expect(skill.executionShell.reflectionBudget, equals(0));
      expect(skill.executionShell.providerPolicy, equals('authority_first'));
      expect(skill.executionShell.authorityDomains, contains('weather.cma.cn'));
      expect(skill.executionShell.authorityDomains, contains('weather.com.cn'));
      expect(skill.executionShell.freshnessHoursMax, equals(1));
      expect(
        skill.skillInstructionMarkdown,
        allOf(
          contains('assistant_turn'),
          contains('tool_observation_v1'),
          contains('双轨输出契约'),
        ),
      );
    });

    test(
      'loads fallback skill with adaptive baseline execution shell',
      () async {
        final loader = const PersonalAssistantSkillLoader();
        final skills = await loader.loadBundledSkills();
        final fallback = skills
            .where((s) => s.id == 'fallback_general_search')
            .toList();
        expect(fallback, isNotEmpty);
        final skill = fallback.first;
        expect(skill.domainId, equals('fallback_general_search'));
        expect(skill.allowedTools, contains('search'));
        expect(skill.allowedTools, contains('web_search'));
        expect(skill.allowedTools.first, equals('search'));
        expect(skill.executionShell.problemClass, equals('general'));
        expect(skill.executionShell.maxIterations, equals(4));
        expect(skill.executionShell.toolBudget, equals(2));
        expect(skill.executionShell.variantBudget, equals(1));
        expect(skill.executionShell.reflectionBudget, equals(1));
        expect(skill.executionShell.freshnessHoursMax, equals(24));
      },
    );

    test('loads fortune skill from SKILL.md and routes by trigger', () async {
      final loader = const PersonalAssistantSkillLoader();
      final router = const PersonalAssistantSkillRouter();
      final skills = await loader.loadBundledSkills();
      final fortune = skills.where((s) => s.id == 'fortune-daily').toList();
      expect(fortune, isNotEmpty);
      final skill = fortune.first;
      expect(skill.domainId, equals('divination_fortune'));
      expect(skill.allowedTools, contains('search'));
      expect(skill.allowedTools, contains('web_search'));
      expect(skill.allowedTools.first, equals('search'));
      final matched = router.resolveSkillForDomain(
        userText: '今天的运势怎么样？',
        domainId: 'divination_fortune',
        skills: skills,
      );
      expect(matched?.id, equals('fortune-daily'));
    });

    test(
      'knowledge skill opt-in metadata controls QA tool-chain profile',
      () async {
        final loader = const PersonalAssistantSkillLoader();
        final skills = await loader.loadBundledSkills();
        final knowledge = skills
            .where((s) => s.id == 'knowledge_general')
            .toList();
        expect(knowledge, isNotEmpty);
        expect(knowledge.first.toolChainProfile, equals('knowledge_qa'));
      },
    );

    test('all bundled skills expose explicit shell and dialogue runtime state', () async {
      final loader = const PersonalAssistantSkillLoader();
      final dialogueRuntime = DialogueStateRuntime();
      final skills = await loader.loadBundledSkills();
      final domainSkills = skills
          .where((skill) => skill.domainId.trim().isNotEmpty)
          .toList(growable: false);

      expect(domainSkills.length, greaterThanOrEqualTo(19));

      for (final skill in domainSkills) {
        expect(skill.id.trim(), isNotEmpty, reason: '${skill.domainId}: skill id');
        expect(
          skill.description.trim(),
          isNotEmpty,
          reason: '${skill.id}: description',
        );
        expect(
          skill.skillInstructionMarkdown.trim(),
          isNotEmpty,
          reason: '${skill.id}: SKILL.md body',
        );
        expect(skill.allowedTools, isNotEmpty, reason: '${skill.id}: allowed_tools');
        expect(
          skill.executionShell.maxIterations,
          greaterThan(0),
          reason: '${skill.id}: execution_shell.maxIterations',
        );
        expect(
          skill.executionShell.toolBudget,
          greaterThan(0),
          reason: '${skill.id}: execution_shell.toolBudget',
        );

        final shellMap =
            (skill.frontmatter['execution_shell'] as Map?)
                ?.cast<String, dynamic>() ??
            const <String, dynamic>{};
        final hasExplicitProblemClass =
            ((shellMap['problemClass'] as String?)?.trim().isNotEmpty ?? false) ||
            ((skill.frontmatter['problem_class'] as String?)?.trim().isNotEmpty ??
                false);
        if (!hasExplicitProblemClass) {
          expect(
            skill.executionShell.problemClass,
            equals('general'),
            reason:
                '${skill.id}: runtime 不得再从 mode 推导 problemClass，缺显式配置时只能保持 general',
          );
        }

        final script = await dialogueRuntime.buildRoundScript(
          domainId: skill.domainId,
          userQuery: '验证 ${skill.domainId} 技能状态',
          contextScopeHint: const <String, dynamic>{},
        );
        expect(script.enabled, isTrue, reason: '${skill.id}: dialogue enabled');
        expect(
          script.currentStateId.trim(),
          isNotEmpty,
          reason: '${skill.id}: current state',
        );
        expect(
          script.suggestedNextStateId.trim(),
          isNotEmpty,
          reason: '${skill.id}: suggested next state',
        );
      }
    });
  });
}

import 'dart:convert';
import 'dart:io';

import 'package:test/test.dart';

void main() {
  group('Domain quality benchmark', () {
    final benchmarkFile = File(
      'test/assistant/domain_quality_benchmark_cases.json',
    );

    test('benchmark dataset is complete for 19 domains', () {
      expect(benchmarkFile.existsSync(), isTrue);
      final decoded = jsonDecode(benchmarkFile.readAsStringSync()) as Map;
      final domains =
          (decoded['domains'] as List?)?.whereType<Map>().toList(
            growable: false,
          ) ??
          const <Map>[];
      expect(domains.length, equals(19));
      for (final domain in domains) {
        final cases =
            (domain['cases'] as List?)?.whereType<Map>().toList(
              growable: false,
            ) ??
            const <Map>[];
        expect(cases.length >= 3 && cases.length <= 5, isTrue);
        expect(cases.any((c) => c['multiTurn'] == true), isTrue);
      }
    });

    test('run per-domain benchmark and enforce first-class quality score', () {
      final decoded = jsonDecode(benchmarkFile.readAsStringSync()) as Map;
      final domains =
          (decoded['domains'] as List?)?.whereType<Map>().toList(
            growable: false,
          ) ??
          const <Map>[];
      final failures = <String>[];

      for (final domain in domains) {
        final domainId = (domain['domainId'] ?? '').toString();
        final cases =
            (domain['cases'] as List?)?.whereType<Map>().toList(
              growable: false,
            ) ??
            const <Map>[];
        final score = _evaluateSkillDomain(domainId: domainId, cases: cases);
        if (score < 0) {
          failures.add('$domainId: missing skill baseline');
          continue;
        }
        if (score < 0.85) {
          failures.add('$domainId: score=${score.toStringAsFixed(2)} < 0.85');
        }
      }

      if (failures.isNotEmpty) {
        fail('Domain quality benchmark failed:\n${failures.join('\n')}');
      }
    });
  });
}

double _evaluateSkillDomain({
  required String domainId,
  required List<Map> cases,
}) {
  final skillPath = _migratedSkillByDomain[domainId];
  if (skillPath == null) return -1;
  final skillFile = File(skillPath);
  if (!skillFile.existsSync()) return -1;
  final raw = skillFile.readAsStringSync();
  var score = 0.0;
  final requiredSections = <String>[
    '## 目标',
    '## 工具调用策略',
    '## 触发与禁用条件',
    '## 双轨输出契约',
    '## Markdown 卡片结构',
    '## 参考资料',
    '## 脚本指引',
    '## 轮次状态定义',
  ];
  if (requiredSections.every(raw.contains)) score += 0.4;
  if (raw.contains('assistant_turn')) score += 0.15;
  if (raw.contains('tool_observation_v1')) score += 0.15;
  if (raw.contains('dialogue/state_transition_contract.json')) score += 0.1;
  if (_highRiskDomains.contains(domainId)) {
    if (raw.contains('仅供参考') || raw.contains('不确定性声明')) score += 0.1;
  } else {
    score += 0.1;
  }

  var casePass = 0;
  for (final qa in cases) {
    final mustContain =
        (qa['mustContain'] as List?)?.whereType<String>().toList(
          growable: false,
        ) ??
        const <String>[];
    final hit = mustContain.where((item) => raw.contains(item)).length;
    if (mustContain.isEmpty || (hit / mustContain.length) >= 0.3) {
      casePass += 1;
    }
  }
  final caseRatio = cases.isEmpty ? 0.0 : casePass / cases.length;
  score += 0.1 * caseRatio;
  return score;
}

const Set<String> _highRiskDomains = <String>{
  'emotion_companion',
  'relationship_matchmaking',
  'divination_fortune',
  'astrology_constellation',
  'family_parenting',
};

const Map<String, String> _migratedSkillByDomain = <String, String>{
  'weather': 'assets/assistant/skills/weather/SKILL.md',
  'travel_transport':
      'assets/assistant/skills/travel_transport/SKILL.md',
  'travel_planning':
      'assets/assistant/skills/travel_planning/SKILL.md',
  'local_life': 'assets/assistant/skills/local_life/SKILL.md',
  'calendar_task': 'assets/assistant/skills/calendar_task/SKILL.md',
  'knowledge_general':
      'assets/assistant/skills/knowledge_general/SKILL.md',
  'finance_consumer':
      'assets/assistant/skills/finance_consumer/SKILL.md',
  'health_wellness':
      'assets/assistant/skills/health_wellness/SKILL.md',
  'education_learning':
      'assets/assistant/skills/education_learning/SKILL.md',
  'work_productivity':
      'assets/assistant/skills/work_productivity/SKILL.md',
  'shopping_decision':
      'assets/assistant/skills/shopping_decision/SKILL.md',
  'policy_public_service':
      'assets/assistant/skills/policy_public_service/SKILL.md',
  'emotion_companion':
      'assets/assistant/skills/emotion_companion/SKILL.md',
  'social_companion_chat':
      'assets/assistant/skills/social_companion_chat/SKILL.md',
  'relationship_matchmaking':
      'assets/assistant/skills/relationship_matchmaking/SKILL.md',
  'divination_fortune':
      'assets/assistant/skills/divination_fortune/SKILL.md',
  'astrology_constellation':
      'assets/assistant/skills/astrology_constellation/SKILL.md',
  'family_parenting':
      'assets/assistant/skills/family_parenting/SKILL.md',
  'fallback_general_search':
      'assets/assistant/skills/fallback_general_search/SKILL.md',
};

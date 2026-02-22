import 'dart:convert';
import 'dart:io';

import 'package:test/test.dart';

void main() {
  group('Domain quality benchmark', () {
    final benchmarkFile = File(
      'test/personal_assistant/domain_quality_benchmark_cases.json',
    );

    test('benchmark dataset is complete for 19 domains', () {
      expect(benchmarkFile.existsSync(), isTrue);
      final decoded = jsonDecode(benchmarkFile.readAsStringSync()) as Map;
      final domains =
          (decoded['domains'] as List?)?.whereType<Map>().toList(growable: false) ??
          const <Map>[];
      expect(domains.length, equals(19));
      for (final domain in domains) {
        final cases =
            (domain['cases'] as List?)?.whereType<Map>().toList(growable: false) ??
            const <Map>[];
        expect(cases.length >= 3 && cases.length <= 5, isTrue);
        expect(cases.any((c) => c['multiTurn'] == true), isTrue);
      }
    });

    test('run per-domain benchmark and enforce first-class quality score', () {
      final decoded = jsonDecode(benchmarkFile.readAsStringSync()) as Map;
      final domains =
          (decoded['domains'] as List?)?.whereType<Map>().toList(growable: false) ??
          const <Map>[];
      final failures = <String>[];

      for (final domain in domains) {
        final domainId = (domain['domainId'] ?? '').toString();
        final cases =
            (domain['cases'] as List?)?.whereType<Map>().toList(growable: false) ??
            const <Map>[];
        final planMd = File(
          'assets/personal_assistant/prompts/domains/$domainId/domain.$domainId.plan.md',
        );
        final answerMd = File(
          'assets/personal_assistant/prompts/domains/$domainId/domain.$domainId.answer.md',
        );
        final planMeta = File(
          'assets/personal_assistant/prompts/domains/$domainId/domain.$domainId.plan.meta.json',
        );
        final answerMeta = File(
          'assets/personal_assistant/prompts/domains/$domainId/domain.$domainId.answer.meta.json',
        );
        if (!planMd.existsSync() ||
            !answerMd.existsSync() ||
            !planMeta.existsSync() ||
            !answerMeta.existsSync()) {
          failures.add('$domainId: template assets missing');
          continue;
        }
        final planText = planMd.readAsStringSync();
        final answerText = answerMd.readAsStringSync();
        final answerMetaJson =
            jsonDecode(answerMeta.readAsStringSync()) as Map<String, dynamic>;
        final score = _evaluateDomain(
          domainId: domainId,
          planText: planText,
          answerText: answerText,
          answerMeta: answerMetaJson,
          cases: cases,
        );
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

double _evaluateDomain({
  required String domainId,
  required String planText,
  required String answerText,
  required Map<String, dynamic> answerMeta,
  required List<Map> cases,
}) {
  var score = 0.0;
  final mandatorySections = <String>[
    '## 任务背景',
    '## 任务目标',
    '## 约束',
    '## 执行要求',
    '## 输出格式',
    '## 反思与自检',
    '=== CONTEXT_DATA_START ===',
    '=== CONTEXT_DATA_END ===',
  ];
  final hasAllPlanSections = mandatorySections.every(planText.contains);
  final hasAllAnswerSections = mandatorySections.every(answerText.contains);
  if (hasAllPlanSections) score += 0.2;
  if (hasAllAnswerSections) score += 0.2;

  final outputContract = (answerMeta['outputContract'] ?? '').toString();
  if (outputContract == 'domain_answer_v2026_02_18') score += 0.1;
  final requiredVars = (answerMeta['requiredVariables'] as List?)
          ?.whereType<String>()
          .toList(growable: false) ??
      const <String>[];
  if (requiredVars.contains('domainResults') && requiredVars.contains('contextSlots')) {
    score += 0.1;
  }
  final selfCheckRules = (answerMeta['selfCheckRules'] as List?)
          ?.whereType<String>()
          .toList(growable: false) ??
      const <String>[];
  if (selfCheckRules.length >= 3) score += 0.1;

  final lower = answerText.toLowerCase();
  if (domainId == 'fallback_general_search') {
    if (lower.contains('online') && lower.contains('offline')) score += 0.1;
  } else if (_highRiskDomains.contains(domainId)) {
    if (answerText.contains('免责声明') || answerText.contains('边界')) score += 0.1;
  } else {
    score += 0.1;
  }

  var casePass = 0;
  for (final qa in cases) {
    final mustContain =
        (qa['mustContain'] as List?)?.whereType<String>().toList(growable: false) ??
            const <String>[];
    final hit = mustContain.where((item) => answerText.contains(item)).length;
    if (mustContain.isEmpty) {
      casePass += 1;
      continue;
    }
    final ratio = hit / mustContain.length;
    if (ratio >= 0.5) casePass += 1;
  }
  final caseRatio = cases.isEmpty ? 0.0 : casePass / cases.length;
  score += 0.2 * caseRatio;

  return score;
}

const Set<String> _highRiskDomains = <String>{
  'emotion_companion',
  'relationship_matchmaking',
  'divination_fortune',
  'astrology_constellation',
  'family_parenting',
};


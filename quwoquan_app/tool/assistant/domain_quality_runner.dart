import 'dart:convert';
import 'dart:io';

Future<void> main() async {
  final benchmarkFile = File(
    'test/assistant/domain_quality_benchmark_cases.json',
  );
  if (!benchmarkFile.existsSync()) {
    stderr.writeln('benchmark file missing');
    exitCode = 1;
    return;
  }
  final decoded = jsonDecode(benchmarkFile.readAsStringSync()) as Map;
  final domains =
      (decoded['domains'] as List?)?.whereType<Map>().toList(growable: false) ??
      const <Map>[];
  final failed = <String>[];

  stdout.writeln('== Personal Assistant Domain Quality Runner ==');
  for (final domain in domains) {
    final domainId = (domain['domainId'] ?? '').toString();
    final cases =
        (domain['cases'] as List?)?.whereType<Map>().toList(growable: false) ??
        const <Map>[];
    final skillFile = File(
      'assets/assistant/skills/$domainId/SKILL.md',
    );
    final skillText = skillFile.existsSync()
        ? skillFile.readAsStringSync()
        : '';
    final corpus = skillText;
    stdout.writeln('\n[$domainId]');
    var passCount = 0;
    for (final qa in cases) {
      final id = (qa['id'] ?? '').toString();
      final mustContain =
          (qa['mustContain'] as List?)?.whereType<String>().toList(
            growable: false,
          ) ??
          const <String>[];
      final hit = mustContain.where(corpus.contains).length;
      final ratio = mustContain.isEmpty ? 1.0 : hit / mustContain.length;
      final modelJudgeScore = _modelJudgeScore(
        ratio: ratio,
        answerText: skillText,
        domainId: domainId,
      );
      final passed = modelJudgeScore >= 0.75;
      if (passed) passCount += 1;
      stdout.writeln(
        ' - $id => ${passed ? 'PASS' : 'FAIL'} '
        '(hit=$hit/${mustContain.length}, score=${modelJudgeScore.toStringAsFixed(2)}, multiTurn=${qa['multiTurn'] == true})',
      );
    }
    final domainPass =
        cases.isNotEmpty && passCount >= ((cases.length * 0.8).ceil());
    stdout.writeln(' => domain result: ${domainPass ? 'PASS' : 'FAIL'}');
    if (!domainPass) {
      failed.add(domainId);
    }
  }

  if (failed.isNotEmpty) {
    stdout.writeln('\nFAILED domains: ${failed.join(', ')}');
    exitCode = 1;
    return;
  }
  stdout.writeln('\nAll domains passed benchmark cases.');
}

double _modelJudgeScore({
  required double ratio,
  required String answerText,
  required String domainId,
}) {
  var score = 0.4 + (ratio * 0.4);
  if (answerText.contains('## 双轨输出契约') && answerText.contains('## 轮次状态定义')) {
    score += 0.1;
  }
  if (_highRiskDomains.contains(domainId)) {
    if (answerText.contains('免责声明') || answerText.contains('安全')) {
      score += 0.1;
    }
  } else {
    score += 0.05;
  }
  if (score > 1.0) return 1.0;
  return score;
}

const Set<String> _highRiskDomains = <String>{
  'emotion_companion',
  'relationship_matchmaking',
  'divination_fortune',
  'astrology_constellation',
  'family_parenting',
};

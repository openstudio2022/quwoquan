import 'dart:convert';
import 'dart:io';

import 'package:quwoquan_app/assistant/application/assistant_gateway.dart';
import 'package:quwoquan_app/assistant/domain/channel/channel.dart';
import 'package:quwoquan_app/assistant/runtime/assistant_runtime.dart';

Future<void> main() async {
  final benchmarkFile = File(
    'test/assistant/domain_quality_benchmark_cases.json',
  );
  if (!benchmarkFile.existsSync()) {
    stderr.writeln('benchmark file not found');
    exitCode = 1;
    return;
  }
  final decoded = jsonDecode(benchmarkFile.readAsStringSync()) as Map;
  final domains =
      (decoded['domains'] as List?)?.whereType<Map>().toList(growable: false) ??
      const <Map>[];
  if (domains.isEmpty) {
    stderr.writeln('no benchmark cases found');
    exitCode = 1;
    return;
  }

  final storagePath =
      '${Directory.systemTemp.path}/pa_e2e_${DateTime.now().millisecondsSinceEpoch}.json';
  final runtime = AssistantRuntime.createForTest(storagePath: storagePath);
  final gateway = AssistantGateway(runtime);
  await runtime.ensureRemoteConfigLoaded();
  final models = runtime.listAvailableModels();
  if (models.isEmpty) {
    stderr.writeln('no remote model available');
    exitCode = 2;
    return;
  }
  final mimo = models.firstWhere(
    (item) => item.toLowerCase().contains('mimo'),
    orElse: () => '',
  );
  if (mimo.isEmpty) {
    stderr.writeln('mimo model not found in configured models: $models');
    exitCode = 3;
    return;
  }
  runtime.switchModel(mimo);
  stdout.writeln('Using model: $mimo');

  final failures = <String>[];
  var totalCases = 0;
  var passedCases = 0;

  for (final domain in domains) {
    final domainId = (domain['domainId'] ?? '').toString();
    final cases =
        (domain['cases'] as List?)?.whereType<Map>().toList(growable: false) ??
        const <Map>[];
    stdout.writeln('\n[$domainId]');
    for (final qa in cases) {
      totalCases += 1;
      final id = (qa['id'] ?? '').toString();
      final turns =
          (qa['conversation'] as List?)?.whereType<String>().toList(growable: false) ??
          const <String>[];
      final mustContain =
          (qa['mustContain'] as List?)?.whereType<String>().toList(growable: false) ??
          const <String>[];
      final sessionId = 'e2e-$domainId-$id';
      AssistantRunResponse? lastResponse;
      for (final turn in turns) {
        lastResponse = await gateway.run(
          AssistantRunRequest(
            sessionId: sessionId,
            messages: <AssistantRunMessage>[
              AssistantRunMessage(role: 'user', content: turn),
            ],
            capabilityCatalog: const <String>[
              'context.current_page',
              'context.chat_recent',
              'context.chat_longterm',
              'context.web_search',
            ],
            gpsLocation: const <String, dynamic>{'city': '深圳'},
            maxIterations: 4,
          ),
        );
      }
      final response = lastResponse;
      if (response == null) {
        failures.add('$domainId/$id: empty response');
        stdout.writeln(' - $id => FAIL score=0 (empty)');
        continue;
      }
      final score = _scoreResponse(
        response: response,
        mustContain: mustContain,
      );
      final passed = score >= 80;
      if (passed) {
        passedCases += 1;
      } else {
        failures.add('$domainId/$id: score=$score');
      }
      final hasSearch = response.traces.any((trace) {
        final msg = trace.message.toLowerCase();
        if (msg.contains('calling web_search')) {
          return true;
        }
        final data = trace.data ?? const <String, dynamic>{};
        final toolName = (data['toolName'] ?? '').toString().toLowerCase();
        return toolName == 'web_search';
      });
      stdout.writeln(
        ' - $id => ${passed ? 'PASS' : 'FAIL'} score=$score '
        '(search=${hasSearch ? 'yes' : 'no'}, degraded=${response.degraded})',
      );
    }
  }

  stdout.writeln(
    '\nE2E summary: $passedCases/$totalCases passed (threshold >=80)',
  );
  if (failures.isNotEmpty) {
    stdout.writeln('Failed cases:');
    for (final item in failures) {
      stdout.writeln(' - $item');
    }
    exitCode = 10;
    return;
  }
  stdout.writeln('All E2E cases passed.');
}

int _scoreResponse({
  required AssistantRunResponse response,
  required List<String> mustContain,
}) {
  var score = 0;
  final text = response.finalText.trim();
  if (text.isNotEmpty) score += 30;
  final hasSearch = response.traces.any((trace) {
    final msg = trace.message.toLowerCase();
    return msg.contains('calling web_search') ||
        msg.contains('检索结果');
  });
  if (hasSearch) score += 20;
  final hasStructured = response.structuredResponse.isNotEmpty;
  if (hasStructured) score += 10;
  if (!response.degraded) score += 10;
  if (mustContain.isNotEmpty) {
    final hits = mustContain.where(text.contains).length;
    score += ((hits / mustContain.length) * 30).round();
  }
  if (score > 100) return 100;
  return score;
}


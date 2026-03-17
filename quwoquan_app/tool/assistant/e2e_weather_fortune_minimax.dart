import 'dart:convert';
import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/assistant/application/assistant_gateway.dart';
import 'package:quwoquan_app/assistant/domain/channel/channel.dart';
import 'package:quwoquan_app/assistant/runtime/assistant_runtime.dart';

class _ScenarioResult {
  const _ScenarioResult({
    required this.name,
    required this.passed,
    required this.reason,
    required this.domain,
    required this.degraded,
    required this.errorCode,
    required this.finalText,
    required this.traceCount,
  });

  final String name;
  final bool passed;
  final String reason;
  final String domain;
  final bool degraded;
  final String errorCode;
  final String finalText;
  final int traceCount;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'name': name,
      'passed': passed,
      'reason': reason,
      'domain': domain,
      'degraded': degraded,
      'errorCode': errorCode,
      'traceCount': traceCount,
      'finalText': finalText,
    };
  }
}

Future<_ScenarioResult> _runScenario({
  required AssistantGateway gateway,
  required String name,
  required String expectedDomain,
  required String query,
}) async {
  final response = await gateway.run(
    AssistantRunRequest(
      sessionId: 'e2e_minimax_${DateTime.now().millisecondsSinceEpoch}',
      userId: 'e2e_user',
      channel: 'app',
      deviceProfile: 'mobile',
      messages: <AssistantRunMessage>[
        AssistantRunMessage(role: 'user', content: query),
      ],
    ),
  );
  final selectedDomains =
      ((response.structuredResponse['domainRouting'] as Map?)
                  ?.cast<String, dynamic>()['selectedDomains']
              as List?)
          ?.whereType<String>()
          .toList(growable: false) ??
      const <String>[];
  final selectedDomain = selectedDomains.isEmpty ? '' : selectedDomains.first;
  final finalText = response.finalText.trim();
  final errorCode = (response.errorCode ?? '').trim();
  final ok =
      selectedDomain == expectedDomain &&
      !response.degraded &&
      errorCode.isEmpty &&
      finalText.isNotEmpty;
  final reason = ok
      ? 'ok'
      : 'domain=$selectedDomain, degraded=${response.degraded}, errorCode=$errorCode, textEmpty=${finalText.isEmpty}';
  return _ScenarioResult(
    name: name,
    passed: ok,
    reason: reason,
    domain: selectedDomain,
    degraded: response.degraded,
    errorCode: errorCode,
    finalText: finalText,
    traceCount: response.traces.length,
  );
}

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final runtime = AssistantRuntime.createForTest();
  await runtime.ensureRemoteConfigLoaded();
  final gateway = AssistantGateway(runtime);

  const minimaxRef = 'modelscope/MiniMax/MiniMax-M2.5';
  final switched = gateway.switchModel(minimaxRef);
  if (!switched) {
    stderr.writeln('E2E FAIL: MiniMax model not available: $minimaxRef');
    stderr.writeln('available: ${gateway.listAvailableModels()}');
    exitCode = 2;
    return;
  }
  gateway.setSelectedModels(const <String>[minimaxRef]);

  final weather = await _runScenario(
    gateway: gateway,
    name: 'weather',
    expectedDomain: 'weather',
    query: '深圳今天天气怎么样？请给我穿衣和出行建议。',
  );
  final fortune = await _runScenario(
    gateway: gateway,
    name: 'divination_fortune',
    expectedDomain: 'divination_fortune',
    query: '我是狮子座，今天整体运势如何？请给我简短建议。',
  );

  final report = <String, dynamic>{
    'generatedAt': DateTime.now().toIso8601String(),
    'model': gateway.currentModel(),
    'selectedModels': gateway.selectedModels(),
    'results': <Map<String, dynamic>>[weather.toJson(), fortune.toJson()],
    'pass': weather.passed && fortune.passed,
  };

  stdout.writeln(const JsonEncoder.withIndent('  ').convert(report));
  if (report['pass'] != true) {
    stderr.writeln('E2E FAIL: weather/fortune did not fully pass');
    exitCode = 1;
  } else {
    stdout.writeln('E2E PASS: MiniMax weather + fortune');
  }
}

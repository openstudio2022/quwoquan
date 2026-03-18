import 'dart:convert';
import 'dart:io';

import 'package:quwoquan_app/assistant/application/assistant_gateway.dart';
import 'package:quwoquan_app/assistant/application/assistant_request_policy.dart';
import 'package:quwoquan_app/assistant/application/local_assistant_entry.dart';
import 'package:quwoquan_app/assistant/domain/channel/channel.dart';
import 'package:quwoquan_app/assistant/runtime/assistant_runtime.dart';

Future<void> main() async {
  final reportDir = Directory(
    '/Users/zhaoyuxi/Projects/quwoquan/app_log/personal_assistant_eval/runtime_entry',
  );
  await reportDir.create(recursive: true);
  final now = DateTime.now().toUtc().toIso8601String();

  final tempDir = await Directory.systemTemp.createTemp('pa_runtime_entry_e2e_');
  final runtime = AssistantRuntime.createForTest(
    storagePath: '${tempDir.path}/vector_store.json',
  );
  final assistantGateway = AssistantGateway(runtime);
  final localEntry = LocalAssistantEntry(
    assistantGateway: assistantGateway,
    requestPolicy: const AssistantRequestPolicy(),
  );

  final request = AssistantRunRequest(
    sessionId: 'runtime_entry_e2e',
    userId: 'current_user',
    channel: 'app',
    deviceProfile: 'mobile',
    messages: const <AssistantRunMessage>[
      AssistantRunMessage(
        role: 'user',
        content: '我想看最近事业运，下个月跳槽机会怎样？',
      ),
    ],
  );

  final response = await localEntry.run(request: request);

  final report = <String, dynamic>{
    'generatedAt': now,
    'entry': 'local_assistant_entry.run',
    'request': request.toJson(),
    'result': <String, dynamic>{
      'degraded': response.degraded,
      'errorCode': response.errorCode,
      'finalText': response.finalText,
      'traceCount': response.traces.length,
      'traceTypes': response.traces.map((e) => e.type.name).toList(growable: false),
    },
    'pass': response.finalText.trim().isNotEmpty,
  };

  final reportFile = File('${reportDir.path}/runtime_entry_e2e_report.json');
  await reportFile.writeAsString(
    const JsonEncoder.withIndent('  ').convert(report),
    flush: true,
  );

  stdout.writeln('runtime_entry_e2e: ${report['pass'] == true ? 'PASS' : 'FAIL'}');
  stdout.writeln('report: ${reportFile.path}');
  stdout.writeln('degraded: ${response.degraded}, errorCode: ${response.errorCode ?? ''}');
  stdout.writeln('finalText: ${response.finalText}');
}

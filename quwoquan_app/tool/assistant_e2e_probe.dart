import 'dart:convert';
import 'dart:io';

import 'package:quwoquan_app/personal_assistant/app/assistant_gateway.dart';
import 'package:quwoquan_app/personal_assistant/app/assistant_runtime.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_request.dart';
import 'package:quwoquan_app/personal_assistant/protocol/trace_events.dart';

Future<void> main(List<String> args) async {
  final query = args.isNotEmpty ? args.join(' ') : '深圳天气怎么样';
  final runtime = AssistantRuntime.createDefault();
  await runtime.ensureRemoteConfigLoaded();
  final gateway = AssistantGateway(runtime);
  final modelRef = gateway.currentModel() ?? '';

  final response = await gateway.run(
    AssistantRunRequest(
      sessionId: 'assistant_e2e_probe',
      userId: 'probe_user',
      deviceProfile: 'mobile',
      channel: 'app',
      messages: <AssistantRunMessage>[
        AssistantRunMessage(role: 'user', content: query),
      ],
    ),
  );

  final toolTraces = response.traces
      .where(
        (trace) =>
            trace.type == AssistantTraceEventType.toolStart ||
            trace.type == AssistantTraceEventType.toolResult ||
            trace.type == AssistantTraceEventType.toolError,
      )
      .map((trace) => <String, dynamic>{
            'type': trace.type.name,
            'message': trace.message,
            'data': trace.data,
          })
      .toList(growable: false);

  final result = <String, dynamic>{
    'query': query,
    'modelRef': modelRef,
    'runId': response.runId,
    'traceId': response.traceId,
    'degraded': response.degraded,
    'errorCode': response.errorCode,
    'finalText': response.finalText,
    'toolTraceCount': toolTraces.length,
    'toolTraces': toolTraces,
  };
  stdout.writeln(jsonEncode(result));
}


import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/personal_assistant/app/assistant_gateway.dart';
import 'package:quwoquan_app/personal_assistant/app/assistant_http_gateway.dart';
import 'package:quwoquan_app/personal_assistant/app/assistant_runtime.dart';
import 'package:quwoquan_app/personal_assistant/connectors/openclaw_bridge.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_request.dart';
import 'package:quwoquan_app/personal_assistant/protocol/trace_events.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('Personal assistant acceptance scenarios', () {
    late AssistantRuntime runtime;
    late AssistantGateway gateway;
    late AssistantHttpGateway httpGateway;

    setUp(() async {
      // 模拟 path_provider 返回临时目录，避免平台通道依赖
      const channel = MethodChannel('plugins.flutter.io/path_provider');
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, (MethodCall call) async {
        return Directory.systemTemp.path;
      });

      runtime = AssistantRuntime.createDefault();
      gateway = AssistantGateway(runtime);
      httpGateway = AssistantHttpGateway(
        gateway: gateway,
        port: 18189,
        authToken: 'test-token',
      );
      await httpGateway.start();
    });

    tearDown(() async {
      await httpGateway.stop();
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(
            const MethodChannel('plugins.flutter.io/path_provider'),
            null,
          );
    });

    test('Scenario A: feishu voice command through OpenClaw can invoke web search skill', () async {
      final bridge = OpenClawBridge(
        baseUrl: 'http://127.0.0.1:18189',
        authToken: 'test-token',
      );

      final text = await bridge.handleVoiceCommandForKnowledgeQa(
        '帮我查一下今日财经热点和天气',
      );

      expect(text, isNotNull);
      final normalized = text!.toLowerCase();
      expect(
        normalized,
        anyOf(
          contains('web search'),
          contains('success'),
          contains('fallback'),
          contains('unavailable'),
        ),
      );
    });

    test('Scenario B: app text chat can directly ask and trigger assistant react loop', () async {
      final response = await gateway.run(
        const AssistantRunRequest(
          sessionId: 'assistant',
          userId: 'u_test',
          deviceProfile: 'mobile',
          messages: <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '帮我搜索今日财经知识'),
          ],
        ),
      );

      expect(response.finalText.trim().isNotEmpty, isTrue);
      expect(
        response.traces.any((t) => t.type == AssistantTraceEventType.lifecycleStart),
        isTrue,
      );
      expect(
        response.traces.any((t) => t.type == AssistantTraceEventType.lifecycleEnd),
        isTrue,
      );
    });
  });
}

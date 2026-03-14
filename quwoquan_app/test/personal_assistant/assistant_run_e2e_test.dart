import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/personal_assistant/app/assistant_gateway.dart';
import 'package:quwoquan_app/personal_assistant/app/assistant_runtime.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_request.dart';

void main() {
  group('Assistant run E2E', () {
    test('问「深圳天气怎么样」能拿到回复且不出现「未配置可用模型」', () async {
      final binding = TestWidgetsFlutterBinding.ensureInitialized();
      const channel = MethodChannel('plugins.flutter.io/path_provider');
      binding.defaultBinaryMessenger.setMockMethodCallHandler(channel, (
        MethodCall call,
      ) async {
        if (call.method == 'getApplicationDocumentsDirectory') {
          return Directory.systemTemp.path;
        }
        return null;
      });

      final runtime = AssistantRuntime.createForTest();
      await runtime.ensureRemoteConfigLoaded();
      final gateway = AssistantGateway(runtime);

      final response = await gateway.run(
        AssistantRunRequest(
          sessionId: 'assistant_e2e_test',
          userId: 'test_user',
          deviceProfile: 'mobile',
          channel: 'app',
          messages: const <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '深圳天气怎么样'),
          ],
        ),
      );

      expect(response.finalText, isNotEmpty);
      expect(
        response.finalText.contains('未配置可用模型'),
        isFalse,
        reason: '小艺私人助手对话中不应展示「未配置可用模型」，应走本地启发式或远程模型',
      );
      expect(response.machineEnvelope, equals(response.finalText));
      expect(response.displayMarkdown.trim(), isNotEmpty);
      expect(response.displayPlainText.trim(), isNotEmpty);
      expect(response.displayMarkdown.contains('contractVersion'), isFalse);
      final processJournal = ((((response.structuredResponse['runArtifacts']
                      as Map?)?['processJournal'] as List?) ??
                  const <dynamic>[]))
          .whereType<Map>()
          .map((item) => item.cast<String, dynamic>())
          .toList(growable: false);
      expect(processJournal, isNotEmpty, reason: '简单事实问题也应生成统一主过程日志');
    });

    test('问「深圳住宿和行程规划」时主过程不串入内部摘要任务', () async {
      final binding = TestWidgetsFlutterBinding.ensureInitialized();
      const channel = MethodChannel('plugins.flutter.io/path_provider');
      binding.defaultBinaryMessenger.setMockMethodCallHandler(channel, (
        MethodCall call,
      ) async {
        if (call.method == 'getApplicationDocumentsDirectory') {
          return Directory.systemTemp.path;
        }
        return null;
      });

      final runtime = AssistantRuntime.createForTest();
      await runtime.ensureRemoteConfigLoaded();
      final gateway = AssistantGateway(runtime);

      final response = await gateway.run(
        AssistantRunRequest(
          sessionId: 'assistant_trip_e2e_test',
          userId: 'test_user',
          deviceProfile: 'mobile',
          channel: 'app',
          messages: const <AssistantRunMessage>[
            AssistantRunMessage(
              role: 'user',
              content: '帮我规划深圳三天两晚住宿和行程，预算4000元',
            ),
          ],
        ),
      );

      expect(response.finalText.trim(), isNotEmpty);
      expect(
        response.finalText.contains('未配置可用模型'),
        isFalse,
        reason: '复杂规划问题也不应回退到未配置模型文案',
      );
      expect(response.machineEnvelope, equals(response.finalText));
      expect(response.displayMarkdown.trim(), isNotEmpty);
      expect(response.displayPlainText.trim(), isNotEmpty);
      expect(response.displayMarkdown.contains('contractVersion'), isFalse);

      final structured = response.structuredResponse;
      final processJournal =
          ((((structured['runArtifacts'] as Map?)?['processJournal'] as List?) ??
                  const <dynamic>[]))
          .whereType<Map>()
          .map((item) => item.cast<String, dynamic>())
          .toList(growable: false);

      expect(processJournal, isNotEmpty, reason: '复杂规划问题应输出统一主过程日志');

      final combinedNarrative = processJournal
          .map((item) => (item['message'] as String?) ?? '')
          .join(' ');
      expect(combinedNarrative.contains('压缩以上对话历史为简洁摘要'), isFalse);
      expect(combinedNarrative.contains('summarize_session'), isFalse);
    });
  });
}

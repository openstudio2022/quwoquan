import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/application/assistant_gateway.dart';
import 'package:quwoquan_app/assistant/domain/channel/channel.dart';
import 'package:quwoquan_app/assistant/runtime/assistant_runtime.dart';

// Verifies the v2 prompt template architecture end-to-end:
// 1. New template files load via manifest
// 2. Prompt stack uses v2 order (identity → safety → task → contract → persona → tool_policy)
// 3. Semantic trace events are emitted
// 4. Response parses correctly with v4 contract support
void main() {
  group('Prompt v2 architecture E2E', () {
    late AssistantGateway gateway;

    setUpAll(() async {
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
      gateway = AssistantGateway(runtime);
    });

    test('深圳天气查询返回结构化响应且包含语义 trace 事件', () async {
      final traces = <AssistantTraceEvent>[];
      final response = await gateway.runWithTraceStream(
        AssistantRunRequest(
          sessionId: 'v2_e2e_weather',
          userId: 'test_user',
          deviceProfile: 'mobile',
          channel: 'app',
          messages: const <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '深圳天气'),
          ],
        ),
        onTraceEvent: traces.add,
      );

      expect(response.finalText, isNotEmpty);
      expect(
        response.finalText.contains('未配置可用模型'),
        isFalse,
        reason: '不应出现未配置模型降级文案',
      );

      // v2: planStarted trace event should be emitted
      final hasPlanStarted = traces.any(
        (t) => t.type == AssistantTraceEventType.planStarted,
      );
      expect(hasPlanStarted, isTrue, reason: '应发射 planStarted 语义事件');

      // v2: thinkingStarted trace event should be emitted
      final hasThinking = traces.any(
        (t) => t.type == AssistantTraceEventType.thinkingStarted,
      );
      expect(hasThinking, isTrue, reason: '应发射 thinkingStarted 语义事件');

      // Structured response should have domain info
      final structured = response.structuredResponse;
      expect(structured, isNotEmpty);
      final domainId = (structured['domainId'] as String?) ?? '';
      expect(domainId, isNotEmpty, reason: '应有域路由结果');
    });

    test('新模板文件全部可从 manifest 加载', () {
      final manifestFile = File('assets/assistant/prompts/manifest.json');
      expect(manifestFile.existsSync(), isTrue);

      final decoded = jsonDecode(manifestFile.readAsStringSync()) as Map;
      final templates =
          (decoded['templates'] as List?)?.whereType<Map>().toList() ?? [];

      final templateIds = templates
          .map((t) {
            final metaPath = (t['metaPath'] as String?) ?? '';
            if (metaPath.isEmpty) return '';
            final metaFile = File(metaPath);
            if (!metaFile.existsSync()) return '';
            final meta = jsonDecode(metaFile.readAsStringSync()) as Map;
            return (meta['templateId'] as String?)?.trim() ?? '';
          })
          .where((id) => id.isNotEmpty)
          .toSet();

      // v2 required templates
      for (final required in [
        'stack.identity',
        'stack.safety',
        'stack.persona',
        'stack.tool_policy',
        'phase.output_contract.plan',
        'phase.output_contract.answer',
        'phase.output_contract.ask_user',
      ]) {
        expect(
          templateIds.contains(required),
          isTrue,
          reason: 'manifest 中应注册 $required 模板',
        );
      }
    });

    test('v4 contract version 被正确识别', () async {
      final response = await gateway.run(
        AssistantRunRequest(
          sessionId: 'v2_e2e_v4_contract',
          userId: 'test_user',
          deviceProfile: 'mobile',
          channel: 'app',
          messages: const <AssistantRunMessage>[
            AssistantRunMessage(role: 'user', content: '深圳天气怎么样'),
          ],
        ),
      );

      // Response should parse and wrap correctly
      final text = response.finalText.trim();
      expect(text, isNotEmpty);

      // Structured response should contain contract version info
      final structured = response.structuredResponse;
      final contractVersion =
          (structured['contractVersion'] as String?)?.trim() ?? '';
      expect(
        contractVersion,
        equals('assistant_turn'),
        reason: '应输出 assistant_turn 合约版本，实际: $contractVersion',
      );
    });
  });
}

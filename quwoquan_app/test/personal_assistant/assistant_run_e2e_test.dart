import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/personal_assistant/app/assistant_gateway.dart';
import 'package:quwoquan_app/personal_assistant/app/assistant_runtime.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_request.dart';

void main() {
  group('Assistant run E2E', () {
    test('问「深圳天气怎么样」能拿到回复且不出现「未配置可用模型」', () async {
      TestWidgetsFlutterBinding.ensureInitialized();
      const MethodChannel(
        'plugins.flutter.io/path_provider',
      ).setMockMethodCallHandler((MethodCall call) async {
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
    });
  });
}

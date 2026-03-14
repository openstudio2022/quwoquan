import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/application/assistant_gateway.dart';
import 'package:quwoquan_app/assistant/domain/channel/channel.dart';
import 'package:quwoquan_app/assistant/runtime/assistant_runtime.dart';

class _DirectHttpOverrides extends HttpOverrides {
  @override
  HttpClient createHttpClient(SecurityContext? context) {
    return HttpClient(context: context);
  }
}

void main() {
  group('MiniMax live e2e weather + fortune', () {
    late HttpOverrides? previousOverrides;

    setUpAll(() {
      previousOverrides = HttpOverrides.current;
      HttpOverrides.global = _DirectHttpOverrides();
    });

    tearDownAll(() {
      HttpOverrides.global = previousOverrides;
    });

    test(
      'switch to MiniMax and run weather + divination_fortune',
      skip: const bool.fromEnvironment('LIVE_TEST', defaultValue: false)
          ? null
          : 'live test：需要真实 MiniMax API key 和网络，设置 LIVE_TEST=true 启用',
      () async {
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

        const minimaxRef = 'modelscope/MiniMax/MiniMax-M2.5';
        expect(
          gateway.switchModel(minimaxRef),
          isTrue,
          reason: 'MiniMax model should be available in runtime config',
        );
        gateway.setSelectedModels(const <String>[minimaxRef]);

        final weather = await gateway.run(
          AssistantRunRequest(
            sessionId: 'minimax_live_weather',
            userId: 'test_user',
            channel: 'app',
            deviceProfile: 'mobile',
            messages: const <AssistantRunMessage>[
              AssistantRunMessage(
                role: 'user',
                content: '深圳今天天气怎么样？请给我穿衣和出行建议。',
              ),
            ],
          ),
        );
        final weatherDomains =
            (((weather.structuredResponse['domainRouting'] as Map?)
                        ?.cast<String, dynamic>()['selectedDomains']
                    as List?)
                ?.whereType<String>()
                .toList(growable: false)) ??
            const <String>[];
        final weatherDomain = weatherDomains.isEmpty
            ? ''
            : weatherDomains.first;
        expect(weather.finalText.trim().isNotEmpty, isTrue);
        expect(weather.degraded, isFalse);
        expect((weather.errorCode ?? '').trim(), isEmpty);
        expect(weatherDomain, equals('weather'));

        final fortune = await gateway.run(
          AssistantRunRequest(
            sessionId: 'minimax_live_fortune',
            userId: 'test_user',
            channel: 'app',
            deviceProfile: 'mobile',
            messages: const <AssistantRunMessage>[
              AssistantRunMessage(
                role: 'user',
                content: '我是狮子座，今天整体运势如何？请给我简短建议。',
              ),
            ],
          ),
        );
        final fortuneDomains =
            (((fortune.structuredResponse['domainRouting'] as Map?)
                        ?.cast<String, dynamic>()['selectedDomains']
                    as List?)
                ?.whereType<String>()
                .toList(growable: false)) ??
            const <String>[];
        final fortuneDomain = fortuneDomains.isEmpty
            ? ''
            : fortuneDomains.first;
        expect(fortune.finalText.trim().isNotEmpty, isTrue);
        expect(fortune.degraded, isFalse);
        expect((fortune.errorCode ?? '').trim(), isEmpty);
        expect(fortuneDomain, equals('divination_fortune'));
      },
      timeout: const Timeout(Duration(minutes: 2)),
    );
  });
}

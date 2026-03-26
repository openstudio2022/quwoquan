import 'dart:convert';
import 'dart:io';

import 'package:quwoquan_app/assistant/infrastructure/assistant_model_runtime.dart';
import 'package:quwoquan_app/assistant/template_runtime/assistant_template_runtime.dart';
import 'package:test/test.dart';

void main() {
  PromptTemplateRuntime buildTemplateRuntime() {
    return PromptTemplateRuntime(
      registry: TemplateRegistry.withSeeded(
        seededTemplates: <String, PromptTemplate>{
          'planner.global_plan@v1': const PromptTemplate(
            templateId: 'planner.global_plan',
            templateVersion: 'v1',
            content: '你是测试助手。请直接回答用户问题。',
          ),
        },
      ),
    );
  }

  group('Model routing', () {
    test('can list/switch/current model', () async {
      final provider = SwitchableAssistantLlmProvider(
        fallbackProvider: const HeuristicLocalLlmProvider(),
      );
      const configs = <AssistantModelRuntimeConfig>[
        AssistantModelRuntimeConfig(
          modelRef: 'p/m1',
          providerId: 'p',
          modelId: 'm1',
          baseUrl: 'https://example.com/v1',
          apiKey: 'k1',
        ),
        AssistantModelRuntimeConfig(
          modelRef: 'p/m2',
          providerId: 'p',
          modelId: 'm2',
          baseUrl: 'https://example.com/v1',
          apiKey: 'k2',
        ),
      ];
      provider.registerRemoteModels(configs);

      expect(provider.availableModelRefs.length, equals(2));
      expect(provider.activeModelRef, equals('p/m1'));
      expect(provider.switchModel('p/m2'), isTrue);
      expect(provider.activeModelRef, equals('p/m2'));
      expect(provider.switchModel('not-exist'), isFalse);
      expect(
        provider.setSelectedModels(const <String>['p/m1', 'p/m2']),
        isTrue,
      );
      expect(
        provider.selectedModelRefs,
        equals(const <String>['p/m1', 'p/m2']),
      );
      expect(provider.setSelectedModels(const <String>['not-exist']), isFalse);
    });

    test('falls back to local strategy when no config exists', () async {
      final provider = SwitchableAssistantLlmProvider(
        fallbackProvider: const HeuristicLocalLlmProvider(),
      );
      final output = await provider.reason(
        messages: const <Map<String, String>>[
          <String, String>{'role': 'user', 'content': '请帮我搜索天气'},
        ],
        availableTools: const <String>['web_search'],
      );
      expect(output.text.trim().isNotEmpty, isTrue);
    });

    test(
      'falls through to next remote model when primary model is unreachable',
      () async {
        final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
        addTearDown(() async {
          await server.close(force: true);
        });
        server.listen((request) async {
          expect(request.uri.path, equals('/v1/chat/completions'));
          final body = await utf8.decoder.bind(request).join();
          final decoded = jsonDecode(body) as Map<String, dynamic>;
          expect(decoded['model'], equals('healthy-model'));
          request.response
            ..statusCode = HttpStatus.ok
            ..headers.contentType = ContentType.json
            ..write(
              jsonEncode(<String, dynamic>{
                'choices': <Map<String, dynamic>>[
                  <String, dynamic>{
                    'message': <String, dynamic>{'content': '备选模型响应成功'},
                  },
                ],
              }),
            );
          await request.response.close();
        });

        final provider = SwitchableAssistantLlmProvider(
          fallbackProvider: const HeuristicLocalLlmProvider(),
          templateRuntime: buildTemplateRuntime(),
        );
        provider.registerRemoteModels(<AssistantModelRuntimeConfig>[
          const AssistantModelRuntimeConfig(
            modelRef: 'broken/primary-model',
            providerId: 'broken',
            modelId: 'primary-model',
            baseUrl: 'http://127.0.0.1:9/v1',
            apiKey: 'broken-key',
          ),
          AssistantModelRuntimeConfig(
            modelRef: 'healthy/healthy-model',
            providerId: 'healthy',
            modelId: 'healthy-model',
            baseUrl: 'http://127.0.0.1:${server.port}/v1',
            apiKey: 'healthy-key',
          ),
        ]);

        final output = await provider.reason(
          messages: const <Map<String, String>>[
            <String, String>{'role': 'user', 'content': '你好'},
          ],
          availableTools: const <String>[],
        );

        expect(output.degraded, isFalse);
        expect(output.text, equals('备选模型响应成功'));
        expect(provider.activeModelRef, equals('healthy/healthy-model'));
      },
    );

    test('independent config loader does not require moltbot', () {
      final loader = const AssistantModelConfigLoader();
      final defaults = loader.loadDefaultSync();
      expect(defaults, isA<List<AssistantModelRuntimeConfig>>());
    });

    test(
      'retries without json mode when provider rejects response_format',
      () async {
        final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
        addTearDown(() async {
          await server.close(force: true);
        });
        var requestCount = 0;
        server.listen((request) async {
          requestCount += 1;
          final body = await utf8.decoder.bind(request).join();
          final decoded = jsonDecode(body) as Map<String, dynamic>;
          if (decoded.containsKey('response_format')) {
            request.response
              ..statusCode = HttpStatus.badRequest
              ..headers.contentType = ContentType.json
              ..write(
                jsonEncode(<String, dynamic>{
                  'error': <String, dynamic>{
                    'message': 'response_format is not supported',
                  },
                }),
              );
            await request.response.close();
            return;
          }
          request.response
            ..statusCode = HttpStatus.ok
            ..headers.contentType = ContentType.json
            ..write(
              jsonEncode(<String, dynamic>{
                'choices': <Map<String, dynamic>>[
                  <String, dynamic>{
                    'message': <String, dynamic>{'content': '兼容模式成功'},
                  },
                ],
              }),
            );
          await request.response.close();
        });

        final provider = OpenAiCompatibleLlmProvider(
          modelId: 'MiniMax/MiniMax-M2.5',
          baseUrl: 'http://127.0.0.1:${server.port}/v1',
          apiKey: 'test-key',
          templateRuntime: buildTemplateRuntime(),
          modelRef: 'modelscope/MiniMax/MiniMax-M2.5',
        );

        final output = await provider.reason(
          messages: const <Map<String, String>>[
            <String, String>{'role': 'user', 'content': '你好'},
          ],
          availableTools: const <String>[],
          callOptions: const LlmCallOptions.synthesis(),
        );

        expect(output.degraded, isFalse);
        expect(output.text, equals('兼容模式成功'));
        expect(requestCount, equals(2));
      },
    );

    test(
      'streaming path retries without json mode when provider rejects response_format',
      () async {
        final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
        addTearDown(() async {
          await server.close(force: true);
        });
        var requestCount = 0;
        server.listen((request) async {
          requestCount += 1;
          final body = await utf8.decoder.bind(request).join();
          final decoded = jsonDecode(body) as Map<String, dynamic>;
          if (decoded.containsKey('response_format')) {
            request.response
              ..statusCode = HttpStatus.badRequest
              ..headers.contentType = ContentType.json
              ..write(
                jsonEncode(<String, dynamic>{
                  'error': <String, dynamic>{
                    'message': 'response_format is not supported',
                  },
                }),
              );
            await request.response.close();
            return;
          }
          request.response
            ..statusCode = HttpStatus.ok
            ..headers.set('content-type', 'text/event-stream; charset=utf-8');
          request.response.add(
            utf8.encode(
              'data: ${jsonEncode(<String, dynamic>{
                'choices': <Map<String, dynamic>>[
                  <String, dynamic>{
                    'delta': <String, dynamic>{'content': '流式'},
                  },
                ],
              })}\n\n',
            ),
          );
          request.response.add(
            utf8.encode(
              'data: ${jsonEncode(<String, dynamic>{
                'choices': <Map<String, dynamic>>[
                  <String, dynamic>{
                    'delta': <String, dynamic>{'content': '兼容成功'},
                  },
                ],
              })}\n\n',
            ),
          );
          request.response.add(utf8.encode('data: [DONE]\n\n'));
          await request.response.close();
        });

        final provider = OpenAiCompatibleLlmProvider(
          modelId: 'MiniMax/MiniMax-M2.5',
          baseUrl: 'http://127.0.0.1:${server.port}/v1',
          apiKey: 'test-key',
          templateRuntime: buildTemplateRuntime(),
          modelRef: 'modelscope/MiniMax/MiniMax-M2.5',
        );
        final deltas = <String>[];

        final output = await provider.reason(
          messages: const <Map<String, String>>[
            <String, String>{'role': 'user', 'content': '你好'},
          ],
          availableTools: const <String>[],
          callOptions: const LlmCallOptions.synthesis(),
          onDelta: deltas.add,
        );

        expect(output.degraded, isFalse);
        expect(output.text, equals('流式兼容成功'));
        expect(deltas.join(), equals('流式兼容成功'));
        expect(requestCount, equals(2));
      },
    );

    test('native reasoning field deltas 会实时透出到 onDelta', () async {
      final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      addTearDown(() async {
        await server.close(force: true);
      });
      server.listen((request) async {
        expect(request.uri.path, equals('/v1/chat/completions'));
        request.response
          ..statusCode = HttpStatus.ok
          ..headers.set('content-type', 'text/event-stream; charset=utf-8');
        request.response.add(
          utf8.encode(
            'data: ${jsonEncode(<String, dynamic>{
              'choices': <Map<String, dynamic>>[
                <String, dynamic>{
                  'delta': <String, dynamic>{
                    'reasoning_content': '先确认问题焦点',
                  },
                },
              ],
            })}\n\n',
          ),
        );
        request.response.add(
          utf8.encode(
            'data: ${jsonEncode(<String, dynamic>{
              'choices': <Map<String, dynamic>>[
                <String, dynamic>{
                  'delta': <String, dynamic>{
                    'reasoning_content': '，再核对最新信息',
                  },
                },
              ],
            })}\n\n',
          ),
        );
        request.response.add(utf8.encode('data: [DONE]\n\n'));
        await request.response.close();
      });

      final provider = OpenAiCompatibleLlmProvider(
        modelId: 'mimo-v2-flash',
        baseUrl: 'http://127.0.0.1:${server.port}/v1',
        apiKey: 'test-key',
        templateRuntime: buildTemplateRuntime(),
        modelRef: 'mimo/mimo-v2-flash',
      );
      final deltas = <String>[];

      final output = await provider.reason(
        messages: const <Map<String, String>>[
          <String, String>{'role': 'user', 'content': '深圳天气怎么样'},
        ],
        availableTools: const <String>[],
        onDelta: deltas.add,
      );

      expect(deltas.join(), equals('先确认问题焦点，再核对最新信息'));
      expect(output.reasoningText, contains('先确认问题焦点，再核对最新信息'));
    });
  });
}

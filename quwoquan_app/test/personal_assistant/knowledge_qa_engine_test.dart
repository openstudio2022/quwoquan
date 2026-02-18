import 'package:quwoquan_app/personal_assistant/knowledge/knowledge_qa_engine.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_registry.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_schema.dart';
import 'package:test/test.dart';

class _MockWebSearchTool implements AssistantTool {
  @override
  String get description => 'mock web search';

  @override
  String get name => 'web_search';

  @override
  Future<AssistantToolResult> execute(Map<String, dynamic> arguments) async {
    final provider = (arguments['provider'] as String?) ?? 'perplexity';
    if (provider == 'perplexity') {
      return const AssistantToolResult(
        success: true,
        message: 'ok',
        data: <String, dynamic>{
          'raw': <String, dynamic>{
            'choices': <Map<String, dynamic>>[
              <String, dynamic>{
                'message': <String, dynamic>{
                  'content': '杭州周末有降雨概率，建议携带雨具并避开晚高峰。',
                },
              },
            ],
          },
        },
      );
    }
    if (provider == 'brave') {
      return const AssistantToolResult(
        success: true,
        message: 'ok',
        data: <String, dynamic>{
          'raw': <String, dynamic>{
            'web': <String, dynamic>{
              'results': <Map<String, dynamic>>[
                <String, dynamic>{
                  'title': '杭州天气预报',
                  'description': '本周末多云转小雨，温度 10~16 度。',
                  'url': 'https://example.com/weather',
                },
              ],
            },
          },
        },
      );
    }
    return const AssistantToolResult(
      success: false,
      message: 'provider unavailable',
      errorCode: AssistantErrorCode.networkUnavailable,
      degraded: true,
    );
  }
}

void main() {
  group('KnowledgeQaEngine', () {
    late AssistantToolRegistry registry;
    late KnowledgeQaEngine engine;

    setUp(() {
      registry = AssistantToolRegistry()..register(_MockWebSearchTool());
      engine = KnowledgeQaEngine(toolRegistry: registry);
    });

    test('builds structured answer with evidences and uncertainty', () async {
      final report = await engine.run(
        query: '请给出杭州周末天气与出行建议',
        primaryProvider: 'perplexity',
        backupProviders: const <String>['brave'],
        maxEvidence: 4,
      );

      expect(report.answer, contains('结论：'));
      expect(report.answer, contains('依据：'));
      expect(report.answer, contains('不确定性：'));
      expect(report.evidences, isNotEmpty);
      expect(report.providersTried, contains('perplexity'));
    });
  });
}


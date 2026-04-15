import 'package:quwoquan_app/assistant/skills/knowledge_qa_engine.dart';
import 'package:quwoquan_app/assistant/tool/runtime/tool_registry.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';
import 'package:test/test.dart';

class _MockWebSearchTool implements AssistantTool {
  @override
  String get description => 'mock web search';

  @override
  String get name => 'web_search';

  @override
  Future<AssistantToolResult> execute(AssistantToolArguments arguments) async {
    final provider = (arguments['provider'] as String?) ?? 'perplexity';
    if (provider == 'perplexity') {
      return AssistantToolResult(
        success: true,
        message: 'ok',
        data: AssistantToolResultData.fromJson(<String, dynamic>{
          'references': <Map<String, dynamic>>[
            <String, dynamic>{
              'title': '综合天气摘要',
              'summary': '杭州周末有降雨概率，建议携带雨具并避开晚高峰。',
              'url': '',
            },
          ],
        }),
      );
    }
    if (provider == 'brave') {
      return AssistantToolResult(
        success: true,
        message: 'ok',
        data: AssistantToolResultData.fromJson(<String, dynamic>{
          'references': <Map<String, dynamic>>[
            <String, dynamic>{
              'title': '杭州天气预报',
              'snippet': '本周末多云转小雨，温度 10~16 度。',
              'url': 'https://example.com/weather',
            },
          ],
        }),
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
        domainId: 'weather',
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

    test('does not classify domain from query text anymore', () async {
      final report = await engine.run(query: '财经和天气都帮我看看', maxEvidence: 2);

      expect(report.providersTried, contains('default'));
      expect(report.conclusion, contains('针对「财经和天气都帮我看看」'));
    });
  });
}

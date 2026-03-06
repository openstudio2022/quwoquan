import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/personal_assistant/tools/metadata/tool_metadata_registry.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_registry.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_schema.dart';

class _FakeTool implements AssistantTool {
  _FakeTool({
    required this.toolName,
    required this.resultFactory,
  });

  final String toolName;
  final AssistantToolResult Function(Map<String, dynamic> args) resultFactory;
  int executeCount = 0;

  @override
  String get name => toolName;

  @override
  String get description => 'fake';

  @override
  Future<AssistantToolResult> execute(Map<String, dynamic> arguments) async {
    executeCount += 1;
    return resultFactory(arguments);
  }
}

void main() {
  group('AssistantToolRegistry contract validation', () {
    test('pre-validates required arguments for web_search', () async {
      final metadata = ToolMetadataRegistry();
      await metadata.ensureLoaded();
      final registry = AssistantToolRegistry(metadataRegistry: metadata);
      final fakeWeb = _FakeTool(
        toolName: 'web_search',
        resultFactory: (_) => const AssistantToolResult(
          success: true,
          message: 'ok',
          data: <String, dynamic>{
            'provider': 'duckduckgo',
            'summary': 'ok',
            'references': <Map<String, dynamic>>[],
          },
        ),
      );
      registry.register(fakeWeb);

      final result = await registry.execute('web_search', <String, dynamic>{});

      expect(result.success, isFalse);
      expect(result.errorCode, AssistantErrorCode.invalidArguments);
      expect(result.message, contains('missing required "query"'));
      expect(fakeWeb.executeCount, equals(0));
    });

    test('post-validates required output paths for local_context', () async {
      final metadata = ToolMetadataRegistry();
      await metadata.ensureLoaded();
      final registry = AssistantToolRegistry(metadataRegistry: metadata);
      final fakeLocal = _FakeTool(
        toolName: 'local_context',
        resultFactory: (_) => const AssistantToolResult(
          success: true,
          message: 'ok',
          data: <String, dynamic>{
            // Missing required "contextVersion"
            'location': <String, dynamic>{'city': '深圳'},
            'permissions': <String, dynamic>{'location': true},
            'media': <String, dynamic>{'included': false},
          },
        ),
      );
      registry.register(fakeLocal);

      final result = await registry.execute(
        'local_context',
        <String, dynamic>{'requestedFields': <String>['location']},
      );

      expect(result.success, isFalse);
      expect(result.errorCode, AssistantErrorCode.executionFailed);
      expect(result.message, contains('missing "contextVersion"'));
      expect(fakeLocal.executeCount, equals(1));
    });

    test('passes when output satisfies contract', () async {
      final metadata = ToolMetadataRegistry();
      await metadata.ensureLoaded();
      final registry = AssistantToolRegistry(metadataRegistry: metadata);
      final fakeLocal = _FakeTool(
        toolName: 'local_context',
        resultFactory: (_) => const AssistantToolResult(
          success: true,
          message: 'ok',
          data: <String, dynamic>{
            'contextVersion': 'local_context_v1',
            'location': <String, dynamic>{'city': '深圳'},
            'permissions': <String, dynamic>{'location': true},
            'media': <String, dynamic>{'included': false},
          },
        ),
      );
      registry.register(fakeLocal);

      final result = await registry.execute(
        'local_context',
        <String, dynamic>{'requestedFields': <String>['location']},
      );

      expect(result.success, isTrue);
      expect(fakeLocal.executeCount, equals(1));
    });
  });
}

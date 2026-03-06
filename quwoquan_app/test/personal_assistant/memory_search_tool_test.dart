import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/personal_assistant/memory/memory_repository.dart';
import 'package:quwoquan_app/personal_assistant/memory/objectbox_store.dart';
import 'package:quwoquan_app/personal_assistant/tools/memory_search_tool.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_schema.dart';

void main() {
  group('MemorySearchTool', () {
    late MemorySearchTool tool;
    late AssistantMemoryRepository memoryRepo;
    late String tempPath;

    setUp(() {
      tempPath =
          '${Directory.systemTemp.path}/memory_test_${DateTime.now().microsecondsSinceEpoch}/vector_store.json';
      final store = ObjectBoxVectorStore(storagePath: tempPath);
      memoryRepo = AssistantMemoryRepository(store);
      tool = MemorySearchTool(memoryRepository: memoryRepo);
    });

    tearDown(() {
      final file = File(tempPath);
      if (file.existsSync()) file.deleteSync();
    });

    test('name and description', () {
      expect(tool.name, 'memory_search');
      expect(tool.description, isNotEmpty);
    });

    test('rejects empty query', () async {
      final result = await tool.execute(<String, dynamic>{});
      expect(result.success, false);
      expect(result.errorCode, AssistantErrorCode.invalidArguments);
    });

    test('returns empty results when no memories exist', () async {
      final result = await tool.execute(<String, dynamic>{
        'query': '用户喜欢什么',
      });
      expect(result.success, true);
      expect(result.data?['resultCount'], 0);
      expect(result.data?['results'], isEmpty);
    });

    test('finds stored memories', () async {
      await memoryRepo.rememberText(
        id: 'pref-1',
        text: '用户喜欢粤菜和海鲜',
        metadata: <String, dynamic>{'type': 'preference'},
      );
      await memoryRepo.rememberText(
        id: 'pref-2',
        text: '用户住在深圳南山区',
        metadata: <String, dynamic>{'type': 'location'},
      );

      final result = await tool.execute(<String, dynamic>{
        'query': '用户的饮食偏好',
        'maxResults': 3,
      });
      expect(result.success, true);
      expect(result.data?['resultCount'], greaterThan(0));
      final results = result.data?['results'] as List;
      expect(results, isNotEmpty);
      expect(results.first['text'], isA<String>());
    });

    test('respects maxResults limit', () async {
      for (var i = 0; i < 10; i++) {
        await memoryRepo.rememberText(
          id: 'mem-$i',
          text: '记忆条目 $i 关于深圳天气',
        );
      }

      final result = await tool.execute(<String, dynamic>{
        'query': '深圳天气',
        'maxResults': 3,
      });
      expect(result.success, true);
      final results = result.data?['results'] as List;
      expect(results.length, lessThanOrEqualTo(3));
    });

    test('output has required fields: query, resultCount', () async {
      final result = await tool.execute(<String, dynamic>{
        'query': '任何查询',
      });
      expect(result.success, true);
      expect(result.data?['query'], '任何查询');
      expect(result.data?.containsKey('resultCount'), true);
    });
  });
}

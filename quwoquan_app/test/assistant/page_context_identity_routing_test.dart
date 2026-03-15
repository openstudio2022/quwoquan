import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';
import 'package:quwoquan_app/assistant/retrieval/providers/page_context_retrieval_provider.dart';
import 'package:quwoquan_app/assistant/retrieval/contracts/retrieval_models.dart';

class _AssistantSignalRepo extends MockAppContentRepository {
  @override
  List<Map<String, dynamic>> get discoveryMomentData => <Map<String, dynamic>>[
    <String, dynamic>{
      'postId': 'moment_1',
      'contentType': 'micro',
      'contentIdentity': 'moment',
      'body': '今天在公园散步，看到一片晚霞。',
      'assistantUsePolicy': 'inherit',
    },
  ];

  @override
  List<Map<String, dynamic>> get discoveryArticleData => <Map<String, dynamic>>[
    <String, dynamic>{
      'postId': 'work_1',
      'contentType': 'article',
      'contentIdentity': 'work',
      'title': '东京三日清单',
      'summary': '把行程拆成可执行的出行清单。',
      'tags': <String>['checklist'],
      'assistantUsePolicy': 'inherit',
    },
    <String, dynamic>{
      'postId': 'work_excluded',
      'contentType': 'article',
      'contentIdentity': 'work',
      'title': '不应进入助手的私有笔记',
      'assistantUsePolicy': 'exclude',
    },
  ];

  @override
  List<Map<String, dynamic>> get discoveryVideoData =>
      const <Map<String, dynamic>>[];
}

void main() {
  group('PageContextRetrievalProvider content identity routing', () {
    test('点滴进入 context memory，作品进入 knowledge index', () async {
      final provider = PageContextRetrievalProvider(_AssistantSignalRepo());
      final result = await provider.retrieve(
        const AssistantRetrievalRequest(
          query: '东京',
          contextScopeHint: <String, dynamic>{'pageType': 'discovery'},
        ),
      );

      expect(result.success, isTrue);

      final moment = result.items.firstWhere(
        (item) => item.sourceId == 'moment_1',
      );
      expect(moment.sourceType, 'page.discovery.moment_context');
      expect(moment.metadata['contentIdentity'], 'moment');
      expect(moment.metadata['assistantRoute'], 'context_memory');

      final work = result.items.firstWhere((item) => item.sourceId == 'work_1');
      expect(work.sourceType, 'page.discovery.work_knowledge');
      expect(work.metadata['contentIdentity'], 'work');
      expect(work.metadata['assistantRoute'], 'knowledge_index');
      expect(work.metadata['contentTier'], 'checklist');
    });

    test('assistantUsePolicy=exclude 的内容不会进入检索结果', () async {
      final provider = PageContextRetrievalProvider(_AssistantSignalRepo());
      final result = await provider.retrieve(
        const AssistantRetrievalRequest(
          query: '私有',
          contextScopeHint: <String, dynamic>{'pageType': 'discovery'},
        ),
      );

      expect(
        result.items.any((item) => item.sourceId == 'work_excluded'),
        isFalse,
      );
    });

    test('未授权 personal_content_access 时直接拒绝页面创作内容检索', () async {
      final provider = PageContextRetrievalProvider(_AssistantSignalRepo());
      final result = await provider.retrieve(
        const AssistantRetrievalRequest(
          query: '东京',
          contextScopeHint: <String, dynamic>{
            'pageType': 'discovery',
            'assistantContentAccess': <String, dynamic>{'granted': false},
          },
        ),
      );

      expect(result.success, isFalse);
      expect(result.errorCode, 'assistant_content_access_denied');
      expect(result.items, isEmpty);
    });

    test('identity index 关闭时回退到 legacy_context', () async {
      final provider = PageContextRetrievalProvider(_AssistantSignalRepo());
      final result = await provider.retrieve(
        const AssistantRetrievalRequest(
          query: '东京',
          contextScopeHint: <String, dynamic>{
            'pageType': 'discovery',
            'assistantContentAccess': <String, dynamic>{'granted': true},
            'assistantContentIndex': <String, dynamic>{'enabled': false},
          },
        ),
      );

      expect(result.success, isTrue);
      final first = result.items.first;
      expect(first.sourceType, 'page.discovery.legacy_context');
      expect(first.metadata['assistantRoute'], 'legacy_context');
      expect(first.metadata['identityIndexEnabled'], isFalse);
      expect(first.metadata.containsKey('contentIdentity'), isFalse);
    });
  });
}

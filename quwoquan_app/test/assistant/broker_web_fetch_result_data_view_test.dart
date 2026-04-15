import 'package:quwoquan_app/assistant/retrieval/domain/retrieval_broker.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';
import 'package:test/test.dart';

void main() {
  group('RetrievalFetchResultPayload', () {
    test('reads references and trimmed string fields', () {
      final payload = RetrievalFetchResultPayload.fromJson(<String, dynamic>{
        'url': ' https://a.test ',
        'title': ' T ',
        'content': ' body ',
        'summary': ' S ',
        'references': <Map<String, dynamic>>[
          <String, dynamic>{'url': 'https://ref', 'snippet': ' snip '},
        ],
      });
      expect(payload.references.length, 1);
      expect(payload.url, 'https://a.test');
      expect(payload.title, 'T');
      expect(payload.content, 'body');
      expect(payload.summary, 'S');
      expect(payload.references.first.url, 'https://ref');
      expect(payload.references.first.snippet, 'snip');
    });

    test('toResultData keeps canonical reference payload', () {
      const payload = RetrievalFetchResultPayload(
        url: 'https://a.test',
        content: 'body',
        references: <RetrievalFetchReference>[
          RetrievalFetchReference(
            url: 'https://ref',
            source: 'example.com',
            snippet: 'snippet',
          ),
        ],
      );
      final data = payload.toResultData();
      expect(data['url'], 'https://a.test');
      expect(data['content'], 'body');
      final refs = (data['references'] as List?)?.whereType<Map>().toList();
      expect(refs, isNotNull);
      expect(refs, isNotEmpty);
      expect(refs!.first['url'], 'https://ref');
    });

    test('result payloadOrNull can recover from tool result data', () {
      final result = RetrievalFetchResult(
        success: true,
        message: 'ok',
        data: payloadData(<String, dynamic>{
          'url': 'https://page.test',
          'content': 'hello',
        }),
      );
      expect(result.payloadOrNull, isNotNull);
      expect(result.payloadOrNull!.url, 'https://page.test');
      expect(result.payloadOrNull!.content, 'hello');
    });
  });
}

AssistantToolResultData payloadData(Map<String, dynamic> json) {
  return AssistantToolResultData.fromJson(json);
}

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// RecentSearchState typed 契约：wire shape 与 metadata
/// search/search/recent_search_state/operations.yaml 的 request_fields 严格一致。
void main() {
  group('UpsertRecentSearchCommand', () {
    test('wire 只含 query/scope/facet，不含 entryId/updatedAt/版本字段', () {
      final payload = encodeUpsertRecentSearchCommand(
        UpsertRecentSearchCommand(
          query: ' 成都旅行 ',
          scope: 'all',
          facet: 'posts',
        ),
      );
      expect(payload.body, <String, Object?>{
        'query': '成都旅行',
        'scope': 'all',
        'facet': 'posts',
      });
      expect(payload.pathParameters, isEmpty);
    });

    test('facet 缺省时不出现在 wire', () {
      final payload = encodeUpsertRecentSearchCommand(
        UpsertRecentSearchCommand(query: 'q', scope: 'all'),
      );
      final body = payload.body as Map<String, Object?>;
      expect(body.containsKey('facet'), isFalse);
    });

    test('空 query 构造期拒绝', () {
      expect(
        () => UpsertRecentSearchCommand(query: '  ', scope: 'all'),
        throwsArgumentError,
      );
    });
  });

  group('Delete/Clear/List 编码', () {
    test('delete 走 entryId path 参数', () {
      final payload = encodeDeleteRecentSearchCommand(
        DeleteRecentSearchCommand(entryId: 'recent_abcdef0123456789'),
      );
      expect(payload.pathParameters, <String, String>{
        'entryId': 'recent_abcdef0123456789',
      });
      expect(payload.body, isNull);
    });

    test('list/clear 的 scope 收窄经 query 参数', () {
      expect(
        encodeListRecentSearchesQuery(
          ListRecentSearchesQuery(scope: 'all'),
        ).queryParameters,
        <String, String>{'scope': 'all'},
      );
      expect(
        encodeClearRecentSearchesCommand(
          ClearRecentSearchesCommand(),
        ).queryParameters,
        isEmpty,
      );
    });
  });

  group('RecentSearchEntry 解码', () {
    test('服务端 wire 逐字段解码；entryId 只读采纳', () {
      final entry = decodeRecentSearchEntry(<String, Object?>{
        'entryId': 'recent_1234567890abcdef',
        'query': '成都旅行',
        'scope': 'all',
        'facet': 'posts',
        'updatedAt': '2026-07-19T08:00:00.000Z',
      });
      expect(entry.entryId, 'recent_1234567890abcdef');
      expect(entry.query, '成都旅行');
      expect(entry.scope, 'all');
      expect(entry.facet, 'posts');
      expect(entry.updatedAt, DateTime.utc(2026, 7, 19, 8));
    });

    test('缺 NOT_NULL 字段抛 FormatException', () {
      expect(
        () => decodeRecentSearchEntry(<String, Object?>{'query': 'x'}),
        throwsFormatException,
      );
    });

    test('slice 解码 items 列表', () {
      final slice = decodeRecentSearchEntrySlice(<String, Object?>{
        'items': <Object?>[
          <String, Object?>{
            'entryId': 'recent_a',
            'query': 'a',
            'scope': 'all',
          },
        ],
      });
      expect(slice.items, hasLength(1));
    });
  });

  group('ReportSearchFeedbackCommand', () {
    test('wire 只含 metadata writable_fields', () {
      final payload = encodeReportSearchFeedbackCommand(
        ReportSearchFeedbackCommand(
          searchRequestId: 'req-1',
          eventType: 'click',
          objectId: 'post-9',
          target: 'posts',
          rankPosition: 2,
          referralSource: 'searchResults',
        ),
      );
      final body = payload.body as Map<String, Object?>;
      expect(
        body.keys.toSet().difference(<String>{
          'searchRequestId',
          'eventType',
          'objectId',
          'target',
          'rankPosition',
          'referralSource',
          'feedRequestId',
          'dwellMs',
        }),
        isEmpty,
      );
      expect(body['rankPosition'], 2);
    });

    test('非法 eventType 构造期拒绝', () {
      expect(
        () => ReportSearchFeedbackCommand(
          searchRequestId: 'req-1',
          eventType: 'smash',
        ),
        throwsArgumentError,
      );
    });

    test('ack 解码', () {
      expect(
        decodeSearchFeedbackAck(<String, Object?>{'accepted': true}).accepted,
        isTrue,
      );
      expect(
        decodeSearchFeedbackAck(<String, Object?>{'accepted': false}).accepted,
        isFalse,
      );
      expect(
        () => decodeSearchFeedbackAck(<String, Object?>{}),
        throwsA(isA<FormatException>()),
      );
      expect(
        () => decodeSearchFeedbackAck(<String, Object?>{'accepted': 'yes'}),
        throwsA(isA<FormatException>()),
      );
    });
  });

  group('ListHotQueriesQuery', () {
    test('limit 经 query parameter 编码且有界', () {
      final payload = encodeListHotQueriesQuery(ListHotQueriesQuery(limit: 6));
      expect(payload.queryParameters, <String, String>{'limit': '6'});
      expect(() => ListHotQueriesQuery(limit: 21), throwsArgumentError);
    });

    test('严格解码 query/relevance 并保留服务端顺序', () {
      final slice = decodeHotQuerySlice(<String, Object?>{
        'items': <Object?>[
          <String, Object?>{'query': '旅行摄影', 'relevance': 9.8},
          <String, Object?>{'query': '城市漫步', 'relevance': 9.1},
        ],
      });
      expect(slice.items.map((item) => item.query), <String>['旅行摄影', '城市漫步']);
      expect(
        () => decodeHotQuerySlice(<String, Object?>{
          'items': <Object?>[
            <String, Object?>{'query': '缺分值'},
          ],
        }),
        throwsFormatException,
      );
    });
  });
}

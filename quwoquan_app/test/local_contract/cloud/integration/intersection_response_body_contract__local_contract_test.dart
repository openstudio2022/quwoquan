/// R-ID02 端云契约测试：交集 operation 的框架级 response_body 声明
/// 与 Remote 仓库实际解码类型对齐（防「声明了没人消费」的死字段）。
///
/// 单一真相源 = contracts/metadata/content/post/service.yaml 的 response_body /
/// response_body_kind，经 codegen 落到 ContentApiMetadata.operationToResponseModel /
/// operationToResponseKind；本测试断言这两张映射与四个交集 operation 的真实解码行为一致。
library;

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_inbox_summary.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_repository.dart';

const _baseUrl = 'https://test-gateway.example.com';

MockClient _stubClient() {
  return MockClient((request) async {
    if (request.method == 'POST') {
      return http.Response(
        json.encode({'data': {'dimension': 'identity', 'status': 'visited'}}),
        200,
        headers: {'content-type': 'application/json'},
      );
    }
    final body = json.encode({
      'data': {
        'totalCount': 2,
        'totalNewCount': 1,
        'dimensions': <dynamic>[],
        'generatedAt': '2026-06-20T00:00:00Z',
      },
      'items': <dynamic>[
        {'dimension': 'identity', 'primaryText': '你的8位校友关注了这里'},
      ],
      'cursor': null,
    });
    return http.Response(
      body,
      200,
      headers: {'content-type': 'application/json'},
    );
  });
}

void main() {
  group('交集 response_body 框架契约（R-ID02）', () {
    late RemoteIntersectionRepository repo;

    setUp(() {
      repo = RemoteIntersectionRepository(
        httpClient: CloudHttpClient(client: _stubClient()),
        baseUrl: _baseUrl,
      );
    });

    test('operationToResponseKind 覆盖 4 个交集 operation 且形态正确', () {
      const kinds = ContentApiMetadata.operationToResponseKind;
      expect(kinds[ContentApiMetadata.getMyIntersectionSummaryOperation], 'object');
      expect(kinds[ContentApiMetadata.listMyIntersectionsOperation], 'page');
      expect(kinds[ContentApiMetadata.getObjectIntersectionsOperation], 'page');
      expect(kinds[ContentApiMetadata.markIntersectionsVisitedOperation], 'ack');
    });

    test('object 形态：getMyIntersectionSummary 解码类型 == 声明读模型', () async {
      final declared = ContentApiMetadata
          .operationToResponseModel[ContentApiMetadata.getMyIntersectionSummaryOperation];
      expect(declared, 'IntersectionInboxSummary');
      final summary = await repo.getMyIntersectionSummary();
      // 实际解码运行时类型必须与 metadata 声明的读模型一致。
      expect(summary, isA<IntersectionInboxSummary>());
      expect(summary.runtimeType.toString(), declared);
    });

    test('page 形态：listMyIntersections 元素类型 == 声明读模型', () async {
      final declared = ContentApiMetadata
          .operationToResponseModel[ContentApiMetadata.listMyIntersectionsOperation];
      expect(declared, 'IntersectionReason');
      final items = await repo.listMyIntersections();
      expect(items, isA<List<IntersectionReason>>());
      expect(items, isNotEmpty);
      expect(items.first.runtimeType.toString(), declared);
    });

    test('page 形态：getObjectIntersections 元素类型 == 声明读模型', () async {
      final declared = ContentApiMetadata
          .operationToResponseModel[ContentApiMetadata.getObjectIntersectionsOperation];
      expect(declared, 'IntersectionReason');
      final items = await repo.getObjectIntersections(
        objectId: 'obj_1',
        objectType: 'person',
      );
      expect(items, isA<List<IntersectionReason>>());
      expect(items, isNotEmpty);
      expect(items.first.runtimeType.toString(), declared);
    });

    test('ack 形态：markIntersectionsVisited 无读模型且返回 void', () async {
      expect(
        ContentApiMetadata.operationToResponseModel
            .containsKey(ContentApiMetadata.markIntersectionsVisitedOperation),
        isFalse,
      );
      // ack 仅状态确认，端返回 void；调用不应抛错。
      await expectLater(repo.markIntersectionsVisited(dimension: 'identity'), completes);
    });
  });
}

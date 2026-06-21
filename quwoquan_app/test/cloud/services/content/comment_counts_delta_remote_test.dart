/// T3 端云集成：RemoteContentRepository.getCommentCountsDelta 解析云侧响应
/// { createdSinceCount, deletedSinceCount, currentTotal, watermark, since }，
/// 与 T1 mock 半开区间语义字段一一对应（R12/R13）。
library;

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';

void main() {
  test('解析 counts-delta 响应字段（created/deleted/currentTotal/watermark/since）', () async {
    Uri? capturedUri;
    final client = MockClient((request) async {
      capturedUri = request.url;
      return http.Response(
        json.encode(<String, dynamic>{
          'createdSinceCount': 3,
          'deletedSinceCount': 1,
          'currentTotal': 26,
          'watermark': '2026-06-20T08:30:00.000Z',
          'since': '2026-06-20T08:00:00.000Z',
        }),
        200,
        headers: {'content-type': 'application/json'},
      );
    });
    final repo = RemoteContentRepository(
      httpClient: CloudHttpClient(client: client),
    );

    final delta = await repo.getCommentCountsDelta(
      postId: 'p1',
      since: DateTime.utc(2026, 6, 20, 8, 0),
    );

    expect(
      capturedUri!.path,
      ContentApiMetadata.getCommentCountsDeltaPath(postId: 'p1'),
    );
    expect(capturedUri!.queryParameters['since'], '2026-06-20T08:00:00.000Z');
    expect(delta.createdSinceCount, 3);
    expect(delta.deletedSinceCount, 1);
    expect(delta.currentTotal, 26);
    expect(delta.watermark, DateTime.utc(2026, 6, 20, 8, 30));
    expect(delta.since, DateTime.utc(2026, 6, 20, 8, 0));
    expect(delta.hasChanges, isTrue);
    expect(delta.netChange, 2);
  });

  test('缺失字段降级为 0，watermark 缺失退化非空', () async {
    final client = MockClient((request) async {
      return http.Response(
        json.encode(<String, dynamic>{'currentTotal': 5}),
        200,
        headers: {'content-type': 'application/json'},
      );
    });
    final repo = RemoteContentRepository(
      httpClient: CloudHttpClient(client: client),
    );

    final delta = await repo.getCommentCountsDelta(postId: 'p1');

    expect(delta.createdSinceCount, 0);
    expect(delta.deletedSinceCount, 0);
    expect(delta.currentTotal, 5);
    expect(delta.hasChanges, isFalse);
  });
}

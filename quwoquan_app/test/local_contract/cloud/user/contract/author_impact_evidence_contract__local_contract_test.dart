/// R-ID03 端云契约：创作者影响力完整证据分页明细（ListAuthorImpactEvidence）端侧接入。
///
/// 覆盖：
/// - response_body 框架契约（R-ID02）：kind=object、model=AuthorImpactEvidencePage；
/// - Remote：path/query 经 codegen path builder 对齐、object 解码为 AuthorImpactEvidencePage、
///   cursor 翻页透传；
/// - Mock：无 seed authorImpact（alpha lite）/未命中 impactId 时返回空页，不编造、不崩溃。
library;

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_evidence_item.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_evidence_page.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';

const _baseUrl = 'https://test-gateway.example.com';
const _subAccountId = 'fixture_user_current';

void main() {
  group('ListAuthorImpactEvidence response_body 框架契约（R-ID02）', () {
    test('kind=object、model=AuthorImpactEvidencePage', () {
      expect(
        ContentApiMetadata.operationToResponseKind[
            ContentApiMetadata.listAuthorImpactEvidenceOperation],
        'object',
      );
      expect(
        ContentApiMetadata.operationToResponseModel[
            ContentApiMetadata.listAuthorImpactEvidenceOperation],
        'AuthorImpactEvidencePage',
      );
    });
  });

  group('RemoteUserProfileRepository.listAuthorImpactEvidence（端云解码/翻页）', () {
    late List<http.Request> captured;

    RemoteUserProfileRepository repoReturning(List<Map<String, dynamic>> pages) {
      captured = <http.Request>[];
      var call = 0;
      final client = MockClient((request) async {
        captured.add(request);
        final page = pages[call < pages.length ? call : pages.length - 1];
        call++;
        return http.Response(
          json.encode(<String, dynamic>{'data': page}),
          200,
          headers: <String, String>{'content-type': 'application/json'},
        );
      });
      return RemoteUserProfileRepository(
        httpClient: CloudHttpClient(client: client),
        baseUrl: _baseUrl,
      );
    }

    test('path 经 codegen builder + query 透传 impactId/limit', () async {
      final repo = repoReturning(<Map<String, dynamic>>[
        <String, dynamic>{
          'impactId': 'imp_1',
          'evidenceSnapshotId': 'snap_1',
          'totalCount': 3,
          'items': <dynamic>[
            <String, dynamic>{
              'evidenceId': 'imp_1_ev_0',
              'impactId': 'imp_1',
              'summaryText': '有人收藏了《城市夜骑指南》',
              'occurredAt': '2026-06-19T08:00:00Z',
            },
            <String, dynamic>{
              'evidenceId': 'imp_1_ev_1',
              'impactId': 'imp_1',
              'summaryText': '有人转发了《城市夜骑指南》',
              'occurredAt': '2026-06-18T08:00:00Z',
            },
          ],
          'nextCursor': '2',
          'hasMore': true,
        },
      ]);

      final page = await repo.listAuthorImpactEvidence(
        subAccountId: _subAccountId,
        impactId: 'imp_1',
        limit: 20,
      );

      expect(page, isA<AuthorImpactEvidencePage>());
      expect(page.impactId, 'imp_1');
      expect(page.totalCount, 3);
      expect(page.items.length, 2);
      expect(page.items.first, isA<AuthorImpactEvidenceItem>());
      expect(page.hasMore, isTrue);
      expect(page.nextCursor, '2');

      final req = captured.single;
      expect(req.method, 'GET');
      expect(
        req.url.path,
        ContentApiMetadata.listAuthorImpactEvidencePath(
          subAccountId: _subAccountId,
        ),
      );
      expect(req.url.queryParameters['impactId'], 'imp_1');
      expect(req.url.queryParameters['limit'], '20');
      // 首页无 cursor。
      expect(req.url.queryParameters.containsKey('cursor'), isFalse);
    });

    test('cursor 翻页：第二页透传 cursor 且解码触底', () async {
      final repo = repoReturning(<Map<String, dynamic>>[
        <String, dynamic>{
          'impactId': 'imp_1',
          'totalCount': 3,
          'items': <dynamic>[
            <String, dynamic>{'evidenceId': 'e2', 'summaryText': '末页一条'},
          ],
          'nextCursor': '',
          'hasMore': false,
        },
      ]);

      final page = await repo.listAuthorImpactEvidence(
        subAccountId: _subAccountId,
        impactId: 'imp_1',
        cursor: '2',
      );

      expect(page.hasMore, isFalse);
      expect(page.items.single.summaryText, '末页一条');
      expect(captured.single.url.queryParameters['cursor'], '2');
    });
  });

  group('MockUserProfileRepository.listAuthorImpactEvidence（无 seed 安全）', () {
    late UserProfileRepository repo;

    setUp(() {
      repo = const MockUserProfileRepository();
    });

    test('未命中作者/impact 返回空页（不编造、不崩溃）', () async {
      final page = await repo.listAuthorImpactEvidence(
        subAccountId: 'no_such_author',
        impactId: 'no_such_impact',
      );
      expect(page, isA<AuthorImpactEvidencePage>());
      expect(page.items, isEmpty);
      expect(page.hasMore, isFalse);
    });

    test('alpha lite 无 authorImpact seed：本人作者亦返回空页（不阻塞、不造假）', () async {
      final page = await repo.listAuthorImpactEvidence(
        subAccountId: _subAccountId,
        impactId: 'imp_anything',
      );
      expect(page.items, isEmpty);
      expect(page.hasMore, isFalse);
    });
  });
}

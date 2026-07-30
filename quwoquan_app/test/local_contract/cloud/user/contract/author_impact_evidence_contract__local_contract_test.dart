/// R-ID03 端云契约：创作者影响力完整证据分页明细（ListAuthorImpactEvidence）端侧接入。
///
/// 覆盖：
/// - response_body 框架契约（R-ID02）：kind=object、model=AuthorImpactEvidencePage；
/// - Remote：path/query 经 codegen path builder 对齐、object 解码为 AuthorImpactEvidencePage、
///   cursor 翻页透传；
/// - Mock：无 seed authorImpact（alpha lite）/未命中 impactId 时返回空页，不编造、不崩溃。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/application/content/post/author_impact_query.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_evidence_item.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_evidence_page.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/remote/content/post/author_impact_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../support/cloud_services/repository_mock_reexports.dart';

const _personaId = 'fixture_user_current';

void main() {
  group('ListAuthorImpactEvidence response_body 框架契约（R-ID02）', () {
    test('kind=object、model=AuthorImpactEvidencePage', () {
      expect(
        ContentApiMetadata.operationToResponseKind[ContentApiMetadata
            .listAuthorImpactEvidenceOperation],
        'object',
      );
      expect(
        ContentApiMetadata.operationToResponseModel[ContentApiMetadata
            .listAuthorImpactEvidenceOperation],
        'AuthorImpactEvidencePage',
      );
    });
  });

  group('RemoteAuthorImpactQuery.listAuthorImpactEvidence（端云解码/翻页）', () {
    late _AuthorImpactExecutor executor;

    RemoteAuthorImpactQuery repoReturning(List<Map<String, Object?>> pages) {
      executor = _AuthorImpactExecutor(pages);
      return RemoteAuthorImpactQuery(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.userProfile.id,
          routeId: AppUiSurfaces.userProfile.routeId,
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(
            accountId: 'fixture_owner',
            personaId: 'fixture_persona',
          ),
        ),
      );
    }

    test('摘要读取经 generated client 传递 path 参数与默认 limit', () async {
      final repo = repoReturning(<Map<String, Object?>>[
        <String, Object?>{
          'authorId': _personaId,
          'total': 1,
          'items': <Object?>[],
        },
      ]);

      final summary = await repo.getAuthorImpact(_personaId);

      expect(summary.authorId, _personaId);
      expect(
        executor.operations.single.canonicalOperationId,
        AppCloudOperationIds.contentPostGetAuthorImpact,
      );
      expect(
        executor.operations.single.pathTemplate,
        ContentApiMetadata.getAuthorImpactPathTemplate,
      );
      expect(executor.requests.single.pathParameters['personaId'], _personaId);
      expect(executor.requests.single.queryParameters['limit'], '12');
    });

    test('path 经 codegen builder + query 透传 impactId/limit', () async {
      final repo = repoReturning(<Map<String, Object?>>[
        <String, Object?>{
          'impactId': 'imp_1',
          'evidenceSnapshotId': 'snap_1',
          'totalCount': 3,
          'items': <Object?>[
            <String, Object?>{
              'evidenceId': 'imp_1_ev_0',
              'impactId': 'imp_1',
              'summaryText': '有人收藏了《城市夜骑指南》',
              'occurredAt': '2026-06-19T08:00:00Z',
            },
            <String, Object?>{
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
        personaId: _personaId,
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

      final operation = executor.operations.single;
      final request = executor.requests.single;
      expect(operation.method, 'GET');
      expect(
        operation.pathTemplate,
        ContentApiMetadata.listAuthorImpactEvidencePathTemplate,
      );
      expect(request.pathParameters['personaId'], _personaId);
      expect(request.queryParameters['impactId'], 'imp_1');
      expect(request.queryParameters['limit'], '20');
      // Repository 的公开参数以空串表达首页；generated request 只做一次
      // canonical 编码，不再把它隐式改写为 null/缺省双轨。
      expect(request.queryParameters['cursor'], '');
    });

    test('cursor 翻页：第二页透传 cursor 且解码触底', () async {
      final repo = repoReturning(<Map<String, Object?>>[
        <String, Object?>{
          'impactId': 'imp_1',
          'totalCount': 3,
          'items': <Object?>[
            <String, Object?>{'evidenceId': 'e2', 'summaryText': '末页一条'},
          ],
          'nextCursor': '',
          'hasMore': false,
        },
      ]);

      final page = await repo.listAuthorImpactEvidence(
        personaId: _personaId,
        impactId: 'imp_1',
        cursor: '2',
      );

      expect(page.hasMore, isFalse);
      expect(page.items.single.summaryText, '末页一条');
      expect(executor.requests.single.queryParameters['cursor'], '2');
    });
  });

  group('AuthorImpactQuery alpha fixture（无 seed 安全）', () {
    late AuthorImpactQuery query;

    setUp(() {
      query = const MockUserProfileRepository();
    });

    test('未命中作者/impact 返回空页（不编造、不崩溃）', () async {
      final page = await query.listAuthorImpactEvidence(
        personaId: 'no_such_author',
        impactId: 'no_such_impact',
      );
      expect(page, isA<AuthorImpactEvidencePage>());
      expect(page.items, isEmpty);
      expect(page.hasMore, isFalse);
    });

    test('alpha lite 无 authorImpact seed：本人作者亦返回空页（不阻塞、不造假）', () async {
      final page = await query.listAuthorImpactEvidence(
        personaId: _personaId,
        impactId: 'imp_anything',
      );
      expect(page.items, isEmpty);
      expect(page.hasMore, isFalse);
    });
  });
}

final class _AuthorImpactExecutor implements CloudOperationExecutor {
  _AuthorImpactExecutor(this._pages);

  final List<Map<String, Object?>> _pages;
  final List<CloudOperationContract> operations = <CloudOperationContract>[];
  final List<CloudOperationRequestPayload> requests =
      <CloudOperationRequestPayload>[];
  var _call = 0;

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    operations.add(operation);
    requests.add(requestEncoder());
    final page = _pages[_call < _pages.length ? _call : _pages.length - 1];
    _call++;
    return responseDecoder(page);
  }
}

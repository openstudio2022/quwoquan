// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/career-interest-profile-editor/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/career-interest-profile-editor/spec.md#gwt-002
// readiness_case: tag_node_view_list_tag_children_app_local
// readiness_case: tag_node_view_resolve_tag_app_local
// readiness_case: tag_node_view_validate_tag_refs_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/tag/tag_request_page_ids.g.dart';
import 'package:quwoquan_app/service/tag_service/tag/tag_node_view/adapters/tag_catalog_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/remote_api_path_test_harness.dart';

/// wire 编解码用例只需要一个稳定的发布号；发布身份的真相源是 tag-service，
/// 不是端侧编译常量。
const String _taxonomyReleaseId = 'tag-taxonomy-contract-fixture';

http.Response _tagCatalogResponseFor(http.Request request) {
  if (request.method == 'GET' && request.url.path == '/tag/children') {
    return remoteApiPathJsonResponse(<String, Object?>{
      'items': <Object?>[
        <String, Object?>{
          'tagRef': 'Audience/用户/职业/产品运营',
          'label': '产品运营',
          'displayLabel': '产品运营',
          'parentTagRef': 'Audience/用户/职业',
          'depth': 3,
          'hasChildren': true,
          'releaseId': _taxonomyReleaseId,
          'lifecycleStatus': 'active',
        },
      ],
    });
  }
  if (request.method == 'GET' && request.url.path == '/tag/resolve') {
    return remoteApiPathJsonResponse(<String, Object?>{
      'tagRef': 'Audience/用户/职业/产品运营/产品经理',
      'group': 'Audience',
      'label': '产品经理',
      'ancestors': <Object?>['Audience/用户/职业', 'Audience/用户/职业/产品运营'],
    });
  }
  if (request.method == 'POST' && request.url.path == '/tag/validate') {
    return remoteApiPathJsonResponse(<String, Object?>{
      'taxonomyReleaseId': _taxonomyReleaseId,
      'valid': <Object?>['Audience/用户/职业/产品运营/产品经理'],
      'invalid': <Object?>['Topic/兴趣/旅行'],
    });
  }
  throw StateError(
    'unexpected TagCatalog request: ${request.method} ${request.url.path}',
  );
}

CloudOperationInvocationContext _tagCatalogContext(String clientPageId) =>
    CloudOperationInvocationContext(
      surfaceId: AppUiSurfaces.profileCareerInterests.id,
      routeId: AppUiSurfaces.profileCareerInterests.routeId,
      clientPageId: clientPageId,
      actor: const CloudOperationActorContext(
        accountId: 'account-tag-catalog',
        personaId: 'persona-tag-catalog',
        deviceActorId: 'device-tag-catalog',
      ),
    );

void main() {
  group('TagCatalog generated client contracts', () {
    test(
      'production Remote executes children, resolve, and validate operations',
      () async {
        final requests = <CapturedRemoteApiPathRequest>[];
        final catalog = RemoteGeneratedTagCatalogQuery(
          client: buildRemoteApiPathOperationClient(
            requests,
            responseFor: _tagCatalogResponseFor,
          ),
          invocationContext: _tagCatalogContext,
        );

        final children = await catalog.listChildren(
          ' Audience/用户/职业 ',
          limit: 30,
        );
        final resolved = await catalog.resolveTag(' Audience/用户/职业/产品运营/产品经理 ');
        final validation = await catalog.validateRefs(
          expectedTaxonomyReleaseId: _taxonomyReleaseId,
          tagRefs: const <String>['Audience/用户/职业/产品运营/产品经理', 'Topic/兴趣/旅行'],
        );

        expect(children, hasLength(1));
        expect(children.single.tagRef, 'Audience/用户/职业/产品运营');
        expect(children.single.releaseId, _taxonomyReleaseId);
        expect(resolved.tagRef, 'Audience/用户/职业/产品运营/产品经理');
        expect(resolved.label, '产品经理');
        expect(validation.valid, const <String>['Audience/用户/职业/产品运营/产品经理']);
        expect(validation.invalid, const <String>['Topic/兴趣/旅行']);

        expect(requests, hasLength(3));
        expect(requests[0].method, 'GET');
        expect(requests[0].path, '/tag/children');
        expect(requests[0].query, <String, String>{
          'parentTagRef': 'Audience/用户/职业',
          'limit': '30',
        });
        expect(requests[0].body, isEmpty);
        expectRemoteApiPathHeaders(
          requests[0].headers,
          clientPageId: TagRequestPageIds.listTagChildren,
          surfaceId: AppUiSurfaces.profileCareerInterests.id,
          operationId: AppCloudOperationIds.tagTagNodeViewListTagChildren,
        );

        expect(requests[1].method, 'GET');
        expect(requests[1].path, '/tag/resolve');
        expect(requests[1].query, <String, String>{
          'tagRef': 'Audience/用户/职业/产品运营/产品经理',
        });
        expect(requests[1].body, isEmpty);
        expectRemoteApiPathHeaders(
          requests[1].headers,
          clientPageId: TagRequestPageIds.resolveTag,
          surfaceId: AppUiSurfaces.profileCareerInterests.id,
          operationId: AppCloudOperationIds.tagTagNodeViewResolveTag,
        );

        expect(requests[2].method, 'POST');
        expect(requests[2].path, '/tag/validate');
        expect(requests[2].query, isEmpty);
        expect(requests[2].body, <String, Object?>{
          'expectedTaxonomyReleaseId': _taxonomyReleaseId,
          'tagRefs': <Object?>['Audience/用户/职业/产品运营/产品经理', 'Topic/兴趣/旅行'],
        });
        expectRemoteApiPathHeaders(
          requests[2].headers,
          clientPageId: TagRequestPageIds.validateTagRefs,
          surfaceId: AppUiSurfaces.profileCareerInterests.id,
          operationId: AppCloudOperationIds.tagTagNodeViewValidateTagRefs,
        );

        for (final request in requests) {
          expect(request.headers, isNot(contains('authorization')));
        }
      },
    );

    test('encodes commercial App queries without exposing wire maps', () {
      final resolve = encodeTagTagNodeViewResolveTagGeneratedRequest(
        ResolveTagQuery(tagRef: ' Topic/旅行 '),
      );
      final children = encodeTagTagNodeViewListTagChildrenGeneratedRequest(
        ListTagChildrenQuery(parentTagRef: 'Topic/旅行', limit: 30),
      );
      final validation = encodeTagTagNodeViewValidateTagRefsGeneratedRequest(
        ValidateTagRefsQuery(
          expectedTaxonomyReleaseId: _taxonomyReleaseId,
          tagRefs: const ['Topic/旅行', 'Place/中国'],
        ),
      );

      expect(resolve.queryParameters, {'tagRef': 'Topic/旅行'});
      expect(children.queryParameters, {
        'parentTagRef': 'Topic/旅行',
        'limit': '30',
      });
      expect(validation.body, {
        'expectedTaxonomyReleaseId': _taxonomyReleaseId,
        'tagRefs': ['Topic/旅行', 'Place/中国'],
      });
    });

    test('decodes resolve, children and validation responses', () {
      final resolved = decodeTagResolveView({
        'tagRef': 'Topic/旅行',
        'group': 'Topic',
        'label': '旅行',
        'labelEn': 'Travel',
        'aliases': ['旅游'],
        'ancestors': ['Topic'],
      });
      final children = decodeTagChildrenSlice({
        'items': [
          {
            'tagRef': 'Topic/旅行/攻略',
            'label': '攻略',
            'displayLabel': '攻略',
            'labelEn': 'Guide',
            'parentTagRef': 'Topic/旅行',
            'depth': 2,
            'hasChildren': false,
            'releaseId': 'tag-release',
            'lifecycleStatus': 'active',
          },
        ],
      });
      final validation = decodeTagValidationResultView({
        'taxonomyReleaseId': _taxonomyReleaseId,
        'valid': ['Topic/旅行'],
        'invalid': ['Topic/不存在'],
      });

      expect(resolved.label, '旅行');
      expect(children.items.single.parentTagRef, 'Topic/旅行');
      expect(validation.taxonomyReleaseId, _taxonomyReleaseId);
      expect(validation.valid, ['Topic/旅行']);
      expect(validation.invalid, ['Topic/不存在']);
    });

    test(
      'malformed Remote projections fail closed instead of synthesizing data',
      () {
        expect(
          () => decodeTagResolveView({'tagRef': 'Topic/旅行'}),
          throwsA(isA<FormatException>()),
        );
        expect(
          () => decodeTagChildrenSlice({
            'items': [
              {
                'tagRef': 'Topic/旅行/攻略',
                'label': '攻略',
                'displayLabel': '攻略',
                'labelEn': 'Guide',
                'parentTagRef': 'Topic/旅行',
                'depth': '2',
                'hasChildren': false,
                'releaseId': 'tag-release',
                'lifecycleStatus': 'active',
              },
            ],
          }),
          throwsA(isA<FormatException>()),
        );
        expect(
          () => decodeTagChildrenSlice(const <Object?>[]),
          throwsA(isA<FormatException>()),
        );
        expect(
          () => decodeTagValidationResultView({
            'taxonomyReleaseId': 'tag-release',
            'valid': 'Topic/旅行',
            'invalid': const <String>[],
          }),
          throwsA(isA<FormatException>()),
        );
      },
    );

    test('Tag feedback result requires an explicit bool', () {
      expect(
        decodeTagFeedbackResultView(<String, Object?>{
          'accepted': true,
        }).accepted,
        isTrue,
      );
      expect(
        decodeTagFeedbackResultView(<String, Object?>{
          'accepted': false,
        }).accepted,
        isFalse,
      );
      expect(
        () => decodeTagFeedbackResultView(<String, Object?>{}),
        throwsA(isA<FormatException>()),
      );
    });

    test('Tag feedback action is a metadata-owned typed enum', () {
      final request = ReportTagFeedbackCommand(
        tagRef: ' Topic/旅行 ',
        action: TagFeedbackAction.correct,
      );

      expect(
        encodeTagTagFeedbackFactReportTagFeedbackGeneratedRequest(request).body,
        <String, Object?>{'tagRef': 'Topic/旅行', 'action': 'correct'},
      );
    });

    test('Every feedback action encodes to its own wire value', () {
      final encoded = <String>{};
      for (final action in TagFeedbackAction.values) {
        final body =
            encodeTagTagFeedbackFactReportTagFeedbackGeneratedRequest(
                  ReportTagFeedbackCommand(tagRef: 'Topic/旅行', action: action),
                ).body
                as Map<String, Object?>;
        expect(body['action'], action.wireName);
        expect(encoded.add(action.wireName), isTrue);
      }
    });

    test('Tag feedback carries a negative action, not only positive ones', () {
      // 只有 click/ignore/correct 时，用户无法把推错的标签压下去：
      // ignore 只回到无偏好，correct 不改特征。
      expect(TagFeedbackAction.values, contains(TagFeedbackAction.dislike));
      expect(
        encodeTagTagFeedbackFactReportTagFeedbackGeneratedRequest(
          ReportTagFeedbackCommand(
            tagRef: 'Topic/摄影/器材/无人机',
            action: TagFeedbackAction.dislike,
          ),
        ).body,
        <String, Object?>{'tagRef': 'Topic/摄影/器材/无人机', 'action': 'dislike'},
      );
    });
  });
}

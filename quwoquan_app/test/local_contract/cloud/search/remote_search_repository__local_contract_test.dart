import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/application/search/search_operation_ports.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';
import 'package:quwoquan_app/core/models/search_models.dart';
import 'package:quwoquan_app/core/services/remote_search_repository.dart';
import 'package:quwoquan_app/core/services/search_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'user.profile canonical hit stays typed through RemoteSearchRepository',
    () async {
      final repository = RemoteSearchRepository(
        remoteQuery: _UserSearchQueryFacet(),
        sessionIdProvider: () => 'search-session',
      );

      final response = await repository.search(
        const SearchRequest(
          query: '林',
          mode: SearchMode.result,
          objectTypes: <SearchObjectType>{SearchObjectType.userProfile},
        ),
      );

      expect(response.hits, hasLength(1));
      final hit = response.hits.single;
      final user = hit.asUserProfileItem;
      expect(user, isNotNull);
      expect(user!.userId, 'user_lin');
      expect(user.displayName, '林同学');
      expect(user.bio, '摄影与城市漫步');
      expect(user.connectionState, 'intersection_lead');
      expect(user.intersectionReason?.primaryText, '你们都关注了光影摄影社');
    },
  );

  test(
    'production remote maps every cloud target to a named payload',
    () async {
      final repository = RemoteSearchRepository(
        remoteQuery: _AllTargetsFacet(),
        sessionIdProvider: () => 'search-session',
      );

      final response = await repository.search(
        const SearchRequest(query: '光影', mode: SearchMode.result),
      );

      expect(response.hits, hasLength(6));
      expect(
        response.hits.map((hit) => hit.payload),
        containsAll(<Matcher>[
          isA<SearchHitPayloadContentPost>(),
          isA<SearchHitPayloadUserProfile>(),
          isA<SearchHitPayloadEntityHomepage>(),
          isA<SearchHitPayloadLocationPlace>(),
          isA<SearchHitPayloadCircleCircle>(),
          isA<SearchHitPayloadCircleGroup>(),
        ]),
      );
      expect(
        response.hits.every((hit) => hit.payload is! SearchHitPayloadEmpty),
        isTrue,
      );
    },
  );
}

final class _UserSearchQueryFacet implements CanonicalSearchQueryFacet {
  @override
  Future<SearchResponseView> search(
    CanonicalSearchQuery query, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    return SearchResponseView(
      provenance: CanonicalSearchProvenance(
        provider: 'elasticsearch',
        generatedAt: DateTime.utc(2026, 7, 31),
      ),
      requestId: 'search.req.user',
      hits: <CanonicalSearchHit>[
        _canonicalHit(
          target: 'user',
          objectType: 'user.profile',
          objectId: 'user_lin',
          title: '林同学',
          snippet: '摄影与城市漫步',
          connectionState: 'intersection_lead',
          intersectionReason: CanonicalSearchIntersectionReason(
            primaryText: '你们都关注了光影摄影社',
            intersectionId: 'ix_user_lin',
            dimension: 'circle',
            intersectionClass: 'fact',
            sourceRef: 'sharedCircle',
          ),
        ),
      ],
    );
  }
}

final class _AllTargetsFacet implements CanonicalSearchQueryFacet {
  @override
  Future<SearchResponseView> search(
    CanonicalSearchQuery query, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    return SearchResponseView(
      provenance: CanonicalSearchProvenance(
        provider: 'elasticsearch',
        generatedAt: DateTime.utc(2026, 7, 31),
      ),
      requestId: 'search.req.all-targets',
      hits: <CanonicalSearchHit>[
        _canonicalHit(
          target: 'article',
          objectType: 'content.post',
          objectId: 'post-1',
          title: '光影文章',
          content: CanonicalSearchContentHit(
            postId: 'post-1',
            contentType: ContentType.article,
            title: '光影文章',
            likeCount: 0,
          ),
        ),
        _canonicalHit(
          target: 'user',
          objectType: 'user.profile',
          objectId: 'user-1',
          title: '光影用户',
        ),
        _canonicalHit(
          target: 'entity',
          objectType: 'entity.homepage',
          objectId: 'homepage-1',
          title: '光影主页',
        ),
        _canonicalHit(
          target: 'location',
          objectType: 'location.place',
          objectId: 'place-1',
          title: '光影地点',
        ),
        _canonicalHit(
          target: 'circle',
          objectType: 'circle.circle',
          objectId: 'circle-1',
          title: '光影圈子',
        ),
        _canonicalHit(
          target: 'group',
          objectType: 'circle.group',
          objectId: 'group-1',
          title: '光影讨论',
        ),
      ],
    );
  }
}

CanonicalSearchHit _canonicalHit({
  required String target,
  required String objectType,
  required String objectId,
  required String title,
  String? snippet,
  String? connectionState,
  CanonicalSearchIntersectionReason? intersectionReason,
  CanonicalSearchContentHit? content,
}) {
  return CanonicalSearchHit(
    target: target,
    objectType: objectType,
    objectId: objectId,
    title: title,
    snippet: snippet,
    score: 0,
    matchedTerms: const <String>[],
    matchedTags: const <String>[],
    evidence: const <CanonicalSearchEvidence>[],
    connectionState: connectionState,
    intersectionReason: intersectionReason,
    rankReasons: const <CanonicalSearchRankReason>[],
    content: content,
  );
}

import 'package:flutter_test/flutter_test.dart';
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
        response.hits.any((hit) => hit.payload is SearchHitPayloadWireMap),
        isFalse,
      );
    },
  );
}

final class _UserSearchQueryFacet implements CanonicalSearchQueryFacet {
  @override
  Future<CanonicalSearchResult> search(
    CanonicalSearchQuery query, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    return CanonicalSearchResult(
      requestId: 'search.req.user',
      rankingVersion: 'search-v1',
      hits: <CanonicalSearchHit>[
        CanonicalSearchHit(
          target: 'user',
          objectId: 'user_lin',
          title: '林同学',
          snippet: '摄影与城市漫步',
          connectionState: 'intersection_lead',
          intersectionReason: const CanonicalSearchIntersectionReason(
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
  Future<CanonicalSearchResult> search(
    CanonicalSearchQuery query, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    return CanonicalSearchResult(
      requestId: 'search.req.all-targets',
      rankingVersion: 'search-v1',
      hits: <CanonicalSearchHit>[
        CanonicalSearchHit(
          target: 'article',
          objectId: 'post-1',
          title: '光影文章',
          content: const CanonicalSearchContentHit(
            postId: 'post-1',
            contentType: 'article',
            title: '光影文章',
          ),
        ),
        CanonicalSearchHit(target: 'user', objectId: 'user-1', title: '光影用户'),
        CanonicalSearchHit(
          target: 'entity',
          objectId: 'homepage-1',
          title: '光影主页',
        ),
        CanonicalSearchHit(
          target: 'location',
          objectId: 'place-1',
          title: '光影地点',
        ),
        CanonicalSearchHit(
          target: 'circle',
          objectId: 'circle-1',
          title: '光影圈子',
        ),
        CanonicalSearchHit(target: 'group', objectId: 'group-1', title: '光影讨论'),
      ],
    );
  }
}

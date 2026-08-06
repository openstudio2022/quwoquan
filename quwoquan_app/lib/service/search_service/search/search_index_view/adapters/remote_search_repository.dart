import 'package:quwoquan_app/service/circle_service/circle_management/circle/application/public/circle_search_hit_views.dart';
import 'package:quwoquan_app/service/integration_service/external_integration/location/application/public/search_location_place_hit_view.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_search_item_view/application/public/search_entity_homepage_hit_view.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/canonical_search_query_facet.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/generated/search_execution_policy.g.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/post_search_item_view.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/search_hit_payload.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/search_repository.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/search_execution_values.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/search_query_contract.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/search_user_profile_hit_view.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 全局搜索唯一生产适配器：只调用 search-service canonical generated operation。
final class RemoteSearchRepository implements SearchRepository {
  const RemoteSearchRepository({
    required this.remoteQuery,
    required this.sessionIdProvider,
  });

  final CanonicalSearchQueryFacet remoteQuery;
  final String Function() sessionIdProvider;

  @override
  Future<SearchResponse> search(
    SearchRequest request, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    final normalized = request.normalized();
    if (normalized.query.isEmpty) {
      return SearchResponse(
        request: normalized,
        sections: const <SearchSection>[],
      );
    }

    final targets = _canonicalTargets(normalized);
    if (normalized.objectTypes.isNotEmpty && targets.isEmpty) {
      return SearchResponse(
        request: normalized,
        sections: const <SearchSection>[],
      );
    }

    final result = await remoteQuery.search(
      CanonicalSearchQuery(
        sessionId: sessionIdProvider(),
        query: normalized.query,
        mode: normalized.mode == CanonicalSearchMode.suggest
            ? CanonicalSearchMode.suggest
            : CanonicalSearchMode.result,
        objectTypes: targets.map((target) => target.wireValue),
        ids: normalized.ids,
        limit: normalized.limit,
      ),
      cancellation: cancellation,
      deadlineAt: deadlineAt,
    );
    return _responseFromCanonical(normalized, result);
  }

  SearchResponse _responseFromCanonical(
    SearchRequest request,
    SearchResponseView result,
  ) {
    final hits = result.hits
        .map(_hitFromCanonical)
        .whereType<SearchHit>()
        .toList(growable: false);
    final byType = <SearchObjectType, List<SearchHit>>{};
    for (final hit in hits) {
      byType.putIfAbsent(hit.objectType, () => <SearchHit>[]).add(hit);
    }
    return SearchResponse(
      request: request,
      sections: byType.entries
          .map(
            (entry) => SearchSection(
              id: entry.key.wireValue,
              title: entry.key.wireValue,
              objectTypes: <SearchObjectType>[entry.key],
              hits: entry.value,
              resolvedFrom: SearchResolvedFrom.remote,
            ),
          )
          .toList(growable: false),
      degradeSignals: result.degradeSignals
          .map(
            (signal) => SearchDegradeSignal(
              code: signal.code,
              message: signal.message,
              objectType: SearchObjectType.fromWire(signal.objectType),
            ),
          )
          .toList(growable: false),
      relatedTerms: result.relatedTerms,
      searchRequestId: result.requestId.trim().isEmpty
          ? null
          : result.requestId.trim(),
    );
  }

  SearchHit? _hitFromCanonical(CanonicalSearchHit hit) {
    final target = RetrieveTarget.fromWire(hit.target);
    if (target == null) {
      return null;
    }
    final policy = SearchExecutionPolicy.retrievePolicyFor(target);
    if (policy == null || !_isCloudRetrievable(policy.objectType)) {
      return null;
    }
    if (hit.objectType != policy.objectType.wireValue) {
      return null;
    }
    final objectID = hit.objectId.trim();
    if (objectID.isEmpty) {
      return null;
    }
    final connectionState = hit.connectionState?.trim() ?? '';
    final matchedField = hit.evidence.isEmpty
        ? null
        : hit.evidence.first.field.trim();
    final rankReasons = hit.rankReasons
        .map((reason) => reason.label.trim())
        .where((label) => label.isNotEmpty)
        .toList(growable: false);

    final SearchHitPayload payload;
    if (policy.objectType == SearchObjectType.contentPost) {
      final content = hit.content;
      if (content == null) {
        return null;
      }
      payload = SearchHitPayloadContentPost(
        PostSearchItemView.fromCanonical(
          content,
          highlightText: hit.snippet,
          matchedField: matchedField,
          connectionState: connectionState.isEmpty
              ? 'unconnected'
              : connectionState,
          intersectionReason: hit.intersectionReason,
        ),
      );
    } else if (policy.objectType == SearchObjectType.userProfile) {
      payload = SearchHitPayloadUserProfile(
        SearchUserProfileHitView(
          userId: objectID,
          displayName: hit.title.trim().isEmpty ? objectID : hit.title.trim(),
          bio: (hit.snippet?.trim() ?? '').isEmpty ? null : hit.snippet?.trim(),
          connectionState: connectionState.isEmpty
              ? 'unconnected'
              : connectionState,
          intersectionReason: _intersectionReason(hit.intersectionReason),
        ),
      );
    } else if (policy.objectType == SearchObjectType.circleCircle) {
      payload = SearchHitPayloadCircleCircle(
        _circleItem(hit, objectID: objectID),
      );
    } else if (policy.objectType == SearchObjectType.circleGroup) {
      payload = SearchHitPayloadCircleGroup(
        _circleItem(hit, objectID: objectID),
      );
    } else if (policy.objectType == SearchObjectType.entityHomepage) {
      payload = SearchHitPayloadEntityHomepage(
        SearchEntityHomepageHitView(
          homepageId: objectID,
          name: hit.title,
          subtitle: hit.snippet,
          placeName: hit.payload?.placeName,
          address: hit.payload?.address,
          followerCount: hit.payload?.followerCount ?? 0,
          contentCount: hit.payload?.contentCount ?? 0,
        ),
      );
    } else if (policy.objectType == SearchObjectType.locationPlace) {
      payload = SearchHitPayloadLocationPlace(
        SearchLocationPlaceHitView(
          placeId: objectID,
          name: hit.title,
          address: hit.payload?.address,
        ),
      );
    } else {
      return null;
    }

    final rawPayload = hit.payload;
    final intersectionReason = _intersectionReason(hit.intersectionReason);
    return SearchHit(
      objectType: policy.objectType,
      objectId: objectID,
      title: hit.title.trim().isEmpty ? objectID : hit.title.trim(),
      subtitle: _firstNonEmpty(<Object?>[
        rawPayload?.placeName,
        rawPayload?.circleName,
      ]),
      snippet: hit.snippet,
      resolvedFrom: SearchResolvedFrom.remote,
      matchedField: matchedField,
      payload: payload,
      connectionState: connectionState.isEmpty
          ? 'unconnected'
          : connectionState,
      intersectionReason: intersectionReason,
      rankReasons: rankReasons,
      rankPosition: hit.rankPosition,
    );
  }

  CircleSearchHitViewData _circleItem(
    CanonicalSearchHit hit, {
    required String objectID,
  }) {
    final payload = hit.payload;
    return CircleSearchHitViewData(
      circleId: payload?.circleId ?? objectID,
      name: hit.title,
      description: hit.snippet,
      coverUrl: payload?.coverUrl,
      categoryId: payload?.categoryId,
      subCategory: payload?.subCategory,
      domainId: payload?.domainId,
      kind: payload?.kind,
      displaySubjectType: payload?.displaySubjectType,
      memberCount: payload?.memberCount ?? 0,
      postCount: payload?.postCount ?? 0,
      highlightText: hit.snippet,
      matchedField: hit.evidence.isEmpty ? null : hit.evidence.first.field,
      circleName: payload?.circleName,
      linkedHomepageId: payload?.linkedHomepageId,
      linkedHomepageType: payload?.linkedHomepageType,
      linkedHomepageTitle: payload?.linkedHomepageTitle,
    );
  }

  CanonicalSearchIntersectionReason? _intersectionReason(
    CanonicalSearchIntersectionReason? reason,
  ) {
    if (reason == null || (reason.primaryText?.trim() ?? '').isEmpty) {
      return null;
    }
    return reason;
  }

  List<RetrieveTarget> _canonicalTargets(SearchRequest request) {
    final targets = <RetrieveTarget>{};
    for (final objectType in request.objectTypes) {
      switch (objectType) {
        case SearchObjectType.contentPost:
          targets.addAll(_contentTargets(request.contentTypes));
        case SearchObjectType.userProfile:
          targets.add(RetrieveTarget.user);
        case SearchObjectType.entityHomepage:
          targets.add(RetrieveTarget.entity);
        case SearchObjectType.circleCircle:
          targets.add(RetrieveTarget.circle);
        case SearchObjectType.circleGroup:
          targets.add(RetrieveTarget.group);
        case SearchObjectType.locationPlace:
          targets.add(RetrieveTarget.location);
        case SearchObjectType.chatContact:
        case SearchObjectType.chatConversation:
        case SearchObjectType.chatMessage:
        case SearchObjectType.webDocument:
        case SearchObjectType.tag:
        case SearchObjectType.integrationLocationPoi:
          break;
      }
    }
    if (targets.isEmpty && request.objectTypes.isEmpty) {
      targets.addAll(<RetrieveTarget>[
        RetrieveTarget.article,
        RetrieveTarget.photo,
        RetrieveTarget.video,
        RetrieveTarget.user,
        RetrieveTarget.entity,
        RetrieveTarget.circle,
        RetrieveTarget.group,
        RetrieveTarget.location,
      ]);
    }
    return targets.toList(growable: false);
  }

  Iterable<RetrieveTarget> _contentTargets(
    Set<SearchContentTypeFilter> contentTypes,
  ) {
    if (contentTypes.isEmpty) {
      return const <RetrieveTarget>[
        RetrieveTarget.article,
        RetrieveTarget.photo,
        RetrieveTarget.video,
      ];
    }
    final targets = <RetrieveTarget>{};
    for (final contentType in contentTypes) {
      switch (contentType) {
        case SearchContentTypeFilter.article:
        case SearchContentTypeFilter.micro:
          targets.add(RetrieveTarget.article);
        case SearchContentTypeFilter.image:
          targets.add(RetrieveTarget.photo);
        case SearchContentTypeFilter.video:
          targets.add(RetrieveTarget.video);
      }
    }
    return targets;
  }

  bool _isCloudRetrievable(SearchObjectType type) {
    return switch (type) {
      SearchObjectType.contentPost ||
      SearchObjectType.userProfile ||
      SearchObjectType.entityHomepage ||
      SearchObjectType.circleCircle ||
      SearchObjectType.circleGroup ||
      SearchObjectType.locationPlace => true,
      SearchObjectType.chatContact ||
      SearchObjectType.chatConversation ||
      SearchObjectType.chatMessage ||
      SearchObjectType.webDocument ||
      SearchObjectType.tag ||
      SearchObjectType.integrationLocationPoi => false,
    };
  }

  String? _firstNonEmpty(List<Object?> values) {
    for (final value in values) {
      final text = value?.toString().trim();
      if (text != null && text.isNotEmpty) {
        return text;
      }
    }
    return null;
  }
}

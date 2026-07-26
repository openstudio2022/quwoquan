import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/core/models/search_models.dart';
import 'package:quwoquan_app/core/services/retrieve_request.dart';
import 'package:quwoquan_app/core/services/search_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 全局搜索唯一生产适配器：只调用 search-service canonical generated operation。
final class RemoteSearchRepository implements SearchRepository {
  const RemoteSearchRepository({required this.remoteQuery});

  final CanonicalSearchQueryFacet remoteQuery;

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
        query: normalized.query,
        mode: normalized.mode == SearchMode.suggest
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
    CanonicalSearchResult result,
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
              title:
                  SearchRegistry.entryFor(entry.key)?.label ??
                  entry.key.wireValue,
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
    final entry = RetrieveTargetRegistry.entryFor(target);
    if (entry == null || !_isCloudRetrievable(entry.objectType)) {
      return null;
    }
    final objectID = hit.objectId.trim();
    if (objectID.isEmpty) {
      return null;
    }
    final connectionState = hit.connectionState.trim();

    final SearchHitPayload payload;
    if (entry.objectType == SearchObjectType.contentPost) {
      final content = hit.content;
      if (content == null) {
        return null;
      }
      payload = SearchHitPayloadContentPost(
        PostSearchItemView.fromCanonical(content),
      );
    } else if (entry.objectType == SearchObjectType.userProfile) {
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
    } else if (entry.objectType == SearchObjectType.circleCircle) {
      payload = SearchHitPayloadCircleCircle(
        _circleItem(hit, objectID: objectID),
      );
    } else if (entry.objectType == SearchObjectType.circleGroup) {
      payload = SearchHitPayloadCircleGroup(
        _circleItem(hit, objectID: objectID),
      );
    } else if (entry.objectType == SearchObjectType.entityHomepage) {
      payload = SearchHitPayloadEntityHomepage(
        SearchEntityHomepageHitView(
          homepageId: objectID,
          name: hit.title,
          subtitle: hit.snippet,
          placeName: _payloadText(hit.payload, 'placeName'),
          address: _payloadText(hit.payload, 'address'),
          followerCount: _payloadInt(hit.payload, 'followerCount'),
          contentCount: _payloadInt(hit.payload, 'contentCount'),
        ),
      );
    } else if (entry.objectType == SearchObjectType.locationPlace) {
      payload = SearchHitPayloadLocationPlace(
        SearchLocationPlaceHitView(
          placeId: objectID,
          name: hit.title,
          address: _payloadText(hit.payload, 'address'),
        ),
      );
    } else {
      return null;
    }

    final rawPayload = hit.payload;
    final intersectionReason = _intersectionReason(hit.intersectionReason);
    return SearchHit(
      objectType: entry.objectType,
      objectId: objectID,
      title: hit.title.trim().isEmpty ? objectID : hit.title.trim(),
      subtitle: _firstNonEmpty(<Object?>[
        rawPayload['subtitle'],
        rawPayload['placeName'],
        rawPayload['circleName'],
        rawPayload['authorDisplayName'],
      ]),
      snippet: hit.snippet,
      resolvedFrom: SearchResolvedFrom.remote,
      matchedField: hit.matchedField,
      payload: payload,
      connectionState: connectionState.isEmpty
          ? 'unconnected'
          : connectionState,
      intersectionReason: intersectionReason,
      rankReasons: hit.rankReasons,
      rankPosition: hit.rankPosition,
      coverWidth: hit.coverWidth,
      coverHeight: hit.coverHeight,
    );
  }

  CircleSearchItemView _circleItem(
    CanonicalSearchHit hit, {
    required String objectID,
  }) {
    return CircleSearchItemView(
      circleId: _payloadText(hit.payload, 'circleId') ?? objectID,
      name: hit.title,
      description: hit.snippet,
      coverUrl: _payloadText(hit.payload, 'coverUrl'),
      categoryId: _payloadText(hit.payload, 'categoryId'),
      subCategory: _payloadText(hit.payload, 'subCategory'),
      domainId: _payloadText(hit.payload, 'domainId'),
      kind: _payloadText(hit.payload, 'kind'),
      displaySubjectType: _payloadText(hit.payload, 'displaySubjectType'),
      memberCount: _payloadInt(hit.payload, 'memberCount'),
      postCount: _payloadInt(hit.payload, 'postCount'),
      highlightText: hit.snippet,
      matchedField: hit.matchedField,
      circleName: _payloadText(hit.payload, 'circleName'),
      linkedHomepageId: _payloadText(hit.payload, 'linkedHomepageId'),
      linkedHomepageType: _payloadText(hit.payload, 'linkedHomepageType'),
      linkedHomepageTitle: _payloadText(hit.payload, 'linkedHomepageTitle'),
    );
  }

  IntersectionReason? _intersectionReason(
    CanonicalSearchIntersectionReason? reason,
  ) {
    if (reason == null || reason.primaryText.trim().isEmpty) {
      return null;
    }
    return IntersectionReason(
      primaryText: reason.primaryText,
      intersectionId: reason.intersectionId,
      dimension: reason.dimension,
      intersectionClass: reason.intersectionClass,
      source: reason.sourceRef,
      displayBinding: 'host_plain',
    );
  }

  List<RetrieveTarget> _canonicalTargets(SearchRequest request) {
    return RetrieveRequest.fromSearchRequest(request).targets
        .where((target) => target != RetrieveTarget.chat)
        .toList(growable: false);
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

  String? _payloadText(Map<String, Object?> payload, String key) {
    final text = payload[key]?.toString().trim();
    return text == null || text.isEmpty ? null : text;
  }

  int _payloadInt(Map<String, Object?> payload, String key) {
    final value = payload[key];
    if (value is num) {
      return value.toInt();
    }
    return int.tryParse(value?.toString() ?? '') ?? 0;
  }
}

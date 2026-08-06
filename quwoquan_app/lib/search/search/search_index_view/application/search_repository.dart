import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';
import 'package:quwoquan_app/core/models/search_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

part 'search_repository_models.dart';

abstract interface class SearchRepository {
  Future<SearchResponse> search(
    SearchRequest request, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  });
}

extension SearchHitTypedViews on SearchHit {
  ChatContactSearchItemViewData? get asChatContactItem {
    final value = payload;
    return value is SearchHitPayloadChatContact ? value.item : null;
  }

  ConversationSearchItemView? get asChatConversationItem {
    final value = payload;
    return value is SearchHitPayloadChatConversation ? value.item : null;
  }

  MessageSearchItemView? get asChatMessageItem {
    final value = payload;
    return value is SearchHitPayloadChatMessage ? value.item : null;
  }

  PostSearchItemView? get asContentPostItem {
    final value = payload;
    return value is SearchHitPayloadContentPost ? value.item : null;
  }

  SearchUserProfileHitView? get asUserProfileItem {
    final value = payload;
    return value is SearchHitPayloadUserProfile ? value.item : null;
  }

  CircleSearchHitViewData? get asCircleCircleItem {
    final value = payload;
    return value is SearchHitPayloadCircleCircle ? value.item : null;
  }

  CircleSearchHitViewData? get asCircleGroupItem {
    final value = payload;
    return value is SearchHitPayloadCircleGroup ? value.item : null;
  }

  SearchEntityHomepageHitView? get asEntityHomepageItem {
    final value = payload;
    return value is SearchHitPayloadEntityHomepage ? value.item : null;
  }

  SearchLocationPlaceHitView? get asLocationPlaceItem {
    final value = payload;
    return value is SearchHitPayloadLocationPlace ? value.item : null;
  }

  LocationPoi? get asLocationPoiItem {
    final value = payload;
    return value is SearchHitPayloadLocationPoi ? value.item : null;
  }

  SocialRelationSearchItemViewData? get asSocialRelationItem {
    final value = payload;
    return value is SearchHitPayloadSocialRelation ? value.item : null;
  }
}

String? _normalize(String? value) {
  final normalized = value?.trim().toLowerCase();
  if (normalized == null || normalized.isEmpty) {
    return null;
  }
  return normalized;
}

String? _normalizeConversationType(String? value) {
  final normalized = _normalize(value);
  if (normalized == null) {
    return null;
  }
  return SearchConversationType.fromWire(normalized)?.wireValue;
}

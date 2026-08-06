import 'package:quwoquan_app/service/search_service/search/search_index_view/application/generated/search_execution_policy.g.dart'
    show SearchContractDefaults;
import 'package:quwoquan_app/service/circle_service/circle_management/circle/application/public/circle_search_hit_views.dart';
import 'package:quwoquan_app/service/integration_service/external_integration/location/application/public/search_location_place_hit_view.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_search_item_view/application/public/search_entity_homepage_hit_view.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/post_search_item_view.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/search_hit_payload.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/search_local_hit_views.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/search_query_contract.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/search_execution_values.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/search_user_profile_hit_view.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/social_relation_search_item_view_data.dart';
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

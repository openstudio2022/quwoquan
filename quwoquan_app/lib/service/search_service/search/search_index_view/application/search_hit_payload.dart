import 'package:quwoquan_app/service/circle_service/circle_management/circle/application/public/circle_search_hit_views.dart';
import 'package:quwoquan_app/service/integration_service/external_integration/location/application/public/search_location_place_hit_view.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_search_item_view/application/public/search_entity_homepage_hit_view.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/post_search_item_view.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/search_local_hit_views.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/search_user_profile_hit_view.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/social_relation_search_item_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show LocationPoi;

/// 全局搜索 [SearchHit] 的具名载荷（sealed），避免跨层持匿名 Map 作为业务状态。
sealed class SearchHitPayload {
  const SearchHitPayload();
}

final class SearchHitPayloadEmpty extends SearchHitPayload {
  const SearchHitPayloadEmpty();
}

/// 聊天联系人命中（与 [ChatContactSearchItemViewData] 同源）。
final class SearchHitPayloadChatContact extends SearchHitPayload {
  const SearchHitPayloadChatContact(this.item);

  final ChatContactSearchItemViewData item;
}

final class SearchHitPayloadChatConversation extends SearchHitPayload {
  const SearchHitPayloadChatConversation(this.item);

  final ConversationSearchItemView item;
}

final class SearchHitPayloadChatMessage extends SearchHitPayload {
  const SearchHitPayloadChatMessage(this.item);

  final MessageSearchItemView item;
}

/// Canonical Search 内容帖子命中。
final class SearchHitPayloadContentPost extends SearchHitPayload {
  const SearchHitPayloadContentPost(this.item);

  final PostSearchItemView item;
}

final class SearchHitPayloadUserProfile extends SearchHitPayload {
  const SearchHitPayloadUserProfile(this.item);

  final SearchUserProfileHitView item;
}

/// 圈子「圈子」命中（与 [CircleSearchHitViewData] 同源）。
final class SearchHitPayloadCircleCircle extends SearchHitPayload {
  const SearchHitPayloadCircleCircle(this.item);

  final CircleSearchHitViewData item;
}

final class SearchHitPayloadCircleGroup extends SearchHitPayload {
  const SearchHitPayloadCircleGroup(this.item);

  final CircleSearchHitViewData item;
}

final class SearchHitPayloadEntityHomepage extends SearchHitPayload {
  const SearchHitPayloadEntityHomepage(this.item);

  final SearchEntityHomepageHitView item;
}

final class SearchHitPayloadLocationPlace extends SearchHitPayload {
  const SearchHitPayloadLocationPlace(this.item);

  final SearchLocationPlaceHitView item;
}

final class SearchHitPayloadLocationPoi extends SearchHitPayload {
  const SearchHitPayloadLocationPoi(this.item);

  final LocationPoi item;
}

final class SearchHitPayloadSocialRelation extends SearchHitPayload {
  const SearchHitPayloadSocialRelation(this.item);

  final SocialRelationSearchItemViewData item;
}

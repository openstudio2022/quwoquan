import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/core/models/search_models.dart';

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

/// Canonical Search 用户命中。用户检索只承载公开资料摘要；头像当前未进入
/// SearchIndexView，页面使用语义化人物图标而不伪造头像。
final class SearchUserProfileHitView {
  const SearchUserProfileHitView({
    required this.userId,
    required this.displayName,
    this.bio,
    this.connectionState = 'unconnected',
    this.intersectionReason,
  });

  final String userId;
  final String displayName;
  final String? bio;
  final String connectionState;
  final CanonicalSearchIntersectionReason? intersectionReason;
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

final class SearchEntityHomepageHitView {
  const SearchEntityHomepageHitView({
    required this.homepageId,
    required this.name,
    this.subtitle,
    this.placeName,
    this.address,
    this.followerCount = 0,
    this.contentCount = 0,
  });

  final String homepageId;
  final String name;
  final String? subtitle;
  final String? placeName;
  final String? address;
  final int followerCount;
  final int contentCount;
}

final class SearchHitPayloadEntityHomepage extends SearchHitPayload {
  const SearchHitPayloadEntityHomepage(this.item);

  final SearchEntityHomepageHitView item;
}

final class SearchLocationPlaceHitView {
  const SearchLocationPlaceHitView({
    required this.placeId,
    required this.name,
    this.address,
  });

  final String placeId;
  final String name;
  final String? address;
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

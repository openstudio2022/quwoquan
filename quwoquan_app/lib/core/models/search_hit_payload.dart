import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/core/models/search_models.dart';

/// 全局搜索 [SearchHit] 的具名载荷（sealed），避免跨层持匿名 Map 作为业务状态。
///
/// 通用 wire 边界使用 [SearchHitPayloadWireMap]；与 wire 对齐的帖子/圈子命中优先用 codegen 视图类型。
/// 序列化见各分支 [toWireMap]（仅边界/观测/助手工具）。
sealed class SearchHitPayload {
  const SearchHitPayload();

  /// 可编码 wire Map，仅供 transport/观测兼容边界；新业务消费必须增加具名 payload。
  Map<String, Object?> toWireMap();
}

final class SearchHitPayloadEmpty extends SearchHitPayload {
  const SearchHitPayloadEmpty();

  @override
  Map<String, Object?> toWireMap() => const <String, Object?>{};
}

/// 仅供 transport/fixture 边界保留；生产 Remote adapter 不允许把该类型传入 UI。
final class SearchHitPayloadWireMap extends SearchHitPayload {
  const SearchHitPayloadWireMap([Map<String, Object?>? map])
    : map = map ?? const <String, Object?>{};

  final Map<String, Object?> map;

  @override
  Map<String, Object?> toWireMap() => map;
}

/// 聊天联系人命中（与 [ChatContactSearchItemDto] 同源）。
final class SearchHitPayloadChatContact extends SearchHitPayload {
  const SearchHitPayloadChatContact(this.item);

  final ChatContactSearchItemDto item;

  @override
  Map<String, Object?> toWireMap() => item.toMap();
}

final class SearchHitPayloadChatConversation extends SearchHitPayload {
  const SearchHitPayloadChatConversation(this.item);

  final ConversationSearchItemView item;

  @override
  Map<String, Object?> toWireMap() => item.toMap();
}

final class SearchHitPayloadChatMessage extends SearchHitPayload {
  const SearchHitPayloadChatMessage(this.item);

  final MessageSearchItemView item;

  @override
  Map<String, Object?> toWireMap() => item.toMap();
}

/// Canonical Search 内容帖子命中。
final class SearchHitPayloadContentPost extends SearchHitPayload {
  const SearchHitPayloadContentPost(this.item);

  final PostSearchItemView item;

  @override
  Map<String, Object?> toWireMap() => postSearchItemViewToSearchHitWire(item);
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
  final IntersectionReason? intersectionReason;
}

final class SearchHitPayloadUserProfile extends SearchHitPayload {
  const SearchHitPayloadUserProfile(this.item);

  final SearchUserProfileHitView item;

  @override
  Map<String, Object?> toWireMap() => <String, Object?>{
    'userId': item.userId,
    'displayName': item.displayName,
    'bio': ?item.bio,
    'connectionState': item.connectionState,
    if (item.intersectionReason case final reason?)
      'intersectionReason': reason.toMap(),
  };
}

/// 圈子「圈子」命中（与 [CircleSearchItemView] 同源）。
final class SearchHitPayloadCircleCircle extends SearchHitPayload {
  const SearchHitPayloadCircleCircle(this.item);

  final CircleSearchItemView item;

  @override
  Map<String, Object?> toWireMap() =>
      Map<String, Object?>.from(item.toSearchHitPayload());
}

final class SearchHitPayloadCircleGroup extends SearchHitPayload {
  const SearchHitPayloadCircleGroup(this.item);

  final CircleSearchItemView item;

  @override
  Map<String, Object?> toWireMap() =>
      Map<String, Object?>.from(item.toSearchHitPayload());
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

  @override
  Map<String, Object?> toWireMap() => <String, Object?>{
    'homepageId': item.homepageId,
    'name': item.name,
    'subtitle': ?item.subtitle,
    'placeName': ?item.placeName,
    'address': ?item.address,
    'followerCount': item.followerCount,
    'contentCount': item.contentCount,
  };
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

  @override
  Map<String, Object?> toWireMap() => <String, Object?>{
    'placeId': item.placeId,
    'name': item.name,
    'address': ?item.address,
  };
}

final class SearchHitPayloadLocationPoi extends SearchHitPayload {
  const SearchHitPayloadLocationPoi(this.item);

  final LocationPoiDto item;

  @override
  Map<String, Object?> toWireMap() => Map<String, Object?>.from(item.toMap());
}

final class SearchHitPayloadSocialRelation extends SearchHitPayload {
  const SearchHitPayloadSocialRelation(this.item);

  final SocialRelationSearchItemView item;

  @override
  Map<String, Object?> toWireMap() => <String, Object?>{
    'subAccountId': item.subAccountId,
    'username': item.username,
    'displayName': item.displayName,
    'avatarUrl': ?item.avatarUrl,
    'avatarVersion': item.avatarVersion,
    'headline': ?item.headline,
    'chatAvailable': item.chatAvailable,
    'relationshipCapability': <String, Object?>{
      'relationState': item.relationshipCapability.relationState,
      'canFollow': item.relationshipCapability.canFollow,
      'canUnfollow': item.relationshipCapability.canUnfollow,
      'canOpenConversation': item.relationshipCapability.canOpenConversation,
      'canStartVoiceCall': item.relationshipCapability.canStartVoiceCall,
      'canStartVideoCall': item.relationshipCapability.canStartVideoCall,
    },
  };
}

/// SearchHit 的序列化边界；业务消费禁止通过该 Map 回转内容 DTO。
Map<String, Object?> postSearchItemViewToSearchHitWire(
  PostSearchItemView item,
) {
  return <String, Object?>{
    'postId': item.postId,
    'contentType': item.contentType,
    'contentIdentity': item.contentIdentity,
    'title': item.title,
    'summary': item.summary,
    'coverUrl': item.coverUrl,
    'authorId': item.authorId,
    'authorDisplayName': item.authorDisplayName,
    'authorAvatarUrl': item.authorAvatarUrl,
    'categoryId': item.categoryId,
    'subCategory': item.subCategory,
    'likeCount': item.likeCount,
    'highlightText': item.highlightText,
    'matchedField': item.matchedField,
    'publishedAt': item.publishedAt?.toIso8601String(),
  };
}

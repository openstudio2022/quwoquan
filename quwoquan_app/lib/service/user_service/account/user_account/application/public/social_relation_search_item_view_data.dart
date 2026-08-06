import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/relationship_capability_repository.dart';

/// UserAccount 社交关系搜索结果的公开 App 投影。
class SocialRelationSearchItemViewData {
  const SocialRelationSearchItemViewData({
    required this.personaId,
    required this.userHandle,
    required this.displayName,
    this.avatarUrl,
    this.avatarVersion = 0,
    this.headline,
    required this.chatAvailable,
    required this.relationshipCapability,
  });

  final String personaId;
  final String userHandle;
  final String displayName;
  final String? avatarUrl;
  final int avatarVersion;
  final String? headline;
  final bool chatAvailable;
  final RelationshipCapabilityViewData relationshipCapability;
}

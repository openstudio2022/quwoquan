import 'package:quwoquan_app/runtime/transport/media/avatar_image_url.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/social_relation_search_item_view_data.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/relationship_capability_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    as cloud_contracts;

/// UserAccount wire projection 到 Persona 公开 App 投影的 adapter mapper。
abstract final class SocialRelationSearchItemViewMapper {
  static SocialRelationSearchItemViewData fromWire(
    cloud_contracts.SocialRelationSearchItemView projection,
  ) {
    final personaId = projection.personaId;
    final displayName = projection.displayName.isNotEmpty
        ? projection.displayName
        : personaId;
    final capView = RelationshipCapabilityViewData.fromWire(
      projection.relationshipCapability,
    );
    return SocialRelationSearchItemViewData(
      personaId: personaId,
      userHandle: projection.userHandle,
      displayName: displayName,
      avatarUrl: projection.avatarUrl == null
          ? null
          : resolveAvatarImageUrl(projection.avatarUrl, avatarVersion: 0),
      avatarVersion: 0,
      headline: projection.headline,
      chatAvailable: projection.chatAvailable || capView.canOpenConversation,
      relationshipCapability: capView,
    );
  }
}

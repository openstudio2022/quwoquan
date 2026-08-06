import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/gathering_board_ports.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart' as cloud;

GatheringBoardChatSlice gatheringBoardChatFromWire(
  cloud.GatheringChatBoardSlice wire,
) {
  final access = wire.access;
  return GatheringBoardChatSlice(
    access: GatheringBoardChatAccessSummary(
      gatheringId: access.gatheringId,
      conversationId: access.conversationId,
      accessMode: access.accessMode == cloud.ConversationAccessMode.readOnly
          ? GatheringBoardAccessMode.readOnly
          : GatheringBoardAccessMode.active,
      viewerRole: access.viewerRole,
      canPost: access.canPost,
      statusLabel: access.postingPolicy.wireName,
    ),
    pinnedAnnouncement: wire.pinnedAnnouncement == null
        ? null
        : GatheringBoardPinnedAnnouncement(
            content: wire.pinnedAnnouncement!.content,
            updatedBy: wire.pinnedAnnouncement!.updatedBy,
            updatedAt: wire.pinnedAnnouncement!.updatedAt,
          ),
    assets: wire.assets
        .map(
          (asset) => GatheringBoardAssetIndexItem(
            messageId: asset.messageId,
            mediaAssetId: asset.mediaAssetId,
            kind: _assetKindFromWire(asset.messageType),
            displayLabel: asset.messageType,
            createdAt: asset.createdAt,
          ),
        )
        .toList(growable: false),
  );
}

GatheringBoardAssetKind _assetKindFromWire(String messageType) {
  final normalized = messageType.trim().toLowerCase();
  if (normalized.contains('video')) {
    return GatheringBoardAssetKind.video;
  }
  if (normalized.contains('file')) {
    return GatheringBoardAssetKind.file;
  }
  return GatheringBoardAssetKind.image;
}

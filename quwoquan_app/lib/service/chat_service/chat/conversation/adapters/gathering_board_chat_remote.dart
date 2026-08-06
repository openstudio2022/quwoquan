import 'package:quwoquan_app/runtime/transport/generated/chat/chat_request_page_ids.g.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/adapters/gathering_board_wire_codec.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/gathering_board_ports.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef GatheringBoardChatInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// Chat owner slice for the gathering activity board.
final class RemoteGatheringBoardChatReader implements GatheringBoardChatReader {
  const RemoteGatheringBoardChatReader({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final GatheringBoardChatInvocationContextFactory invocationContext;

  @override
  Future<GatheringBoardChatSlice> loadChat(String conversationId) async {
    final normalized = conversationId.trim();
    if (normalized.isEmpty) {
      throw ArgumentError.value(
        conversationId,
        'conversationId',
        'must not be blank',
      );
    }
    final wire = await client.chatConversationGetGatheringChatBoard(
      GatheringChatBoardQuery(conversationId: normalized),
      context: invocationContext(ChatRequestPageIds.getGatheringChatBoard),
    );
    return gatheringBoardChatFromWire(wire);
  }
}

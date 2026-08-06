import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/gathering_board_ports.dart';

/// 以 Chat contextual conversation 为唯一入口组合活动看板。
///
/// Chat slice 先给出 canonical gatheringId，再由 Circle reader 读取 owner
/// 事实。任何 conversation/gathering identity 漂移都 fail-closed；组合器不
/// 猜测路由参数，也不复制任一 owner 的写状态。
final class GatheringBoardComposer implements GatheringBoardQuery {
  const GatheringBoardComposer({
    required this.chatReader,
    required this.circleReader,
  });

  final GatheringBoardChatReader chatReader;
  final GatheringBoardCircleReader circleReader;

  @override
  Future<GatheringBoardSnapshot> load(
    GatheringBoardQueryRequest request,
  ) async {
    final conversationId = request.conversationId.trim();
    if (conversationId.isEmpty) {
      throw ArgumentError.value(
        request.conversationId,
        'conversationId',
        'must not be blank',
      );
    }

    final chat = await chatReader.loadChat(conversationId);
    final chatConversationId = chat.access.conversationId.trim();
    final gatheringId = chat.access.gatheringId.trim();
    if (chatConversationId != conversationId || gatheringId.isEmpty) {
      throw StateError('gathering board chat identity mismatch');
    }

    final circle = await circleReader.loadCircle(gatheringId);
    if (circle.activity.gatheringId.trim() != gatheringId) {
      throw StateError('gathering board circle identity mismatch');
    }

    return GatheringBoardSnapshot(
      activity: circle.activity,
      participation: circle.participation,
      plan: circle.plan,
      chat: chat,
      mapCapability: circle.mapCapability,
      calendarCapability: circle.calendarCapability,
    );
  }
}

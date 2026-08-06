import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// ConversationUserState 对象的公开命令端口。
abstract interface class ConversationUserStateCommandWriter {
  Future<ConversationUserStateCommandAck> markMessageRead(
    ChatMarkConversationMessageReadCommand command, {
    required String idempotencyKey,
  });

  Future<ConversationUserStateCommandAck> updateConversationSettings(
    ChatUpdateConversationSettingsCommand command, {
    required String idempotencyKey,
  });
}

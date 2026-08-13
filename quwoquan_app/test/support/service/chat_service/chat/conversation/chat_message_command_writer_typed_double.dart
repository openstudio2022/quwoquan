import 'package:quwoquan_cloud_contracts/chat_contracts.dart';

import 'chat_state_seed_builder.dart';
import 'conversation_state_typed_double.dart';

/// local_contract Message command 薄适配器。
///
/// 消息序列、幂等回执与会话列表统一写入 [InMemoryChatStateEngine]，不维护第二份状态。
final class InMemoryChatMessageCommandWriter
    implements ChatMessageCommandWriter {
  InMemoryChatMessageCommandWriter({
    InMemoryChatStateEngine? engine,
    ChatStateSeed? seed,
  }) : _engine =
           engine ??
           InMemoryChatStateEngine(seed: seed ?? minimalChatStateSeed());

  final InMemoryChatStateEngine _engine;

  @override
  Future<ChatSendMessageResult> sendMessage(
    ChatSendMessageCommand command,
  ) async => _engine.sendMessage(command);
}

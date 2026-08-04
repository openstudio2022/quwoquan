import 'package:quwoquan_cloud_contracts/chat_contracts.dart';

import '../../../cloud_services/object_doubles/object_scenario_seed_reader.dart';
import '../conversation/conversation_state_typed_double.dart';

/// local_contract Message command 薄适配器。
///
/// 消息序列、幂等回执与会话列表统一写入 [AlphaChatStateEngine]，不维护第二份状态。
final class AlphaChatMessageCommandWriter implements ChatMessageCommandWriter {
  AlphaChatMessageCommandWriter({
    AlphaChatStateEngine? engine,
    ObjectScenarioSeedReader? fixtures,
  }) : _engine = engine ?? AlphaChatStateEngine(fixtures: fixtures);

  final AlphaChatStateEngine _engine;

  @override
  Future<ChatSendMessageResult> sendMessage(
    ChatSendMessageCommand command,
  ) async => _engine.sendMessage(command);
}

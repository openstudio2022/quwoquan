import 'package:quwoquan_cloud_contracts/chat_contracts.dart';
import 'package:quwoquan_cloud_mock/src/chat/alpha_chat_state_engine.dart';
import 'package:quwoquan_cloud_mock/src/generated/alpha_fixture_bundle.g.dart';

/// Alpha-only Message command 薄适配器。
///
/// 消息序列、幂等回执与会话列表统一写入 [AlphaChatStateEngine]，不维护第二份状态。
final class AlphaChatMessageCommandWriter implements ChatMessageCommandWriter {
  AlphaChatMessageCommandWriter({
    AlphaChatStateEngine? engine,
    AlphaFixtureBundle bundle = alphaFixtureBundle,
  }) : _engine = engine ?? AlphaChatStateEngine(bundle: bundle);

  final AlphaChatStateEngine _engine;

  @override
  Future<ChatSendMessageResult> sendMessage(
    ChatSendMessageCommand command,
  ) async => _engine.sendMessage(command);
}

import 'chat_operation_contracts.g.dart';

export 'chat_operation_contracts.g.dart';

abstract interface class ChatMessageHomeQuery {
  Future<MessageHomePageSlice> listMessageHome(ChatListMessageHomeQuery query);
}

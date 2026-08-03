import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

abstract interface class AppMessageQuery {
  Future<AppMessageInboxSlice> listAppMessages(ListAppMessagesQuery query);

  Future<AppMessage> getAppMessage(GetAppMessageQuery query);

  Future<AppMessageUnreadCountSlice> getUnreadCount(
    GetAppMessageUnreadCountQuery query,
  );
}

abstract interface class AppMessageCommandWriter {
  Future<AppMessage> acknowledge(AckAppMessageCommand command);

  Future<AppMessage> markRead(ReadAppMessageCommand command);
}

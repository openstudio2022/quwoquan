import 'app_message.dart';

final class AppMessageInboxSlice {
  AppMessageInboxSlice({required Iterable<AppMessage> items, this.nextCursor})
    : items = List<AppMessage>.unmodifiable(items);

  final List<AppMessage> items;
  final String? nextCursor;
}

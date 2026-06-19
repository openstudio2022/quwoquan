import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/models/chat_list_item_view_model.dart';
import 'package:quwoquan_app/ui/chat/providers/chat_inbox_provider.dart';

const List<String> messageHomeFilters = <String>[
  'all',
  'unread',
  'group',
  'direct',
  'notification',
];

final messageHomeRowsProvider =
    FutureProvider.family<List<ChatListItemViewModel>, String>((
      ref,
      filter,
    ) async {
      final repo = ref.watch(chatRepositoryProvider);
      final rows = await repo.listMessageHome(filter: filter, limit: 100);
      return rows.map(ChatListItemViewModel.fromMessageHomeDto).toList();
    });

int totalUnreadMessages(Iterable<ChatListItemViewModel> rows) {
  return rows.fold<int>(0, (total, row) => total + row.unreadCount);
}

final messageHomeUnreadBadgeCountProvider = Provider<int?>((ref) {
  final unreadRows = ref.watch(messageHomeRowsProvider('unread'));
  return unreadRows.maybeWhen(data: totalUnreadMessages, orElse: () => null);
});

void refreshMessageReadState(WidgetRef ref, String conversationId) {
  ref.read(chatInboxListProvider.notifier).markConversationRead(conversationId);
  for (final filter in messageHomeFilters) {
    ref.invalidate(messageHomeRowsProvider(filter));
  }
}

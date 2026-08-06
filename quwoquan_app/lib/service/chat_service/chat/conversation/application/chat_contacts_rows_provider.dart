import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/domain/chat_contacts_row.dart';

/// 联系人二级 Tab 下的商用聚合行。
///
/// 业务事实来自云端 ContactHomeProjection；App 不再本地拼 contacts/circles/groups。
final chatContactsRowsForSubTabProvider =
    FutureProvider.family<List<ChatContactsRow>, String>((ref, subTab) async {
      final repo = ref.watch(chatContactRepositoryProvider);
      final rows = await repo.listContactHome(
        filter: _contactHomeFilterForSubTab(subTab),
        limit: 500,
      );
      return rows.map(chatContactsRowFromContactHomeDto).toList();
    });

String _contactHomeFilterForSubTab(String subTab) {
  return switch (subTab) {
    ChatText.contactsTabMutualFollow => 'mutual',
    ChatText.contactsTabCircles => 'circle',
    ChatText.contactsTabGroups => 'group',
    _ => 'all',
  };
}

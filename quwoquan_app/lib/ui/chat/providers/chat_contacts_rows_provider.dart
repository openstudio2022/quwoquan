import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/chat/models/chat_contacts_row.dart';

/// 联系人二级 Tab 下的列表行（ChatRepository + 圈子/趣群占位）。
final chatContactsRowsForSubTabProvider =
    FutureProvider.family<List<ChatContactsRow>, String>((ref, subTab) async {
      final repo = ref.watch(chatRepositoryProvider);
      if (subTab == UITextConstants.contactsTabCircles) {
        final maps = await repo.listContactTabCircles(limit: 500);
        return maps.map(ChatContactsRow.fromContactTabCircleMap).toList();
      }
      if (subTab == UITextConstants.contactsTabFunGroup) {
        final maps = await repo.listContactTabFunGroups(limit: 500);
        return maps.map(ChatContactsRow.fromContactTabFunGroupMap).toList();
      }
      final contacts = await repo.listContacts(limit: 500);
      var rows = contacts.map(ChatContactsRow.fromContactDto).toList();
      if (subTab == UITextConstants.contactsTabSameInterest) {
        rows = rows.where((r) => r.isFriend).toList();
      }
      return rows;
    });

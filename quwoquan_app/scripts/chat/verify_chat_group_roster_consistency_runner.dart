// ignore_for_file: avoid_print

import 'package:quwoquan_app/cloud/services/chat/mock/chat_mock_data.dart';

void main() {
  final violations = <String>[];

  for (final conv in ChatMockData.conversations) {
    if (conv['type']?.toString() != 'group') {
      continue;
    }
    final id = conv['id']?.toString() ?? '';
    if (id.isEmpty) {
      continue;
    }
    final declared = conv['memberCount'];
    final memberCount = declared is int
        ? declared
        : int.tryParse('$declared') ?? -1;
    final roster = ChatMockData.membersFor(id);
    if (memberCount != roster.length) {
      violations.add(
        'ChatMockData $id: memberCount=$memberCount roster=${roster.length}',
      );
    }
  }

  if (violations.isNotEmpty) {
    print('verify_chat_group_roster_consistency (mock): FAIL');
    for (final item in violations) {
      print('  - $item');
    }
    // ignore: avoid_dynamic_calls
    throw StateError('mock roster consistency failed');
  }
  print('verify_chat_group_roster_consistency (mock): OK');
}

// ignore_for_file: avoid_print

import 'package:quwoquan_cloud_mock/chat_fixture.dart';

void main() {
  final violations = <String>[];
  final engine = AlphaChatStateEngine();

  for (final conv in engine.conversationSeeds) {
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
    final roster = engine.membersFor(id);
    if (memberCount != roster.length) {
      violations.add(
        'AlphaChatStateEngine $id: '
        'memberCount=$memberCount roster=${roster.length}',
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

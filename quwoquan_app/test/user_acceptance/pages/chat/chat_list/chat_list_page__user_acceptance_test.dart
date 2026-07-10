import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

File _repoFile(String path) {
  final direct = File(path);
  if (direct.existsSync()) {
    return direct;
  }
  return File('../$path');
}

void main() {
  test('chatList page coverage evidence is declared', () {
    const surfaceId = 'chatList';
    const owner = 'chat';
    const routeId = 'chat';
    const sourceEvidence = <String>[
    'quwoquan_app/test/local_contract/ui/chat/widgets/chat_page_widget__local_contract_test.dart',
    'quwoquan_app/test/user_acceptance/journeys/chat/chat_conversation_list_journey__user_acceptance_test.dart',
  ];
    const apiEvidence = <String>[
    'quwoquan_service/services/chat-service/tests/api_integration/group_lifecycle_contract__api_integration_test.go',
    'quwoquan_service/services/chat-service/tests/api_integration/message_sync_contract__api_integration_test.go',
  ];
    const requiredCaseIds = <String>[
    'user_acceptance.page.chatList.load_success',
    'user_acceptance.page.chatList.empty_permission_error',
    'user_acceptance.page.chatList.primary_cta',
    'user_acceptance.page.chatList.trace_context',
  ];

    expect(surfaceId, isNotEmpty);
    expect(owner, isNotEmpty);
    expect(routeId, isNotEmpty);
    expect(sourceEvidence, isNotEmpty);
    expect(apiEvidence, isNotEmpty);
    expect(requiredCaseIds, containsAll(<String>[
      'user_acceptance.page.$surfaceId.load_success',
      'user_acceptance.page.$surfaceId.empty_permission_error',
      'user_acceptance.page.$surfaceId.primary_cta',
      'user_acceptance.page.$surfaceId.trace_context',
    ]));

    for (final path in <String>[...sourceEvidence, ...apiEvidence]) {
      expect(_repoFile(path).existsSync(), isTrue, reason: path);
    }
  });
}

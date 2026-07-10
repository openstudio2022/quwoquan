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
  test('assistantHistory page coverage evidence is declared', () {
    const surfaceId = 'assistantHistory';
    const owner = 'assistant';
    const routeId = 'chatDetail';
    const sourceEvidence = <String>[
    'quwoquan_app/test/local_contract/ui/assistant/contract/assistant_message_history_contract__local_contract_test.dart',
    'quwoquan_app/test/user_acceptance/journeys/chat/chat_assistant_journey__user_acceptance_test.dart',
  ];
    const apiEvidence = <String>[
    'quwoquan_app/test/api_integration/cloud/assistant/assistant_skill_comparison__api_integration_test.dart',
    'quwoquan_service/services/assistant-service/tests/api_integration/assistant_mentioned_chat_integration__api_integration_test.go',
  ];
    const requiredCaseIds = <String>[
    'user_acceptance.page.assistantHistory.load_success',
    'user_acceptance.page.assistantHistory.empty_permission_error',
    'user_acceptance.page.assistantHistory.primary_cta',
    'user_acceptance.page.assistantHistory.trace_context',
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

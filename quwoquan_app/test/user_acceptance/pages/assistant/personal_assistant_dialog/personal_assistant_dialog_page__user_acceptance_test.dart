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
  test('personalAssistantDialog page coverage evidence is declared', () {
    const surfaceId = 'personalAssistantDialog';
    const owner = 'assistant';
    const routeId = 'assistantPersonal';
    const sourceEvidence = <String>[
    'quwoquan_app/test/user_acceptance/journeys/chat/chat_assistant_journey__user_acceptance_test.dart',
    'quwoquan_app/test/local_contract/ui/assistant/personal_assistant_stream_controller__local_contract_test.dart',
  ];
    const apiEvidence = <String>[
    'quwoquan_app/test/api_integration/cloud/assistant/assistant_scenario_simulator__api_integration_test.dart',
    'quwoquan_service/services/assistant-service/tests/api_integration/assistant_mentioned_chat_integration__api_integration_test.go',
  ];
    const requiredCaseIds = <String>[
    'user_acceptance.page.personalAssistantDialog.load_success',
    'user_acceptance.page.personalAssistantDialog.empty_permission_error',
    'user_acceptance.page.personalAssistantDialog.primary_cta',
    'user_acceptance.page.personalAssistantDialog.trace_context',
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

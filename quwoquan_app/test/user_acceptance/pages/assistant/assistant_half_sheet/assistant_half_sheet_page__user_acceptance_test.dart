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
  test('assistantHalfSheet page coverage evidence is declared', () {
    const surfaceId = 'assistantHalfSheet';
    const owner = 'assistant';
    const routeId = 'assistantPersonal';
    const sourceEvidence = <String>[
    'quwoquan_app/test/local_contract/ui/assistant/widgets/assistant_half_sheet_personalization_provider__local_contract_test.dart',
    'quwoquan_app/test/local_contract/ui/chat/widgets/chat_assistant_ui_widget__local_contract_test.dart',
  ];
    const apiEvidence = <String>[
    'quwoquan_app/test/api_integration/cloud/assistant/assistant_scenario_simulator__api_integration_test.dart',
    'quwoquan_service/services/assistant-service/tests/api_integration/assistant_mentioned_chat_integration__api_integration_test.go',
  ];
    const requiredCaseIds = <String>[
    'user_acceptance.page.assistantHalfSheet.load_success',
    'user_acceptance.page.assistantHalfSheet.empty_permission_error',
    'user_acceptance.page.assistantHalfSheet.primary_cta',
    'user_acceptance.page.assistantHalfSheet.trace_context',
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

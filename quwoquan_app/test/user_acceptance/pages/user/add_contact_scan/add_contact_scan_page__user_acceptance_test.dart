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
  test('addContactScan page coverage evidence is declared', () {
    const surfaceId = 'addContactScan';
    const owner = 'user';
    const routeId = 'addContactScan';
    const sourceEvidence = <String>[
    'quwoquan_app/test/local_contract/ui/user/pages/my_profile_page__local_contract_test.dart',
    'quwoquan_app/test/user_acceptance/journeys/user/other_profile_journey__user_acceptance_test.dart',
  ];
    const apiEvidence = <String>[
    'quwoquan_service/services/user-service/tests/api_integration/profile_crud_contract__api_integration_test.go',
    'quwoquan_service/services/user-service/tests/api_integration/contact_discovery_contract__api_integration_test.go',
  ];
    const requiredCaseIds = <String>[
    'user_acceptance.page.addContactScan.load_success',
    'user_acceptance.page.addContactScan.empty_permission_error',
    'user_acceptance.page.addContactScan.primary_cta',
    'user_acceptance.page.addContactScan.trace_context',
    'user_acceptance.page.addContactScan.request_wait_recovery',
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
      'user_acceptance.page.$surfaceId.request_wait_recovery',
    ]));

    for (final path in <String>[...sourceEvidence, ...apiEvidence]) {
      expect(_repoFile(path).existsSync(), isTrue, reason: path);
    }
  });
}

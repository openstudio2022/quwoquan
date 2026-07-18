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
  test('globalSearchLanding page coverage evidence is declared', () {
    const surfaceId = 'globalSearchLanding';
    const owner = 'search';
    const routeId = 'globalSearch';
    const sourceEvidence = <String>[
    'quwoquan_app/test/local_contract/ui/search/pages/global_search_page_widget__local_contract_test.dart',
    'quwoquan_app/test/user_acceptance/journeys/search/cross_domain_search_journey__user_acceptance_test.dart',
  ];
    const apiEvidence = <String>[
    'quwoquan_service/services/search-service/tests/api_integration/search_contract__api_integration_test.go',
    'quwoquan_service/services/search-service/tests/api_integration/storage_ttl_contract__api_integration_test.go',
  ];
    const requiredCaseIds = <String>[
    'user_acceptance.page.globalSearchLanding.load_success',
    'user_acceptance.page.globalSearchLanding.empty_permission_error',
    'user_acceptance.page.globalSearchLanding.primary_cta',
    'user_acceptance.page.globalSearchLanding.trace_context',
    'user_acceptance.page.globalSearchLanding.request_wait_recovery',
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

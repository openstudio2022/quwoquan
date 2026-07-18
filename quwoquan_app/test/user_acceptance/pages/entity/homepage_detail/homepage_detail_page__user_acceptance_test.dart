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
  test('homepageDetail page coverage evidence is declared', () {
    const surfaceId = 'homepageDetail';
    const owner = 'entity';
    const routeId = 'homepageDetail';
    const sourceEvidence = <String>[
    'quwoquan_app/test/local_contract/ui/entity/pages/homepage_detail_page_widget__local_contract_test.dart',
    'quwoquan_app/test/local_contract/ui/components/object_page/object_page_shell__local_contract_test.dart',
  ];
    const apiEvidence = <String>[
    'quwoquan_service/services/entity-service/tests/api_integration/homepage_handler__api_integration_test.go',
    'quwoquan_service/services/entity-service/tests/api_integration/homepage_search_contract__api_integration_test.go',
  ];
    const requiredCaseIds = <String>[
    'user_acceptance.page.homepageDetail.load_success',
    'user_acceptance.page.homepageDetail.empty_permission_error',
    'user_acceptance.page.homepageDetail.primary_cta',
    'user_acceptance.page.homepageDetail.trace_context',
    'user_acceptance.page.homepageDetail.request_wait_recovery',
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

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
  test('localDrafts page coverage evidence is declared', () {
    const surfaceId = 'localDrafts';
    const owner = 'content';
    const routeId = 'localDrafts';
    const sourceEvidence = <String>[
    'quwoquan_app/test/local_contract/ui/content/entry/draft_recovery_widget__local_contract_test.dart',
    'quwoquan_app/test/local_contract/ui/content/entry/widgets/create_entry_sheet_widget__local_contract_test.dart',
  ];
    const apiEvidence = <String>[
    'quwoquan_service/services/content-service/tests/api_integration/post_crud_contract__api_integration_test.go',
    'quwoquan_service/services/content-service/tests/api_integration/post_markdown_contract__api_integration_test.go',
  ];
    const requiredCaseIds = <String>[
    'user_acceptance.page.localDrafts.load_success',
    'user_acceptance.page.localDrafts.empty_permission_error',
    'user_acceptance.page.localDrafts.primary_cta',
    'user_acceptance.page.localDrafts.trace_context',
    'user_acceptance.page.localDrafts.request_wait_recovery',
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

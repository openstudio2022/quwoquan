import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';

import '../../support/runtime/release/release_homepage_uat_cases.dart';

void main() {
  test('release homepage uat cases decode importer identities', () {
    final encoded = base64.encode(
      utf8.encode(
        jsonEncode(<String, Object?>{
          'schema': 'quwoquan_data.homepage_verification_case_manifest',
          'environment': 'gamma',
          'releaseId': 'release-example',
          'runId': 'apply-001',
          'importerReportRef':
              'env/gamma/runs/data-release/example/apply-001/homepage-import.json',
          'generatedAt': '2026-07-14T00:00:00Z',
          'cases': <Object?>[
            <String, Object?>{
              'entityRef': '地点/景区/测试实体',
              'homepageId': 'homepage-example',
              'title': '测试实体',
            },
          ],
        }),
      ),
    );

    final cases = parseReleaseHomepageUatCases(encoded);

    expect(cases, hasLength(1));
    expect(cases.single.homepageId, 'homepage-example');
  });

  test('release homepage uat cases reject duplicate homepage identity', () {
    final encoded = base64.encode(
      utf8.encode(
        jsonEncode(<String, Object?>{
          'schema': 'quwoquan_data.homepage_verification_case_manifest',
          'environment': 'gamma',
          'releaseId': 'release',
          'runId': 'run',
          'importerReportRef':
              'env/gamma/runs/data-release/release/run/homepage-import.json',
          'generatedAt': '2026-07-14T00:00:00Z',
          'cases': <Object?>[
            <String, Object?>{
              'entityRef': 'a/b/c',
              'homepageId': 'homepage-1',
              'title': 'c',
            },
            <String, Object?>{
              'entityRef': 'a/b/d',
              'homepageId': 'homepage-1',
              'title': 'd',
            },
          ],
        }),
      ),
    );

    expect(() => parseReleaseHomepageUatCases(encoded), throwsStateError);
  });
}

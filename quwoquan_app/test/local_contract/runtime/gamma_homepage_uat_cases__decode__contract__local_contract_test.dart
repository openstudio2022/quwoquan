import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';

import '../../support/runtime/release/gamma_homepage_uat_cases.dart';

void main() {
  test('gamma homepage uat cases decode release-bound importer identities', () {
    final encoded = base64.encode(
      utf8.encode(
        jsonEncode(<String, Object?>{
          'schema': 'quwoquan_data.homepage_verification_case_manifest',
          'environment': 'gamma',
          'releaseId':
              '20260714--travel-homepage-coverage--cn-zhejiang-sichuan--canary-002',
          'runId': 'apply-001',
          'importerReportRef':
              'env/gamma/runs/data-release/example/apply-001/homepage-import.json',
          'generatedAt': '2026-07-14T00:00:00Z',
          'cases': <Object?>[
            <String, Object?>{
              'entityRef': '地点/景区/普陀山',
              'homepageId': 'homepage-putuo',
              'title': '普陀山',
            },
          ],
        }),
      ),
    );

    final cases = parseGammaHomepageUatCases(encoded);

    expect(cases, hasLength(1));
    expect(cases.single.homepageId, 'homepage-putuo');
  });

  test('gamma homepage uat cases reject duplicate homepage identity', () {
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

    expect(() => parseGammaHomepageUatCases(encoded), throwsStateError);
  });
}

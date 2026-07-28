// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/spec.md#gwt-002
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/app/recovery/recovery_version_client.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/ops_api_metadata.g.dart';

void main() {
  test(
    'version client sends only platform and local version coordinates',
    () async {
      late Uri requested;
      final client = RecoveryVersionClient(
        client: MockClient((request) async {
          requested = request.url;
          return http.Response(
            '{"latestVersion":"1.8.2","latestBuild":"18201",'
            '"updateUrl":"https://cdn.quwoquan.com/downloads/android/latest.json",'
            '"recoveryUrl":"https://quwoquan.com/"}',
            200,
          );
        }),
      );

      final result = await client.fetch(
        baseUrl: 'https://api.quwoquan.com',
        platform: 'android',
        appVersion: '1.8.1',
        buildNumber: 18100,
      );

      expect(requested.path, OpsApiMetadata.getAppRecoveryVersionPath);
      expect(requested.queryParameters, <String, String>{
        'platform': 'android',
        'appVersion': '1.8.1',
        'buildNumber': '18100',
      });
      expect(result.latestBuild, 18201);
    },
  );

  test(
    'version client rejects non-https origin and expanded response',
    () async {
      final client = RecoveryVersionClient(
        client: MockClient(
          (_) async => http.Response(
            '{"latestVersion":"1.8.2","latestBuild":"18201",'
            '"updateUrl":"https://cdn.quwoquan.com/downloads/android/latest.json",'
            '"recoveryUrl":"https://quwoquan.com/",'
            '"diagnosticId":"forbidden"}',
            200,
          ),
        ),
      );
      await expectLater(
        client.fetch(
          baseUrl: 'http://api.quwoquan.com',
          platform: 'android',
          appVersion: '1.8.1',
          buildNumber: 18100,
        ),
        throwsFormatException,
      );
      await expectLater(
        client.fetch(
          baseUrl: 'https://api.quwoquan.com',
          platform: 'android',
          appVersion: '1.8.1',
          buildNumber: 18100,
        ),
        throwsFormatException,
      );
    },
  );
}

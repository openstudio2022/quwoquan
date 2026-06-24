import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/local_dev_https_trust.dart';

void main() {
  group('LocalDevHttpsTrust', () {
    test('installs only for Android non-release local HTTPS runtime', () {
      expect(
        LocalDevHttpsTrust.shouldInstallForRuntime(
          isReleaseMode: false,
          isAndroid: true,
          appRuntimeEnv: 'alpha',
          runtimeBases: const <String>[
            'https://localhost:17100',
            'https://alpha-image.quwoquan-env.test:17100',
          ],
        ),
        isTrue,
      );
      expect(
        LocalDevHttpsTrust.shouldInstallForRuntime(
          isReleaseMode: false,
          isAndroid: true,
          appRuntimeEnv: 'beta',
          runtimeBases: const <String>['https://beta-api.localhost:18000'],
        ),
        isTrue,
      );
    });

    test(
      'does not install for prod, release, non-Android, or cleartext bases',
      () {
        expect(
          LocalDevHttpsTrust.shouldInstallForRuntime(
            isReleaseMode: true,
            isAndroid: true,
            appRuntimeEnv: 'alpha',
            runtimeBases: const <String>['https://localhost:17100'],
          ),
          isFalse,
        );
        expect(
          LocalDevHttpsTrust.shouldInstallForRuntime(
            isReleaseMode: false,
            isAndroid: false,
            appRuntimeEnv: 'alpha',
            runtimeBases: const <String>['https://localhost:17100'],
          ),
          isFalse,
        );
        expect(
          LocalDevHttpsTrust.shouldInstallForRuntime(
            isReleaseMode: false,
            isAndroid: true,
            appRuntimeEnv: 'prod',
            runtimeBases: const <String>['https://118.31.239.122'],
          ),
          isFalse,
        );
        expect(
          LocalDevHttpsTrust.shouldInstallForRuntime(
            isReleaseMode: false,
            isAndroid: true,
            appRuntimeEnv: 'alpha',
            runtimeBases: const <String>['http://localhost:17100'],
          ),
          isFalse,
        );
      },
    );
  });
}

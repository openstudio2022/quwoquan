import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/platform/local_dev_https_trust.dart';

void main() {
  group('LocalDevHttpsTrust', () {
    test('installs for Android non-release when bases are local HTTPS plane', () {
      expect(
        LocalDevHttpsTrust.shouldInstallForRuntime(
          isReleaseMode: false,
          isAndroid: true,
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
          runtimeBases: const <String>['https://beta-api.localhost:18000'],
        ),
        isTrue,
      );
      // prod-sim: APP_RUNTIME_ENV may be prod, but *.localhost bases must install.
      expect(
        LocalDevHttpsTrust.shouldInstallForRuntime(
          isReleaseMode: false,
          isAndroid: true,
          appRuntimeEnv: 'prod',
          runtimeBases: const <String>['https://prod-image.localhost:20100'],
        ),
        isTrue,
      );
    });

    test('installs for iOS Simulator non-release local HTTPS bases', () {
      expect(
        LocalDevHttpsTrust.shouldInstallForRuntime(
          isReleaseMode: false,
          isAndroid: false,
          isIos: true,
          runtimeBases: const <String>['https://gamma-api.localhost:19000'],
        ),
        isTrue,
      );
      expect(
        LocalDevHttpsTrust.shouldInstallForRuntime(
          isReleaseMode: true,
          isAndroid: false,
          isIos: true,
          runtimeBases: const <String>['https://gamma-api.localhost:19000'],
        ),
        isFalse,
      );
    });

    test(
      'does not install for release, non-Android, public bases, or cleartext',
      () {
        expect(
          LocalDevHttpsTrust.shouldInstallForRuntime(
            isReleaseMode: true,
            isAndroid: true,
            runtimeBases: const <String>['https://localhost:17100'],
          ),
          isFalse,
        );
        expect(
          LocalDevHttpsTrust.shouldInstallForRuntime(
            isReleaseMode: false,
            isAndroid: false,
            runtimeBases: const <String>['https://localhost:17100'],
          ),
          isFalse,
        );
        expect(
          LocalDevHttpsTrust.shouldInstallForRuntime(
            isReleaseMode: false,
            isAndroid: true,
            appRuntimeEnv: 'prod',
            runtimeBases: const <String>['https://118.31.239.122:19100'],
          ),
          isFalse,
        );
        expect(
          LocalDevHttpsTrust.shouldInstallForRuntime(
            isReleaseMode: false,
            isAndroid: true,
            runtimeBases: const <String>['http://localhost:17100'],
          ),
          isFalse,
        );
        // Canonical env.test alone is not the Android local transport plane.
        expect(
          LocalDevHttpsTrust.shouldInstallForRuntime(
            isReleaseMode: false,
            isAndroid: true,
            runtimeBases: const <String>[
              'https://alpha-api.quwoquan-env.test:17000',
              'https://alpha-image.quwoquan-env.test:17100',
            ],
          ),
          isFalse,
        );
      },
    );

    test('rejects placeholder local CA subject marker', () {
      final placeholderPem = utf8.encode(
        '-----BEGIN CERTIFICATE-----\n'
        'subject=CN=quwoquan-local-debug-placeholder\n'
        '-----END CERTIFICATE-----\n',
      );
      expect(
        LocalDevHttpsTrust.isPlaceholderLocalEnvCertificate(
          Uint8List.fromList(placeholderPem),
        ),
        isTrue,
      );
      expect(
        LocalDevHttpsTrust.isPlaceholderLocalEnvCertificate(
          Uint8List.fromList(utf8.encode('real-ca-without-marker')),
        ),
        isFalse,
      );
    });

    test('classifies local HTTPS transport bases by host plane', () {
      expect(
        LocalDevHttpsTrust.isLocalHttpsTransportBase(
          'https://gamma-image.localhost:19100',
        ),
        isTrue,
      );
      expect(
        LocalDevHttpsTrust.isLocalHttpsTransportBase(
          'https://118.31.239.122:19100',
        ),
        isFalse,
      );
    });

    test(
      'projects canonical signed target URLs to loopback without reclassifying install plane',
      () {
        const signedUploadUrl =
            'https://beta-upload.quwoquan-env.test:18100/upload/session';
        expect(
          LocalDevHttpsTrust.shouldResolveThroughLocalLoopback(signedUploadUrl),
          isTrue,
        );
        expect(
          LocalDevHttpsTrust.isLocalHttpsTransportBase(signedUploadUrl),
          isFalse,
          reason:
              'canonical authority alone must not trigger local CA installation',
        );
        expect(
          LocalDevHttpsTrust.shouldResolveThroughLocalLoopback(
            'https://media.quwoquan.com/upload/session',
          ),
          isFalse,
        );
      },
    );
  });
}

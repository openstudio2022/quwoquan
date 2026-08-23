import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/platform/native_runtime_config_bridge.dart';

final class _FakeClient implements RuntimeConfigChannelClient {
  _FakeClient(this.responses);

  final List<Object?> responses;
  var attempts = 0;

  @override
  Future<Object?> invokeMethod(String method) async {
    expect(method, 'readRuntimeConfig');
    final response = responses[attempts.clamp(0, responses.length - 1)];
    attempts += 1;
    if (response is Exception) {
      throw response;
    }
    if (response is Future<Object?>) {
      return response;
    }
    return response;
  }
}

void main() {
  test('Hot Restart 通道短暂空包时有界重试同一 package', () async {
    final client = _FakeClient(<Object?>[
      const <String, Object?>{},
      const <String, Object?>{
        'schema': 'app-runtime-config-package',
        'buildProfile': 'nonprod',
      },
    ]);
    final bridge = NativeRuntimeConfigBridge(
      client: client,
      retryDelay: Duration.zero,
    );

    final package = await bridge.readRuntimePackage();

    expect(client.attempts, 2);
    expect(package['buildProfile'], 'nonprod');
    expect(package, isNot(contains('package')));
    expect(package, isNot(contains('trustedBuildProfile')));
    expect(package, isNot(contains('trustedTarget')));
  });

  test('持续空包抛 typed emptyPackage，绝不返回空 map', () async {
    final client = _FakeClient(<Object?>[const <String, Object?>{}]);
    final bridge = NativeRuntimeConfigBridge(
      client: client,
      retryDelay: Duration.zero,
    );

    await expectLater(
      bridge.readRuntimePackage(),
      throwsA(
        isA<NativeRuntimeConfigReadException>()
            .having(
              (error) => error.reason,
              'reason',
              NativeRuntimeConfigReadFailureReason.emptyPackage,
            )
            .having((error) => error.attempts, 'attempts', 3),
      ),
    );
    expect(client.attempts, 3);
  });

  test(
    'MissingPlugin 与 PlatformException 转为 typed config read failure',
    () async {
      for (final testCase
          in <(Exception, NativeRuntimeConfigReadFailureReason)>[
            (
              MissingPluginException('missing'),
              NativeRuntimeConfigReadFailureReason.missingPlugin,
            ),
            (
              PlatformException(code: 'read_failed'),
              NativeRuntimeConfigReadFailureReason.platform,
            ),
          ]) {
        final bridge = NativeRuntimeConfigBridge(
          client: _FakeClient(<Object?>[testCase.$1]),
          maxAttempts: 1,
          retryDelay: Duration.zero,
        );
        await expectLater(
          bridge.readRuntimePackage(),
          throwsA(
            isA<NativeRuntimeConfigReadException>()
                .having((error) => error.reason, 'reason', testCase.$2)
                .having(
                  (error) => error.platformCode,
                  'platformCode',
                  testCase.$2 == NativeRuntimeConfigReadFailureReason.platform
                      ? 'read_failed'
                      : null,
                ),
          ),
        );
      }
    },
  );

  test('非 Map 与非字符串键 Map 转为 typed malformedPackage', () async {
    for (final response in <Object?>[
      'not-a-map',
      <Object?, Object?>{1: 'invalid-key'},
    ]) {
      final bridge = NativeRuntimeConfigBridge(
        client: _FakeClient(<Object?>[response]),
        maxAttempts: 1,
        retryDelay: Duration.zero,
      );

      await expectLater(
        bridge.readRuntimePackage(),
        throwsA(
          isA<NativeRuntimeConfigReadException>()
              .having(
                (error) => error.reason,
                'reason',
                NativeRuntimeConfigReadFailureReason.malformedPackage,
              )
              .having((error) => error.attempts, 'attempts', 1),
        ),
      );
    }
  });

  test('读取超时转为 typed timeout failure', () async {
    final bridge = NativeRuntimeConfigBridge(
      client: _FakeClient(<Object?>[Completer<Object?>().future]),
      maxAttempts: 1,
      retryDelay: Duration.zero,
      attemptTimeout: const Duration(milliseconds: 1),
    );

    await expectLater(
      bridge.readRuntimePackage(),
      throwsA(
        isA<NativeRuntimeConfigReadException>().having(
          (error) => error.reason,
          'reason',
          NativeRuntimeConfigReadFailureReason.timeout,
        ),
      ),
    );
  });
}

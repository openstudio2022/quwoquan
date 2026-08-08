import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';

/// `lib/runtime/context/**` 中 client context 快照与迁移桥的行为契约。
///
/// 两条关键纪律在这里被钉住：
///
/// 1. **未装配时必须是可识别的占位，而不是猜测值**。`regionCode` / `carrier`
///    没有真实来源时保持 `null`，灰度路由的地域维度对该请求就不匹配；一旦
///    fallback 开始填充猜测值，灰度会按错误地域放量。
/// 2. **`CloudClientContextRegistry` 是可变全局，必须能被装配覆盖并复位**。
///    它是存量静态 header builder 的迁移桥，测试之间若不能复位就会串味。
class _StubCloudClientContextProvider implements CloudClientContextProvider {
  _StubCloudClientContextProvider(this._snapshot);

  final CloudClientContextSnapshot _snapshot;
  int snapshotCallCount = 0;

  @override
  CloudClientContextSnapshot snapshot() {
    snapshotCallCount += 1;
    return _snapshot;
  }
}

void main() {
  // 该 registry 是进程级可变全局；每个用例结束后复位，避免污染同进程其他用例。
  tearDown(() {
    CloudClientContextRegistry.configure(
      const FallbackCloudClientContextProvider(),
    );
  });

  group('CloudClientContextSnapshot', () {
    test('optional dimensions default to null rather than a guessed value', () {
      const snapshot = CloudClientContextSnapshot(
        sessionId: 's-1',
        platform: 'ios',
        appVersion: '1.2.3',
        locale: 'zh-Hans-CN',
      );

      expect(snapshot.deviceActorId, isNull);
      expect(snapshot.regionCode, isNull);
      expect(snapshot.carrier, isNull);
    });

    test('supplied dimensions are carried verbatim', () {
      const snapshot = CloudClientContextSnapshot(
        sessionId: 's-1',
        platform: 'android',
        appVersion: '2.0.0',
        locale: 'en-US',
        deviceActorId: 'device-9',
        regionCode: '330000',
        carrier: 'chinamobile',
      );

      expect(snapshot.deviceActorId, 'device-9');
      expect(snapshot.regionCode, '330000');
      expect(snapshot.carrier, 'chinamobile');
    });
  });

  group('FallbackCloudClientContextProvider', () {
    test('exposes an explicitly unconfigured, non-guessing snapshot', () {
      const provider = FallbackCloudClientContextProvider();

      final snapshot = provider.snapshot();

      // 这些值是刻意「可被识别为未装配」的占位，不是伪造的真实值。
      expect(snapshot.sessionId, 'unconfigured');
      expect(snapshot.platform, 'unknown');
      expect(snapshot.appVersion, 'dev');
      expect(snapshot.locale, 'und');
      expect(snapshot.regionCode, isNull);
      expect(snapshot.carrier, isNull);
    });
  });

  group('CloudClientContextRegistry', () {
    test('defaults to the fallback provider before any composition runs', () {
      expect(
        CloudClientContextRegistry.provider,
        isA<FallbackCloudClientContextProvider>(),
      );
    });

    test('composition can replace the provider and every read observes it', () {
      final stub = _StubCloudClientContextProvider(
        const CloudClientContextSnapshot(
          sessionId: 'session-77',
          platform: 'ios',
          appVersion: '3.1.0',
          locale: 'zh-Hans-CN',
          regionCode: '110000',
        ),
      );

      CloudClientContextRegistry.configure(stub);

      expect(CloudClientContextRegistry.provider, same(stub));
      expect(
        CloudClientContextRegistry.provider.snapshot().sessionId,
        'session-77',
      );
      expect(
        CloudClientContextRegistry.provider.snapshot().regionCode,
        '110000',
      );
      expect(stub.snapshotCallCount, 2, reason: '每次读取都必须回到当前装配的 provider');
    });

    test('a later configure wins so composition order is the single truth', () {
      final first = _StubCloudClientContextProvider(
        const CloudClientContextSnapshot(
          sessionId: 'first',
          platform: 'ios',
          appVersion: '1.0.0',
          locale: 'zh-Hans-CN',
        ),
      );
      final second = _StubCloudClientContextProvider(
        const CloudClientContextSnapshot(
          sessionId: 'second',
          platform: 'ios',
          appVersion: '1.0.0',
          locale: 'zh-Hans-CN',
        ),
      );

      CloudClientContextRegistry.configure(first);
      CloudClientContextRegistry.configure(second);

      expect(CloudClientContextRegistry.provider.snapshot().sessionId, 'second');
      expect(first.snapshotCallCount, 0);
    });

    test('can be restored to the fallback provider', () {
      CloudClientContextRegistry.configure(
        _StubCloudClientContextProvider(
          const CloudClientContextSnapshot(
            sessionId: 'temporary',
            platform: 'ios',
            appVersion: '1.0.0',
            locale: 'zh-Hans-CN',
          ),
        ),
      );

      CloudClientContextRegistry.configure(
        const FallbackCloudClientContextProvider(),
      );

      expect(
        CloudClientContextRegistry.provider.snapshot().sessionId,
        'unconfigured',
      );
    });
  });
}

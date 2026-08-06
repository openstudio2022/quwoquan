import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/platform/native_bridge.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_context_provider.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_session_store.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('bootstrapForColdStart 不阻塞于 SecureStorage', () async {
    final neverCompletes = Completer<String?>();
    final store = AppTelemetrySessionStore(
      guestKeyStore: _HangingGuestKeyStore(neverCompletes.future),
      now: () => DateTime.utc(2026, 7, 18, 8),
    );

    store.bootstrapForColdStart();
    expect(store.isInitialized, isTrue);
    expect(store.sessionId, startsWith('s.'));
    store.dispose();
  });

  test('reconcilePersistedGuestKey 用持久 guest key 对齐内存会话', () async {
    final store = AppTelemetrySessionStore(
      guestKeyStore: _MemoryGuestKeyStore('guest_01ARZ3NDEKTSV4RRFFQ69G5FAV'),
      now: () => DateTime.utc(2026, 7, 18, 8),
    );

    store.bootstrapForColdStart();
    final ephemeral = store.sessionId;
    await store.reconcilePersistedGuestKey();
    final hydrated = AppTelemetrySessionStore.parseSessionId(store.sessionId);
    expect(store.sessionId, isNot(ephemeral));
    expect(hydrated.userKey, 'guest_01ARZ3NDEKTSV4RRFFQ69G5FAV');
    store.dispose();
  });

  test('session 使用可逆 actor 编码并在同毫秒切换时单调递增', () async {
    final clock = _Clock(DateTime.utc(2026, 7, 18, 8));
    final store = AppTelemetrySessionStore(
      guestKeyStore: _MemoryGuestKeyStore('guest_01ARZ3NDEKTSV4RRFFQ69G5FAV'),
      now: clock.call,
    );

    await store.initialize(authenticatedUserKey: 'user.name/中文');
    final first = AppTelemetrySessionStore.parseSessionId(store.sessionId);
    store.updateActor('other.user', reason: 'account_switch');
    final second = AppTelemetrySessionStore.parseSessionId(store.sessionId);

    expect(first.userKey, 'user.name/中文');
    expect(second.userKey, 'other.user');
    expect(second.startedAtMs, first.startedAtMs + 1);
    expect(store.sessionId.split('.'), hasLength(3));
    store.dispose();
  });

  test('inactive 不切会话，后台终态后的 resumed 才新建会话', () async {
    final clock = _Clock(DateTime.utc(2026, 7, 18, 8));
    final store = AppTelemetrySessionStore(
      guestKeyStore: _MemoryGuestKeyStore('guest_01ARZ3NDEKTSV4RRFFQ69G5FAV'),
      now: clock.call,
    );
    await store.initialize();
    final initial = store.sessionId;

    store.didChangeAppLifecycleState(AppLifecycleState.inactive);
    store.didChangeAppLifecycleState(AppLifecycleState.resumed);
    expect(store.sessionId, initial);

    clock.advance(const Duration(seconds: 1));
    store.didChangeAppLifecycleState(AppLifecycleState.paused);
    expect(store.sessionId, initial);
    store.didChangeAppLifecycleState(AppLifecycleState.resumed);
    expect(store.sessionId, isNot(initial));
    store.dispose();
  });

  test('静态上下文只加载一次，VPN 下仍归一化为底层网络类型', () async {
    var loads = 0;
    final changes = StreamController<List<ConnectivityResult>>.broadcast();
    final cellularProbe = _CellularProbe(CellularNetworkGeneration.g5);
    final provider = AppTelemetryContextProvider(
      staticContextLoader: () async {
        loads++;
        return const AppTelemetryStaticContext(
          deviceManufacturer: 'Apple',
          deviceModel: 'iPhone',
          appVersion: '1.0.0+1',
          devicePlatform: 'ios',
        );
      },
      connectivityLoader: () async => const <ConnectivityResult>[
        ConnectivityResult.mobile,
        ConnectivityResult.wifi,
      ],
      connectivityChanges: changes.stream,
      cellularNetworkProbe: cellularProbe,
    );

    await provider.initialize();
    await provider.initialize();
    expect(loads, 1);
    expect(provider.networkClass, 'wifi');
    expect(provider.devicePlatform, 'ios');
    changes.add(const <ConnectivityResult>[
      ConnectivityResult.wifi,
      ConnectivityResult.vpn,
    ]);
    await pumpEventQueue();
    expect(provider.networkClass, 'wifi');

    changes.add(const <ConnectivityResult>[
      ConnectivityResult.mobile,
      ConnectivityResult.vpn,
    ]);
    await pumpEventQueue();
    expect(provider.networkClass, '5g');
    expect(
      AppTelemetryContextProvider.resolveNetworkClass(
        const <ConnectivityResult>[
          ConnectivityResult.ethernet,
          ConnectivityResult.vpn,
        ],
      ),
      'ethernet',
    );
    expect(
      AppTelemetryContextProvider.resolveNetworkClass(
        const <ConnectivityResult>[ConnectivityResult.mobile],
        cellularGeneration: CellularNetworkGeneration.g4,
      ),
      '4g',
    );
    expect(
      AppTelemetryContextProvider.resolveNetworkClass(
        const <ConnectivityResult>[ConnectivityResult.mobile],
      ),
      'mobile',
    );
    expect(
      AppTelemetryContextProvider.resolveNetworkClass(
        const <ConnectivityResult>[ConnectivityResult.vpn],
      ),
      'other',
    );
    expect(AppTelemetryContextProvider.resolveNetworkClass(const []), 'none');

    await provider.dispose();
    await changes.close();
  });
}

final class _CellularProbe implements CellularNetworkProbe {
  _CellularProbe(this.generation);

  CellularNetworkGeneration generation;

  @override
  Future<CellularNetworkGeneration> readGeneration() async => generation;
}

final class _MemoryGuestKeyStore implements AppTelemetryGuestKeyStore {
  _MemoryGuestKeyStore(this.value);

  String? value;

  @override
  Future<String?> read() async => value;

  @override
  Future<void> write(String value) async => this.value = value;
}

final class _HangingGuestKeyStore implements AppTelemetryGuestKeyStore {
  _HangingGuestKeyStore(this._readFuture);

  final Future<String?> _readFuture;

  @override
  Future<String?> read() => _readFuture;

  @override
  Future<void> write(String value) async {}
}

final class _Clock {
  _Clock(this.value);

  DateTime value;

  DateTime call() => value;

  void advance(Duration duration) => value = value.add(duration);
}

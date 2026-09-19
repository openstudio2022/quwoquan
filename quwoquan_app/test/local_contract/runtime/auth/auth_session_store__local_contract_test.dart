import 'dart:async';
import 'dart:convert';

import 'package:crypto/crypto.dart' as crypto;

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/config/rehearsal_storage_namespace.dart';
import 'package:quwoquan_app/runtime/config/rehearsal_storage_observer.dart';
import 'package:quwoquan_app/runtime/config/generated/app_launch_contract.g.dart';
import 'package:quwoquan_app/runtime/config/runtime_package_resolver.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/config/generated/offline_content_bundle_identity.g.dart';
import 'package:quwoquan_app/runtime/platform/native_runtime_config_bridge.dart';
import 'package:quwoquan_cloud_contracts/generated/values/user/account/account_session.values.dart';

import '../alpha_rehearsal/alpha_rehearsal_synthetic_login__local_contract_test.dart'
    as signed;
import '../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../support/runtime/config/runtime_package_test_hydration.dart';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:shared_preferences/shared_preferences.dart';

// 文件内私有持久double；跨store实例保留数据，从不调用平台Keychain。
class PrivateAuthStorage extends FlutterSecureStorage {
  final values = <String, String>{
    'auth.install_id': 'sentinel-install',
    'auth.alpha-local%7Calpha.access_token': 'sentinel-token',
  };
  final calls = <String>[];
  int writes = 0;
  bool failWrite = false;
  bool dropSyntheticWrite = false;
  bool failRead = false;
  bool failDelete = false;
  Completer<void>? readRelease;
  String? delayReadKey;
  Completer<void>? writeRelease;
  Completer<void>? deleteRelease;
  @override
  Future<String?> read({
    required String key,
    AppleOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    AppleOptions? mOptions,
    WindowsOptions? wOptions,
  }) async {
    calls.add(key);
    if (readRelease != null && (delayReadKey == null || delayReadKey == key)) {
      await readRelease!.future;
    }
    if (failRead) throw StateError('private read failure');
    return values[key];
  }

  @override
  Future<void> write({
    required String key,
    required String? value,
    AppleOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    AppleOptions? mOptions,
    WindowsOptions? wOptions,
  }) async {
    calls.add(key);
    if (writeRelease != null) await writeRelease!.future;
    if (failWrite) throw StateError('private storage failure');
    writes++;
    if (dropSyntheticWrite && key.endsWith('synthetic_session')) return;
    if (value == null) {
      values.remove(key);
    } else {
      values[key] = value;
    }
  }

  @override
  Future<void> delete({
    required String key,
    AppleOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    AppleOptions? mOptions,
    WindowsOptions? wOptions,
  }) async {
    calls.add(key);
    if (deleteRelease != null) await deleteRelease!.future;
    if (failDelete) throw StateError('private delete failure');
    values.remove(key);
  }
}

// 私有确定性owner身份，仅本地测试，不能作为生产startup绑定。
class StorageObservationFixture {
  StorageObservationFixture(this.space) : current = space {
    observer = RehearsalStorageObserver(
      space: space,
      currentSpace: () => current,
      startupAttemptId: attempt,
      generation: generation,
      currentStartupAttemptId: () => attempt,
      currentGeneration: () => generation,
    );
  }
  final VerifiedRehearsalSpace space;
  VerifiedRehearsalSpace? current;
  String? attempt = 'private-attempt-1';
  String? generation = '1';
  late final RehearsalStorageObserver observer;
}

class _StorageRuntimeChannel implements RuntimeConfigChannelClient {
  _StorageRuntimeChannel(this.envelope);
  final Map<String, Object?> envelope;
  @override
  Future<Object?> invokeMethod(String method) async => envelope;
}

Future<void> hydrateIsolatedStorageRuntime({
  String instance = 'space-a',
}) async {
  final runtime = await signed.signedRuntime(
    instance: instance,
    expectedSnapshot: offlineContentManifestDigest,
    mutate: (doc) => (doc['rehearsalSpace'] as Map)['snapshotDigest'] =
        offlineContentManifestDigest,
  );
  final doc = runtime.package;
  await CloudRuntimeConfig.hydrateFromNativeRuntimePackage(
    // fixture在签名前绑定同一制品pin；expected绝不从待验文档反取。
    expectedOfflineSnapshotDigest: offlineContentManifestDigest,
    bridge: NativeRuntimeConfigBridge(
      client: _StorageRuntimeChannel({
        'package': {...doc.signedPayloadMap(), 'signature': doc.signature},
        'trustedBuildProfile': 'nonprod',
        'trustedTarget': 'alpha-local',
        'trustedPublicKeys': doc.trustedPublicKeys,
        'runtimeConfigPackageDigest':
            'sha256:${crypto.sha256.convert(utf8.encode(canonicalJsonEncode({...doc.signedPayloadMap(), 'signature': doc.signature})))}',
        'runtimeConfigTrustEnvelopeDigest': (doc
            .signedPayloadMap()['trustEnvelopeDigest']),
        'effectiveLaunchManifestDigest': 'sha256:${'c' * 64}',
        'launchProvenance': 'canonical_launcher',
        'runtimeConfigSupplyMode': 'external_runtime_package',
      }),
      maxAttempts: 1,
    ),
  );
}

// 不可拨打的合成标识：只验证完整字符串的持久化，不涉及手机号校验。
const String _syntheticPhoneIdentifier = '00000000000';

const String _defaultNicknameSample = '新同学_260622_6698692';
final RegExp _defaultNicknamePattern = RegExp(r'^新同学_\d{6}_\d{7}$');

/// `AuthSessionGrant` 的 wire 必填面（accountState / identityOrigin /
/// logicalShard / anonymousRetentionPolicy / personaCount /
/// sessionRememberTtlSeconds）全部是 NOT_NULL，云端每次登录授权都会下发。
/// 本套件只验证 AuthSessionStore 的本机持久化语义，所以用例只声明自己断言的字段，
/// 其余由 canonical 默认值补齐，避免每个用例重复整份授权体。
AuthSessionGrant _grant(Map<String, dynamic> overrides) {
  final accountHint = overrides['accountHint'];
  return decodeAuthSessionGrant(<String, dynamic>{
    'accountState': 'active',
    'identityOrigin': 'phone',
    'logicalShard': 1,
    'anonymousRetentionPolicy': 'preserve',
    'personaCount': 1,
    'sessionRememberTtlSeconds': 0,
    ...overrides,
    if (accountHint is Map<String, dynamic>)
      'accountHint': <String, dynamic>{
        'nicknameCustomized': false,
        'avatarUrl': '',
        'avatarAssetId': '',
        'maskedPhone': '',
        'identityOrigin': 'phone',
        ...accountHint,
      },
  });
}

// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/local-cache-architecture/spec.md#gwt-003
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  // spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-008
  group('auth真实IO观察', () {
    test('构造与纯read不访问存储，auth和install独立记录且旧实例不伤新attach', () async {
      final f = StorageObservationFixture(
        (await signed.signedRuntime()).rehearsalSpace!,
      );
      final storage = PrivateAuthStorage();
      final ns = RehearsalStorageNamespace(f.space);
      AuthSessionStore create() => AuthSessionStore.isolated(
        namespace: ns,
        currentSpace: () => f.current,
        secureStorage: storage,
        observer: f.observer,
        prefsFactory: () => throw StateError('不得加载全局prefs'),
      );
      expect(
        f.observer.read().auth.state,
        RehearsalConsumerObservationState.notObserved,
      );
      final store = create();
      expect(
        f.observer.read().auth.state,
        RehearsalConsumerObservationState.constructed,
      );
      expect(
        f.observer.read().installId.state,
        RehearsalConsumerObservationState.constructed,
      );
      expect(
        f.observer.read().pending.state,
        RehearsalConsumerObservationState.notObserved,
      );
      expect(storage.calls, isEmpty);
      await store.read();
      expect(f.observer.read().installId.successfulOperations, [
        RehearsalSuccessfulOperation.write,
      ]);
      expect(f.observer.read().auth.successfulOperations, isEmpty);
      final result = SyntheticSessionResult(
        accountId: 'alpha-account:${'a' * 32}',
        personaId: 'alpha-persona:${'b' * 32}',
      );
      await store.saveSyntheticSession(result);
      await store.read();
      await store.clearSession(manualLogout: true);
      await store.clearSession(manualLogout: true);
      expect(
        f.observer.read().auth.successfulOperations,
        containsAll(RehearsalSuccessfulOperation.values),
      );
      expect(
        f.observer.read().installId.successfulOperations,
        containsAll([
          RehearsalSuccessfulOperation.read,
          RehearsalSuccessfulOperation.write,
        ]),
      );
      final calls = storage.calls.length;
      f.observer.read();
      f.observer.read();
      expect(storage.calls.length, calls);
      store.dispose();
      expect(f.observer.read().auth.namespaceDigest, isEmpty);
      final next = create();
      store.dispose();
      expect(
        f.observer.read().auth.state,
        RehearsalConsumerObservationState.constructed,
      );
      await next.read();
      expect(
        storage.calls.where(
          (k) => k == 'auth.install_id' || k.contains('alpha-local'),
        ),
        isEmpty,
      );
      expect(storage.values['auth.install_id'], 'sentinel-install');
      next.dispose();
    });

    for (final operation in RehearsalSuccessfulOperation.values) {
      for (final failure in [
        'storage',
        'space',
        'attempt',
        'generation',
        'dispose',
        'intent',
      ]) {
        test('$operation失败或迟到$failure不记录成功', () async {
          final f = StorageObservationFixture(
            (await signed.signedRuntime()).rehearsalSpace!,
          );
          final ns = RehearsalStorageNamespace(f.space);
          final storage = PrivateAuthStorage();
          storage.values[ns.installIdKey] = 'private-install';
          final store = AuthSessionStore.isolated(
            namespace: ns,
            currentSpace: () => f.current,
            secureStorage: storage,
            observer: f.observer,
          );
          var intent = true;
          final release = Completer<void>();
          if (failure == 'storage') {
            storage.failRead = operation == RehearsalSuccessfulOperation.read;
            storage.failWrite = operation == RehearsalSuccessfulOperation.write;
            storage.failDelete =
                operation == RehearsalSuccessfulOperation.delete;
          } else {
            if (operation == RehearsalSuccessfulOperation.read) {
              storage.readRelease = release;
            }
            if (operation == RehearsalSuccessfulOperation.write) {
              storage.writeRelease = release;
            }
            if (operation == RehearsalSuccessfulOperation.delete) {
              storage.deleteRelease = release;
            }
          }
          final result = SyntheticSessionResult(
            accountId: 'alpha-account:${'a' * 32}',
            personaId: 'alpha-persona:${'b' * 32}',
          );
          Future<void> run() async {
            if (operation == RehearsalSuccessfulOperation.read) {
              await store.read();
            }
            if (operation == RehearsalSuccessfulOperation.write) {
              await store.saveSyntheticSession(
                result,
                fence: () {
                  if (!intent) throw StateError('cancelled intent');
                },
              );
            }
            if (operation == RehearsalSuccessfulOperation.delete) {
              await store.clearSession(manualLogout: true);
            }
          }

          final pending = run();
          final rejected = expectLater(pending, throwsA(isA<Object>()));
          await Future<void>.delayed(Duration.zero);
          if (failure == 'space') f.current = null;
          if (failure == 'attempt') f.attempt = 'private-attempt-2';
          if (failure == 'generation') f.generation = '2';
          if (failure == 'dispose') store.dispose();
          if (failure == 'intent') {
            intent = false;
            if (operation != RehearsalSuccessfulOperation.write) {
              store.dispose();
            }
          }
          if (failure != 'storage') release.complete();
          await rejected;
          expect(f.observer.read().auth.successfulOperations, isEmpty);
          expect(f.observer.read().installId.successfulOperations, isEmpty);
          expect(
            storage.calls.where(
              (k) => k == 'auth.install_id' || k.contains('alpha-local'),
            ),
            isEmpty,
          );
          store.dispose();
        });
      }
    }

    test('auth payload读取晚到时不报告read，install成功事实独立失效', () async {
      final f = StorageObservationFixture(
        (await signed.signedRuntime()).rehearsalSpace!,
      );
      final ns = RehearsalStorageNamespace(f.space);
      final storage = PrivateAuthStorage();
      storage.values[ns.installIdKey] = 'private-install';
      final store = AuthSessionStore.isolated(
        namespace: ns,
        currentSpace: () => f.current,
        secureStorage: storage,
        observer: f.observer,
      );
      await store.saveSyntheticSession(
        SyntheticSessionResult(
          accountId: 'alpha-account:${'a' * 32}',
          personaId: 'alpha-persona:${'b' * 32}',
        ),
      );
      store.dispose();
      final next = AuthSessionStore.isolated(
        namespace: ns,
        currentSpace: () => f.current,
        secureStorage: storage,
        observer: f.observer,
      );
      final release = Completer<void>();
      storage.delayReadKey =
          'auth.${Uri.encodeComponent(ns.authNamespace)}.synthetic_session';
      storage.readRelease = release;
      final rejected = expectLater(next.read(), throwsA(isA<Object>()));
      await Future<void>.delayed(Duration.zero);
      expect(f.observer.read().installId.successfulOperations, [
        RehearsalSuccessfulOperation.read,
      ]);
      expect(f.observer.read().auth.successfulOperations, isEmpty);
      f.attempt = 'private-attempt-2';
      release.complete();
      await rejected;
      expect(f.observer.read().auth.namespaceDigest, isEmpty);
      expect(f.observer.read().installId.namespaceDigest, isEmpty);
      next.dispose();
    });

    test('缺attempt/generation仍可正常IO但观察unavailable，标准store不注册', () async {
      final space = (await signed.signedRuntime()).rehearsalSpace!;
      final observer = RehearsalStorageObserver(
        space: space,
        currentSpace: () => space,
        startupAttemptId: null,
        generation: null,
        currentStartupAttemptId: () => null,
        currentGeneration: () => null,
      );
      final store = AuthSessionStore.isolated(
        namespace: RehearsalStorageNamespace(space),
        currentSpace: () => space,
        secureStorage: PrivateAuthStorage(),
        observer: observer,
      );
      await store.read();
      expect(observer.read().status, RehearsalObservationStatus.unavailable);
      expect(observer.read().auth.successfulOperations, isEmpty);
      store.dispose();
      final container = ProviderContainer(
        overrides: [
          rehearsalStorageObserverProvider.overrideWithValue(observer),
        ],
      );
      expect(container.read(authSessionStoreProvider).isIsolated, isFalse);
      expect(observer.read().auth.namespaceDigest, isEmpty);
      container.dispose();
    });
  });

  test('isolated auth仅逐键访问新空间，无全局prefs加载或旧installId访问', () async {
    final space = (await signed.signedRuntime()).rehearsalSpace!;
    final namespace = RehearsalStorageNamespace(space);
    final storage = PrivateAuthStorage();
    final store = AuthSessionStore.isolated(
      namespace: namespace,
      currentSpace: () => space,
      secureStorage: storage,
      prefsFactory: () => throw StateError('禁止全局prefs读取'),
    );
    expect(store.isIsolated, isTrue);
    final result = SyntheticSessionResult(
      accountId: 'alpha-account:${'a' * 32}',
      personaId: 'alpha-persona:${'b' * 32}',
    );
    final first = await store.read();
    await store.saveSyntheticSession(result);
    final restored = await store.read();
    expect(restored.ownerId, result.accountId);
    expect(restored.accessToken, isEmpty);
    expect(restored.refreshToken, isEmpty);
    expect(restored.installId, first.installId);
    final restarted = (await signed.signedRuntime()).rehearsalSpace!;
    final next = AuthSessionStore.isolated(
      namespace: RehearsalStorageNamespace(restarted),
      currentSpace: () => restarted,
      secureStorage: storage,
    );
    expect((await next.read()).ownerId, result.accountId);
    final other = (await signed.signedRuntime(instance: 'space-b'))
        .rehearsalSpace!;
    final isolated = AuthSessionStore.isolated(
      namespace: RehearsalStorageNamespace(other),
      currentSpace: () => other,
      secureStorage: storage,
    );
    expect((await isolated.read()).ownerId, isEmpty);
    await next.clearSession(manualLogout: true);
    expect((await next.read()).ownerId, isEmpty);
    expect(storage.values['auth.install_id'], 'sentinel-install');
    expect(
      storage.values['auth.alpha-local%7Calpha.access_token'],
      'sentinel-token',
    );
    expect(
      storage.calls.where(
        (key) => key == 'auth.install_id' || key.contains('alpha-local'),
      ),
      isEmpty,
    );
  });

  test('isolated auth在await后切space或dispose不再执行下一I/O', () async {
    final space = (await signed.signedRuntime()).rehearsalSpace!;
    VerifiedRehearsalSpace? current = space;
    final storage = PrivateAuthStorage()..readRelease = Completer<void>();
    final store = AuthSessionStore.isolated(
      namespace: RehearsalStorageNamespace(space),
      currentSpace: () => current,
      secureStorage: storage,
    );
    final read = store.read();
    final rejected = expectLater(read, throwsA(isA<Object>()));
    await Future<void>.delayed(Duration.zero);
    current = (await signed.signedRuntime()).rehearsalSpace!;
    storage.readRelease!.complete();
    await rejected;
    expect(storage.calls, hasLength(1));
    expect(storage.writes, 0);
    final fresh = AuthSessionStore.isolated(
      namespace: RehearsalStorageNamespace(current),
      currentSpace: () => current,
      secureStorage: storage,
    );
    fresh.dispose();
    await expectLater(fresh.read(), throwsA(isA<Object>()));
    expect(storage.calls, hasLength(1));
    expect(
      () => AuthSessionStore.isolated(
        namespace: RehearsalStorageNamespace(space),
        currentSpace: () => throw StateError('unhydrated'),
        secureStorage: storage,
      ),
      throwsA(isA<Object>()),
    );
    expect(storage.calls, hasLength(1));
  });

  test('isolated实际provider在restore前绑定，新代可恢复无bearer身份', () async {
    await hydrateIsolatedStorageRuntime();
    final storage = PrivateAuthStorage();
    final space = CloudRuntimeConfig.rehearsalSpace!;
    final store = AuthSessionStore.isolated(
      namespace: RehearsalStorageNamespace(space),
      currentSpace: () => CloudRuntimeConfig.rehearsalSpace,
      secureStorage: storage,
    );
    final container = ProviderContainer(
      overrides: [
        ...sealedCloudBoundaryOverrides(),
        authSessionStoreProvider.overrideWithValue(store),
      ],
    );
    try {
      final controller = container.read(authSessionControllerProvider.notifier);
      await controller.restore();
      final result = SyntheticSessionResult(
        accountId: 'alpha-account:${'c' * 32}',
        personaId: 'alpha-persona:${'d' * 32}',
      );
      storage.failWrite = true;
      await expectLater(
        controller.applySyntheticSession(result),
        throwsA(isA<StateError>()),
      );
      expect(
        container.read(authSessionControllerProvider).isAuthenticated,
        isFalse,
      );
      storage.failWrite = false;
      storage.dropSyntheticWrite = true;
      await expectLater(
        controller.applySyntheticSession(result),
        throwsStateError,
      );
      expect(
        container.read(authSessionControllerProvider).isAuthenticated,
        isFalse,
      );
      storage.dropSyntheticWrite = false;
      final beforeReadback = storage.calls.length;
      await controller.applySyntheticSession(result);
      final syntheticReads = storage.calls
          .skip(beforeReadback)
          .where((key) => key.endsWith('synthetic_session'));
      expect(
        syntheticReads.length,
        greaterThanOrEqualTo(3),
      ); // 提交前read、write、提交后read。
      final state = container.read(authSessionControllerProvider);
      expect(state.isAuthenticated, isTrue);
      expect(state.hasTrustedSession, isFalse);
      expect(state.accessToken, isEmpty);
      expect(state.refreshToken, isEmpty);
      expect(await controller.accessTokenForRequest(), isNull);
      await expectLater(
        controller.applyLoginGrant(
          _grant({
            'accessToken': 'remote-access',
            'refreshToken': 'remote-refresh',
            'ownerId': 'remote-owner',
            'activePersona': {'personaId': 'remote-persona'},
          }),
        ),
        throwsA(isA<Object>()),
      );
      final restartedStore = AuthSessionStore.isolated(
        namespace: RehearsalStorageNamespace(space),
        currentSpace: () => CloudRuntimeConfig.rehearsalSpace,
        secureStorage: storage,
      );
      final restarted = ProviderContainer(
        overrides: [
          ...sealedCloudBoundaryOverrides(),
          authSessionStoreProvider.overrideWithValue(restartedStore),
        ],
      );
      await restarted.read(authSessionControllerProvider.notifier).restore();
      expect(
        restarted.read(authSessionControllerProvider).ownerId,
        result.accountId,
      );
      expect(
        restarted.read(authSessionControllerProvider).isAuthenticated,
        isTrue,
      );
      expect(
        restarted.read(authSessionControllerProvider).hasTrustedSession,
        isFalse,
      );
      restarted.dispose();
      final providers = ProviderContainer();
      final productionStore = providers.read(authSessionStoreProvider);
      expect(productionStore.isIsolated, isTrue);
      providers.dispose();
      expect(productionStore.requireCurrentStorage, throwsA(isA<Object>()));
    } finally {
      container.dispose();
      await hydrateRuntimePackageForTests(environment: 'beta');
    }
  });

  test('isolated provider先于任何平台I/O拒绝未水合，standard显式构造拒绝', () async {
    final runtime = await signed.signedRuntime(
      mode: 'standard',
      instance: 'default',
    );
    expect(
      () => RehearsalStorageNamespace(runtime.rehearsalSpace!),
      throwsA(isA<Object>()),
    );
    await expectLater(
      CloudRuntimeConfig.hydrateFromNativeRuntimePackage(
        bridge: NativeRuntimeConfigBridge(
          client: _StorageRuntimeChannel({}),
          maxAttempts: 1,
        ),
      ),
      throwsA(isA<Object>()),
    );
    final container = ProviderContainer();
    expect(
      () => container.read(authSessionStoreProvider),
      throwsA(isA<Object>()),
    );
    container.dispose();
    await hydrateRuntimePackageForTests(environment: 'beta');
  });

  test('isolated controller销毁时迟到restore不生成installId或写身份', () async {
    await hydrateIsolatedStorageRuntime();
    final space = CloudRuntimeConfig.rehearsalSpace!;
    final storage = PrivateAuthStorage()..readRelease = Completer<void>();
    final store = AuthSessionStore.isolated(
      namespace: RehearsalStorageNamespace(space),
      currentSpace: () => CloudRuntimeConfig.rehearsalSpace,
      secureStorage: storage,
    );
    final container = ProviderContainer(
      overrides: [
        ...sealedCloudBoundaryOverrides(),
        authSessionStoreProvider.overrideWithValue(store),
      ],
    );
    final controller = container.read(authSessionControllerProvider.notifier);
    final restore = controller.restore();
    await Future<void>.delayed(Duration.zero);
    container.dispose();
    storage.readRelease!.complete();
    await restore;
    expect(storage.calls, hasLength(1));
    expect(storage.writes, 0);
    await hydrateRuntimePackageForTests(environment: 'beta');
  });

  test('target 隔离授权且 installId 保持安装级，旧 token 不迁移', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      'auth.install_id': 'installation-1',
      'auth.owner_id': 'legacy-owner',
    });
    FlutterSecureStorage.setMockInitialValues(<String, String>{
      'auth.access_token': 'legacy-access',
      'auth.refresh_token': 'legacy-refresh',
    });
    final sim = AuthSessionStore(storageNamespace: 'prod-sim|prod');
    final hosted = AuthSessionStore(storageNamespace: 'prod-hosted|prod');
    expect((await sim.read()).accessToken, isEmpty);
    await sim.saveLoginGrant(
      _grant(<String, dynamic>{
        'accessToken': 'sim-access',
        'refreshToken': 'sim-refresh',
        'ownerId': 'sim-owner',
        'activePersona': <String, dynamic>{'personaId': 'sim-persona'},
      }),
    );
    expect((await hosted.read()).accessToken, isEmpty);
    expect((await hosted.read()).ownerId, isEmpty);
    expect((await sim.read()).accessToken, 'sim-access');
    expect((await sim.read()).installId, 'installation-1');
    expect((await hosted.read()).installId, 'installation-1');
  });
  setUp(() async {
    // 每例独立建立真实签名在线前置，避免前例失败留下未水合状态污染头像清理。
    // isolated/未水合负例仍在自身用例内显式覆盖这一前置。
    await hydrateRuntimePackageForTests(environment: 'beta');
    SharedPreferences.setMockInitialValues(<String, Object>{});
    FlutterSecureStorage.setMockInitialValues(<String, String>{});
  });

  test('saveLoginGrant persists tokens and active persona', () async {
    final store = AuthSessionStore(secureStorage: const FlutterSecureStorage());
    final result = _grant(<String, dynamic>{
      'accessToken': 'access-1',
      'refreshToken': 'refresh-1',
      'ownerId': 'owner-1',
      'activePersona': <String, dynamic>{'personaId': 'sub-1'},
      'personaCount': 1,
      'accountState': 'active',
      'identityOrigin': 'phone',
    });

    await store.saveLoginGrant(result);
    final stored = await store.read();

    expect(stored.accessToken, 'access-1');
    expect(stored.refreshToken, 'refresh-1');
    expect(stored.ownerId, 'owner-1');
    expect(stored.activePersonaId, 'sub-1');
    expect(stored.manualLoggedOut, isFalse);
  });

  test(
    'saveLoginGrant persists remembered login method and masked account',
    () async {
      final store = AuthSessionStore(
        secureStorage: const FlutterSecureStorage(),
      );
      final result = _grant(<String, dynamic>{
        'accessToken': 'access-2',
        'refreshToken': 'refresh-2',
        'ownerId': 'owner-2',
        'activePersona': <String, dynamic>{'personaId': 'sub-2'},
        'personaCount': 1,
        'accountState': 'active',
        'identityOrigin': 'phone',
        'accountHint': <String, dynamic>{
          'displayName': _defaultNicknameSample,
          'nicknameCustomized': false,
          'avatarUrl': 'https://cdn.example.com/avatar.png',
          'maskedPhone': '138****3909',
        },
      });

      await store.saveLoginGrant(
        result,
        rememberedLoginMethod: AuthRememberedLoginMethod.phoneOtp,
      );
      final stored = await store.read();

      expect(stored.rememberedLoginMethod, AuthRememberedLoginMethod.phoneOtp);
      expect(stored.rememberedLoginMaskedIdentifier, '138****3909');
      expect(stored.rememberedDisplayName, matches(_defaultNicknamePattern));
      expect(stored.rememberedAvatarUrl, 'https://cdn.example.com/avatar.png');
      expect(stored.rememberedNicknameCustomized, isFalse);
    },
  );

  test('malformed nicknameCustomized cannot grant customized status', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      'auth.unbound.remembered_nickname_customized': 'true',
    });
    final store = AuthSessionStore(secureStorage: const FlutterSecureStorage());

    final stored = await store.read();

    expect(stored.rememberedNicknameCustomized, isFalse);
  });

  test('read restores the canonical active persona key', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      'auth.unbound.active_persona_id': 'persona-current',
    });
    final store = AuthSessionStore(secureStorage: const FlutterSecureStorage());

    final stored = await store.read();
    final preferences = await SharedPreferences.getInstance();

    expect(stored.activePersonaId, 'persona-current');
    expect(
      preferences.getString('auth.unbound.active_persona_id'),
      'persona-current',
    );
  });

  test('active refresh token is never reinterpreted as quick login', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      'auth.unbound.account_state': 'active',
      'auth.unbound.manual_logged_out': true,
    });
    FlutterSecureStorage.setMockInitialValues(<String, String>{
      'auth.unbound.refresh_token': 'active-refresh',
    });
    final store = AuthSessionStore(secureStorage: const FlutterSecureStorage());

    final stored = await store.read();

    expect(stored.refreshToken, 'active-refresh');
    expect(stored.rememberedRefreshToken, isEmpty);
    expect(stored.quickLoginRefreshToken, isEmpty);
    expect(stored.hasValidQuickLoginCredential, isFalse);
  });

  test('quick login requires its canonical explicit expiry', () async {
    final nowMs = DateTime.now().millisecondsSinceEpoch;
    SharedPreferences.setMockInitialValues(<String, Object>{
      'auth.unbound.manual_logged_out': true,
      'auth.unbound.last_refresh_at_epoch_ms': nowMs,
      'auth.unbound.session_remember_ttl_seconds': 2592000,
    });
    FlutterSecureStorage.setMockInitialValues(<String, String>{
      'auth.unbound.remembered_refresh_token': 'remembered-refresh',
    });
    final store = AuthSessionStore(secureStorage: const FlutterSecureStorage());

    final stored = await store.read();

    expect(stored.quickLoginRefreshToken, 'remembered-refresh');
    expect(stored.quickLoginExpiresAtEpochMs, 0);
    expect(stored.hasValidQuickLoginCredential, isFalse);
  });

  test('clearSession records manual logout prompt state', () async {
    final store = AuthSessionStore(secureStorage: const FlutterSecureStorage());

    await store.clearSession(manualLogout: true);
    final stored = await store.read();

    expect(stored.accessToken, isEmpty);
    expect(stored.refreshToken, isEmpty);
    expect(stored.manualLoggedOut, isTrue);
    expect(stored.launchPromptDismissed, isFalse);
  });

  test(
    'softLogout keeps refresh credential and records quick-login expiry',
    () async {
      final store = AuthSessionStore(
        secureStorage: const FlutterSecureStorage(),
      );
      await store.saveLoginGrant(
        _grant(<String, dynamic>{
          'accessToken': 'access-soft',
          'refreshToken': 'refresh-soft',
          'ownerId': 'owner-soft',
          'accountState': 'active',
          'identityOrigin': 'phone',
          'accountHint': <String, dynamic>{
            'displayName': '趣友A',
            'nicknameCustomized': true,
            'maskedPhone': '138****0001',
          },
        }),
        rememberedLoginMethod: AuthRememberedLoginMethod.phoneOtp,
      );

      await store.softLogout();
      final stored = await store.read();

      // 软退出：失效活跃会话（删 accessToken），但保留快速登录凭证与账号摘要。
      expect(stored.accessToken, isEmpty);
      expect(stored.refreshToken, isEmpty);
      expect(stored.rememberedRefreshToken, 'refresh-soft');
      expect(stored.quickLoginRefreshToken, 'refresh-soft');
      expect(stored.ownerId, 'owner-soft');
      expect(stored.rememberedDisplayName, '趣友A');
      expect(stored.rememberedNicknameCustomized, isTrue);
      expect(stored.rememberedLoginMaskedIdentifier, '138****0001');
      expect(stored.manualLoggedOut, isTrue);
      expect(stored.quickLoginExpiresAtEpochMs, greaterThan(0));
      expect(stored.hasValidQuickLoginCredential, isTrue);
    },
  );

  test('softLogout uses cloud-issued remember TTL for expiry', () async {
    final store = AuthSessionStore(secureStorage: const FlutterSecureStorage());
    await store.saveLoginGrant(
      _grant(<String, dynamic>{
        'accessToken': 'access-ttl',
        'refreshToken': 'refresh-ttl',
        'ownerId': 'owner-ttl',
        'sessionRememberTtlSeconds': 600,
      }),
    );

    final before = DateTime.now().millisecondsSinceEpoch;
    await store.softLogout();
    final stored = await store.read();

    // 过期戳应约为 now + 600s（云端下发 TTL），允许少量执行耗时偏差。
    final expectedMax = before + 600 * 1000 + 5000;
    expect(stored.quickLoginExpiresAtEpochMs, lessThanOrEqualTo(expectedMax));
    expect(
      stored.quickLoginExpiresAtEpochMs,
      greaterThan(before + 600 * 1000 - 5000),
    );
  });

  test(
    'hardLogout (clearSession) wipes credentials and account summary',
    () async {
      final store = AuthSessionStore(
        secureStorage: const FlutterSecureStorage(),
      );
      await store.saveLoginGrant(
        _grant(<String, dynamic>{
          'accessToken': 'access-hard',
          'refreshToken': 'refresh-hard',
          'ownerId': 'owner-hard',
          'identityOrigin': 'phone',
          'accountHint': <String, dynamic>{
            'displayName': '趣友Hard',
            'nicknameCustomized': true,
            'avatarUrl': 'https://cdn.example.com/avatar-hard.png',
            'maskedPhone': '138****0002',
          },
        }),
        rememberedLoginMethod: AuthRememberedLoginMethod.phoneOtp,
      );

      await store.clearSession(manualLogout: true);
      final stored = await store.read();

      expect(stored.refreshToken, isEmpty);
      expect(stored.quickLoginExpiresAtEpochMs, 0);
      expect(stored.hasValidQuickLoginCredential, isFalse);
      expect(stored.rememberedLoginMethod, AuthRememberedLoginMethod.unknown);
      expect(stored.rememberedLoginMaskedIdentifier, isEmpty);
      expect(stored.rememberedDisplayName, isEmpty);
      expect(stored.rememberedAvatarUrl, isEmpty);
      expect(stored.rememberedNicknameCustomized, isFalse);
    },
  );

  test(
    'expired session clears credentials but preserves account summary',
    () async {
      final store = AuthSessionStore(
        secureStorage: const FlutterSecureStorage(),
      );
      await store.saveLoginGrant(
        _grant(<String, dynamic>{
          'accessToken': 'access-expired',
          'refreshToken': 'refresh-expired',
          'ownerId': 'owner-expired',
          'identityOrigin': 'phone',
          'accountHint': <String, dynamic>{
            'displayName': '趣友Expired',
            'nicknameCustomized': true,
            'avatarUrl': 'https://cdn.example.com/avatar-expired.png',
            'maskedPhone': '138****0003',
          },
        }),
        rememberedLoginMethod: AuthRememberedLoginMethod.phoneOtp,
      );

      await store.clearSession(manualLogout: false);
      final stored = await store.read();

      expect(stored.refreshToken, isEmpty);
      expect(stored.rememberedLoginMethod, AuthRememberedLoginMethod.phoneOtp);
      expect(stored.rememberedLoginMaskedIdentifier, '138****0003');
      expect(stored.rememberedDisplayName, '趣友Expired');
      expect(stored.rememberedAvatarUrl, contains('avatar-expired.png'));
      expect(stored.rememberedNicknameCustomized, isTrue);
    },
  );

  test(
    'refresh accountHint replaces summary and explicit empty avatar',
    () async {
      final store = AuthSessionStore(
        secureStorage: const FlutterSecureStorage(),
      );
      await store.saveLoginGrant(
        _grant(<String, dynamic>{
          'accessToken': 'access-old',
          'refreshToken': 'refresh-old',
          'ownerId': 'owner-refresh',
          'identityOrigin': 'phone',
          'accountHint': <String, dynamic>{
            'displayName': '旧昵称',
            'nicknameCustomized': true,
            'avatarUrl': 'https://cdn.example.com/avatar-old.png',
            'maskedPhone': '138****0004',
          },
        }),
        rememberedLoginMethod: AuthRememberedLoginMethod.phoneOtp,
      );

      await store.saveRefreshedAccountHint(
        const AccountHintSnapshot(
          displayName: '系统默认昵称',
          nicknameCustomized: false,
          avatarUrl: '',
          avatarAssetId: '',
          maskedPhone: '138****0005',
          identityOrigin: 'phone',
        ),
      );
      final refreshed = await store.read();

      expect(refreshed.rememberedDisplayName, '系统默认昵称');
      expect(refreshed.rememberedNicknameCustomized, isFalse);
      expect(refreshed.rememberedAvatarUrl, isEmpty);
      expect(refreshed.rememberedLoginMaskedIdentifier, '138****0005');

      await store.saveRefreshedAccountHint(null);
      final unchanged = await store.read();
      expect(unchanged.rememberedDisplayName, '系统默认昵称');
      expect(unchanged.rememberedLoginMaskedIdentifier, '138****0005');
    },
  );

  test('saveLoginGrant(phoneOtp) 记住完整手机号，软退出保留供自动预填', () async {
    final store = AuthSessionStore(secureStorage: const FlutterSecureStorage());
    await store.saveLoginGrant(
      _grant(<String, dynamic>{
        'accessToken': 'access-phone',
        'refreshToken': 'refresh-phone',
        'ownerId': 'owner-phone',
        'identityOrigin': 'phone',
      }),
      rememberedLoginMethod: AuthRememberedLoginMethod.phoneOtp,
      rememberedLoginMaskedIdentifier: '000****0000',
      rememberedLoginIdentifier: _syntheticPhoneIdentifier,
    );

    final afterLogin = await store.read();
    expect(afterLogin.rememberedLoginIdentifier, _syntheticPhoneIdentifier);

    // 软退出保留完整号（过期后再登录可自动预填 + 自动发码）。
    await store.softLogout();
    final afterSoft = await store.read();
    expect(afterSoft.rememberedLoginIdentifier, _syntheticPhoneIdentifier);
    expect(afterSoft.rememberedLoginMaskedIdentifier, '000****0000');
  });

  test('彻底退出清除本机完整手机号', () async {
    final store = AuthSessionStore(secureStorage: const FlutterSecureStorage());
    await store.saveLoginGrant(
      _grant(<String, dynamic>{
        'accessToken': 'access-phone',
        'refreshToken': 'refresh-phone',
        'ownerId': 'owner-phone',
        'identityOrigin': 'phone',
      }),
      rememberedLoginMethod: AuthRememberedLoginMethod.phoneOtp,
      rememberedLoginMaskedIdentifier: '000****0000',
      rememberedLoginIdentifier: _syntheticPhoneIdentifier,
    );

    await store.clearSession(manualLogout: true);
    final stored = await store.read();
    expect(stored.rememberedLoginIdentifier, isEmpty);
  });

  test('非手机号登录方式不持有完整手机号', () async {
    final store = AuthSessionStore(secureStorage: const FlutterSecureStorage());
    await store.saveLoginGrant(
      _grant(<String, dynamic>{
        'accessToken': 'access-wechat',
        'refreshToken': 'refresh-wechat',
        'ownerId': 'owner-wechat',
        'identityOrigin': 'wechat',
      }),
      rememberedLoginMethod: AuthRememberedLoginMethod.wechat,
      rememberedLoginIdentifier: _syntheticPhoneIdentifier,
    );

    final stored = await store.read();
    expect(stored.rememberedLoginIdentifier, isEmpty);
  });
}

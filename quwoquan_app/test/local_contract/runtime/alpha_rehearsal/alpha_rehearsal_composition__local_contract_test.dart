// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-008
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/alpha_rehearsal_install.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_store.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/config/generated/offline_content_bundle_identity.g.dart';
import 'package:quwoquan_app/service/user_service/account/authentication_challenge/adapters/secure_pending_otp_attempt_store.dart';
import 'package:quwoquan_cloud_contracts/generated/values/user/account/authentication_challenge.values.dart';
import 'package:quwoquan_cloud_contracts/generated/values/user/account/account_session.values.dart';

import '../auth/auth_session_store__local_contract_test.dart' as auth_fixture;
import 'alpha_rehearsal_synthetic_login__local_contract_test.dart' as fixture;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test('真实配置同绑定三存储私有组合，auth失败重放与logout不自动复活', () async {
    await auth_fixture.hydrateIsolatedStorageRuntime();
    final space = CloudRuntimeConfig.rehearsalSpace!;
    final files = fixture.PrivateStorage();
    final secure = auth_fixture.PrivateAuthStorage();
    secure.values['auth.pending_otp_attempt.v1'] = 'old-pending-sentinel';
    final oldFile =
        '/synthetic-private/alpha_rehearsal/${offlineContentManifestDigest.replaceAll(':', '_')}_default.json';
    files.files[oldFile] = 'old-rehearsal-sentinel';
    final composition = createAlphaRehearsalComposition(
      space: space,
      currentSpace: () => CloudRuntimeConfig.rehearsalSpace,
      gatewayFactory: () => files,
    );
    addTearDown(composition.dispose);
    final namespace = composition.storageNamespace!;
    final auth = AuthSessionStore.isolated(
      namespace: namespace,
      currentSpace: () => CloudRuntimeConfig.rehearsalSpace,
      secureStorage: secure,
      prefsFactory: () => throw StateError('global prefs forbidden'),
    );
    final pending = SecurePendingOtpAttemptStore.isolated(
      namespace: namespace,
      currentSpace: () => CloudRuntimeConfig.rehearsalSpace,
      storage: secure,
    );
    await auth.read();
    secure.values[namespace.pendingOtpKey] = 'corrupt-private-pending';
    expect(await pending.read(), isNull);
    final ports = composition.synthetic!;
    final label = ports.createIdentityLabel();
    final view = await composition.challengePort!.begin(
      BeginSyntheticChallenge(
        identity: label,
        requestKey: ports.createRequestKey(),
      ),
    );
    final input = CompleteSyntheticChallenge(
      identityLabel: label.value,
      challengeId: view.challengeId,
      confirmationHint: view.confirmationHint,
      requestKey: ports.createRequestKey(),
    );
    final result = await composition.sessionPort!.complete(input);
    secure.failWrite = true;
    await expectLater(auth.saveSyntheticSession(result), throwsStateError);
    secure.failWrite = false;
    expect((await auth.read()).ownerId, isEmpty);
    final replay = await composition.sessionPort!.complete(input);
    expect(replay.toWire(), result.toWire());
    await auth.saveSyntheticSession(replay);
    expect((await auth.read()).ownerId, result.accountId);
    await auth.clearSession(manualLogout: true);
    expect((await auth.read()).ownerId, isEmpty);
    expect(
      (await ports.restore())!.toWire(),
      result.toWire(),
      reason: '持久业务结果不是auth会话authority',
    );
    await auth_fixture.hydrateIsolatedStorageRuntime();
    final next = createAlphaRehearsalComposition(
      space: CloudRuntimeConfig.rehearsalSpace!,
      currentSpace: () => CloudRuntimeConfig.rehearsalSpace,
      gatewayFactory: () => files,
    );
    addTearDown(next.dispose);
    final nextAuth = AuthSessionStore.isolated(
      namespace: next.storageNamespace!,
      currentSpace: () => CloudRuntimeConfig.rehearsalSpace,
      secureStorage: secure,
    );
    expect((await nextAuth.read()).ownerId, isEmpty);
    expect((await next.synthetic!.restore())!.toWire(), result.toWire());
    await expectLater(
      composition.synthetic!.restore(),
      throwsA(isA<SyntheticLoginFailure>()),
    );
    expect(
      secure.calls.where(
        (key) =>
            key == 'auth.install_id' ||
            key == 'auth.pending_otp_attempt.v1' ||
            key.contains('alpha-local'),
      ),
      isEmpty,
    );
    expect(files.calls.where((call) => call.endsWith(oldFile)), isEmpty);
    expect(files.files[oldFile], 'old-rehearsal-sentinel');
    expect(
      secure.values['auth.pending_otp_attempt.v1'],
      'old-pending-sentinel',
    );
  });

  test('错snapshot/store/当前space在gateway构造前拒绝，standard保留默认', () async {
    final wrong = (await fixture.signedRuntime()).rehearsalSpace!;
    var calls = 0;
    expect(
      () => createAlphaRehearsalComposition(
        space: wrong,
        currentSpace: () => wrong,
        gatewayFactory: () {
          calls++;
          return fixture.PrivateStorage();
        },
      ),
      throwsA(isA<Object>()),
    );
    await auth_fixture.hydrateIsolatedStorageRuntime();
    final space = CloudRuntimeConfig.rehearsalSpace!;
    expect(
      () => createAlphaRehearsalComposition(
        space: space,
        currentSpace: () => null,
        gatewayFactory: () {
          calls++;
          return fixture.PrivateStorage();
        },
      ),
      throwsA(isA<Object>()),
    );
    expect(
      () => createAlphaRehearsalComposition(
        space: space,
        currentSpace: () => space,
        store: AlphaRehearsalStore(),
        gatewayFactory: () {
          calls++;
          return fixture.PrivateStorage();
        },
      ),
      throwsA(isA<Object>()),
    );
    expect(calls, 0);
    final standard = await fixture.signedRuntime(
      mode: 'standard',
      instance: 'default',
      expectedSnapshot: offlineContentManifestDigest,
      mutate: (doc) => (doc['rehearsalSpace'] as Map)['snapshotDigest'] =
          offlineContentManifestDigest,
    );
    final composition = createAlphaRehearsalComposition(
      space: standard.rehearsalSpace!,
      currentSpace: () => standard.rehearsalSpace,
      gatewayFactory: fixture.PrivateStorage.new,
    );
    expect(composition.store.instanceId, 'default');
    expect(composition.synthetic, isNull);
    expect(composition.challengePort, isNull);
  });
}

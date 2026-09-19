// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-011.t1
// readiness_case: pending-otp-attempt-secure-recovery-local
import 'dart:convert';
import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/di/login_dependencies.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/config/runtime_package_resolver.dart';
import 'package:quwoquan_app/runtime/config/rehearsal_storage_namespace.dart';
import 'package:quwoquan_app/runtime/config/generated/app_launch_contract.g.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';

import '../../../../runtime/auth/auth_session_store__local_contract_test.dart'
    as storage_fixture;
import '../../../../runtime/alpha_rehearsal/alpha_rehearsal_synthetic_login__local_contract_test.dart'
    as signed;
import '../../../../../support/runtime/config/runtime_package_test_hydration.dart';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/user_service/account/authentication_challenge/adapters/secure_pending_otp_attempt_store.dart';
import 'package:quwoquan_app/service/user_service/account/authentication_challenge/application/public/authentication_challenge_writer.dart';
import 'package:quwoquan_app/service/user_service/account/authentication_challenge/application/public/pending_otp_attempt_store.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  // spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-008
  test('isolated pending坏记录只删新键，旧坏记录与其他空间完全不触达', () async {
    final space = (await signed.signedRuntime()).rehearsalSpace!;
    final namespace = RehearsalStorageNamespace(space);
    final storage = storage_fixture.PrivateAuthStorage();
    storage.values['auth.pending_otp_attempt.v1'] = '{broken-legacy';
    storage.values[namespace.pendingOtpKey] = '{broken-isolated';
    final store = SecurePendingOtpAttemptStore.isolated(
      namespace: namespace,
      currentSpace: () => space,
      storage: storage,
    );
    expect(await store.read(), isNull);
    expect(storage.values.containsKey(namespace.pendingOtpKey), isFalse);
    final attempt = PendingOtpAttempt(
      phone: '',
      maskedPhone: '',
      idempotencyKey: 'isolated-request-00000001',
      deliveryStatus: 'confirming',
      resendDeadlineEpochMs: 0,
      expiresAtEpochMs: DateTime.now()
          .add(const Duration(minutes: 5))
          .millisecondsSinceEpoch,
    );
    await store.write(attempt);
    expect((await store.read())!.idempotencyKey, attempt.idempotencyKey);
    final restarted = (await signed.signedRuntime()).rehearsalSpace!;
    final next = SecurePendingOtpAttemptStore.isolated(
      namespace: RehearsalStorageNamespace(restarted),
      currentSpace: () => restarted,
      storage: storage,
    );
    expect((await next.read())!.idempotencyKey, attempt.idempotencyKey);
    final other = (await signed.signedRuntime(instance: 'space-b'))
        .rehearsalSpace!;
    final otherStore = SecurePendingOtpAttemptStore.isolated(
      namespace: RehearsalStorageNamespace(other),
      currentSpace: () => other,
      storage: storage,
    );
    expect(await otherStore.read(), isNull);
    storage.values[namespace.pendingOtpKey] = jsonEncode({
      ...attempt.toJson(),
      'expiresAtEpochMs': 0,
    });
    expect(await next.read(), isNull);
    expect(storage.values['auth.pending_otp_attempt.v1'], '{broken-legacy');
    expect(
      storage.calls.where(
        (key) =>
            key == 'auth.pending_otp_attempt.v1' || key == 'auth.install_id',
      ),
      isEmpty,
    );
  });

  test('pending晚到坏记录在space切换或dispose后不清键', () async {
    final space = (await signed.signedRuntime()).rehearsalSpace!;
    VerifiedRehearsalSpace? current = space;
    final namespace = RehearsalStorageNamespace(space);
    final storage = storage_fixture.PrivateAuthStorage()
      ..readRelease = Completer<void>();
    storage.values[namespace.pendingOtpKey] = '{broken';
    var active = true;
    final store = SecurePendingOtpAttemptStore.isolated(
      namespace: namespace,
      currentSpace: () => current,
      isActive: () => active,
      storage: storage,
    );
    final pending = expectLater(store.read(), throwsA(isA<Object>()));
    await Future<void>.delayed(Duration.zero);
    current = (await signed.signedRuntime()).rehearsalSpace!;
    storage.readRelease!.complete();
    await pending;
    expect(storage.calls, [namespace.pendingOtpKey]);
    expect(storage.values[namespace.pendingOtpKey], '{broken');
    active = false;
    await expectLater(store.clear(), throwsA(isA<Object>()));
    expect(storage.calls, [namespace.pendingOtpKey]);
  });

  test('pending production provider先消费verified namespace且dispose后拒绝', () async {
    await storage_fixture.hydrateIsolatedStorageRuntime();
    final container = ProviderContainer();
    final store = container.read(pendingOtpAttemptStoreProvider);
    container.dispose();
    await expectLater(store.read(), throwsA(isA<Object>()));
    await hydrateRuntimePackageForTests(environment: 'beta');
    expect(CloudRuntimeConfig.rehearsalSpace, isNull);
  });

  group('pending真实IO观察', () {
    test('同scope Provider注入无隐藏构造，缺失read不算payload，成功删除可幂等', () async {
      await storage_fixture.hydrateIsolatedStorageRuntime();
      final f = storage_fixture.StorageObservationFixture(
        CloudRuntimeConfig.rehearsalSpace!,
      );
      final storage = storage_fixture.PrivateAuthStorage();
      storage.values['auth.pending_otp_attempt.v1'] = '{legacy-broken';
      final container = ProviderContainer(
        overrides: [
          rehearsalStorageObserverProvider.overrideWithValue(f.observer),
        ],
      );
      expect(
        container.read(rehearsalStorageObserverProvider),
        same(f.observer),
      );
      expect(
        f.observer.read().pending.state,
        RehearsalConsumerObservationState.notObserved,
      );
      expect(
        f.observer.read().auth.state,
        RehearsalConsumerObservationState.notObserved,
      );
      final productionStore = container.read(pendingOtpAttemptStoreProvider);
      expect(
        f.observer.read().pending.state,
        RehearsalConsumerObservationState.constructed,
      );
      expect(
        f.observer.read().auth.state,
        RehearsalConsumerObservationState.notObserved,
      );
      container.dispose();
      await expectLater(productionStore.read(), throwsA(isA<Object>()));
      final ns = RehearsalStorageNamespace(f.space);
      SecurePendingOtpAttemptStore create() =>
          SecurePendingOtpAttemptStore.isolated(
            namespace: ns,
            currentSpace: () => f.current,
            storage: storage,
            observer: f.observer,
          );
      final store = create();
      expect(storage.calls, isEmpty);
      expect(await store.read(), isNull);
      expect(f.observer.read().pending.successfulOperations, isEmpty);
      final attempt = PendingOtpAttempt(
        phone: '',
        maskedPhone: '',
        idempotencyKey: 'private-request-00000001',
        deliveryStatus: 'confirming',
        resendDeadlineEpochMs: 0,
        expiresAtEpochMs: DateTime.now()
            .add(const Duration(minutes: 5))
            .millisecondsSinceEpoch,
      );
      await store.write(attempt);
      await store.read();
      await store.clear();
      await store.clear();
      expect(
        f.observer.read().pending.successfulOperations,
        containsAll(RehearsalSuccessfulOperation.values),
      );
      final calls = storage.calls.length;
      f.observer.read();
      f.observer.read();
      expect(storage.calls.length, calls);
      store.dispose();
      final next = create();
      store.dispose();
      expect(
        f.observer.read().pending.state,
        RehearsalConsumerObservationState.constructed,
      );
      expect(storage.values['auth.pending_otp_attempt.v1'], '{legacy-broken');
      expect(
        storage.calls.where((k) => k == 'auth.pending_otp_attempt.v1'),
        isEmpty,
      );
      next.dispose();
      await hydrateRuntimePackageForTests(environment: 'beta');
    });

    for (final operation in RehearsalSuccessfulOperation.values) {
      for (final failure in [
        'storage',
        'space',
        'attempt',
        'generation',
        'dispose',
      ]) {
        test('$operation失败或迟到$failure无成功观察', () async {
          final f = storage_fixture.StorageObservationFixture(
            (await signed.signedRuntime()).rehearsalSpace!,
          );
          final ns = RehearsalStorageNamespace(f.space);
          final storage = storage_fixture.PrivateAuthStorage();
          storage.values[ns.pendingOtpKey] = '{malformed';
          final store = SecurePendingOtpAttemptStore.isolated(
            namespace: ns,
            currentSpace: () => f.current,
            storage: storage,
            observer: f.observer,
          );
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
          final attempt = PendingOtpAttempt(
            phone: '',
            maskedPhone: '',
            idempotencyKey: 'private-request-00000001',
            deliveryStatus: 'confirming',
            resendDeadlineEpochMs: 0,
            expiresAtEpochMs: 1,
          );
          Future<void> run() async {
            if (operation == RehearsalSuccessfulOperation.read) {
              await store.read();
            }
            if (operation == RehearsalSuccessfulOperation.write) {
              await store.write(attempt);
            }
            if (operation == RehearsalSuccessfulOperation.delete) {
              await store.clear();
            }
          }

          final rejected = expectLater(run(), throwsA(isA<Object>()));
          await Future<void>.delayed(Duration.zero);
          if (failure == 'space') f.current = null;
          if (failure == 'attempt') f.attempt = 'private-attempt-2';
          if (failure == 'generation') f.generation = '2';
          if (failure == 'dispose') store.dispose();
          if (failure != 'storage') release.complete();
          await rejected;
          expect(f.observer.read().pending.successfulOperations, isEmpty);
          expect(storage.calls, hasLength(1));
          store.dispose();
        });
      }
    }
  });

  setUp(() {
    FlutterSecureStorage.setMockInitialValues(<String, String>{});
  });

  test('pending OTP attempt round-trips without persisting an OTP', () async {
    const secureStorage = FlutterSecureStorage();
    const store = SecurePendingOtpAttemptStore(storage: secureStorage);
    final now = DateTime.now();
    final attempt = PendingOtpAttempt(
      phone: '00000000000',
      maskedPhone: '000****0000',
      idempotencyKey: 'otp-idempotency-0000000000000001',
      challengeId: 'otp_ch_1',
      requestId: 'otp_req_1',
      deliveryStatus: 'confirming',
      resendDeadlineEpochMs: now
          .add(const Duration(seconds: 60))
          .millisecondsSinceEpoch,
      expiresAtEpochMs: now
          .add(const Duration(minutes: 5))
          .millisecondsSinceEpoch,
    );

    await store.write(attempt);
    final restored = await store.read();
    expect(restored?.idempotencyKey, attempt.idempotencyKey);
    expect(restored?.phone, attempt.phone);
    expect(restored?.deliveryStatus, 'confirming');

    final securePayload = (await secureStorage.readAll()).values.single;
    expect(securePayload, isNot(contains('otpCode')));
    expect(securePayload, isNot(contains('verificationCode')));
    expect(attempt.toJson().keys, isNot(contains('otp')));
  });

  test(
    'expired or malformed pending attempts are removed fail-closed',
    () async {
      const secureStorage = FlutterSecureStorage();
      const store = SecurePendingOtpAttemptStore(storage: secureStorage);
      final expired = PendingOtpAttempt(
        phone: '00000000000',
        maskedPhone: '000****0000',
        idempotencyKey: 'otp-idempotency-0000000000000002',
        deliveryStatus: 'queued',
        resendDeadlineEpochMs: DateTime.now().millisecondsSinceEpoch,
        expiresAtEpochMs: DateTime.now()
            .subtract(const Duration(seconds: 1))
            .millisecondsSinceEpoch,
      );
      await store.write(expired);
      expect(await store.read(), isNull);
      expect(await secureStorage.readAll(), isEmpty);

      FlutterSecureStorage.setMockInitialValues(<String, String>{
        'auth.pending_otp_attempt.v1': jsonEncode(<String, Object?>{
          'phone': '00000000000',
          'idempotencyKey': 'too-short',
        }),
      });
      expect(await store.read(), isNull);
      expect(await secureStorage.readAll(), isEmpty);
    },
  );

  test('SendOtp idempotency key is opaque random 128-bit material', () {
    final keys = List<String>.generate(64, (_) => newOtpIdempotencyKey());
    expect(keys.toSet(), hasLength(keys.length));
    for (final key in keys) {
      expect(base64Url.decode(base64Url.normalize(key)), hasLength(16));
      expect(key, isNot(contains('00000000000')));
    }
  });
}

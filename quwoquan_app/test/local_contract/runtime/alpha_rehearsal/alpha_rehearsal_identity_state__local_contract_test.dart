// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-008

import 'package:flutter_test/flutter_test.dart';

import 'package:quwoquan_app/runtime/alpha_rehearsal/executor/rehearsal_cloud_operation_executor.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_identity.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_ports.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_store.dart';
import 'package:quwoquan_app/runtime/auth/rehearsal_auth_port.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

const String _syntheticPhoneIdentifier = '00000000000';
void main() {
  test('本地 OTP 登录写入演练身份，重启可恢复，错误码不匹配失败', () async {
    final persistence = MemoryRehearsalPersistence();
    final store = AlphaRehearsalStore(persistence: persistence);
    final executor = AlphaRehearsalCloudOperationExecutor(store: store);
    const publicContext = CloudOperationInvocationContext(
      surfaceId: 'login',
      clientPageId: 'login',
      actor: CloudOperationActorContext(),
    );

    final otp = await executor.send<OtpChallengeIssueResult>(
      appCloudOperationContracts['user.authentication_challenge.SendOtp']!,
      context: publicContext,
      requestEncoder: () => const CloudOperationRequestPayload(
        body: <String, Object?>{'phone': _syntheticPhoneIdentifier},
      ),
      responseDecoder: (wire) =>
          OtpChallengeIssueResult.fromWire(wire! as Map<String, Object?>),
    );
    expect(otp.deliveryStatus.wireName, 'delivered');
    expect(store.lastIssuedOtp, rehearsalOtpCode);

    await expectLater(
      executor.send<AuthSessionGrant>(
        appCloudOperationContracts['user.account_session.LoginWithPhone']!,
        context: publicContext,
        requestEncoder: () => const CloudOperationRequestPayload(
          body: <String, Object?>{
            'phone': _syntheticPhoneIdentifier,
            'otpCode': '111111',
          },
        ),
        responseDecoder: (wire) =>
            AuthSessionGrant.fromWire(wire! as Map<String, Object?>),
      ),
      throwsA(isA<Object>()),
    );

    final grant = await executor.send<AuthSessionGrant>(
      appCloudOperationContracts['user.account_session.LoginWithPhone']!,
      context: publicContext,
      requestEncoder: () => const CloudOperationRequestPayload(
        body: <String, Object?>{
          'phone': _syntheticPhoneIdentifier,
          'otpCode': rehearsalOtpCode,
        },
      ),
      responseDecoder: (wire) =>
          AuthSessionGrant.fromWire(wire! as Map<String, Object?>),
    );
    expect(grant.accessToken, startsWith(rehearsalCredentialPrefix));
    expect(grant.identityOrigin, rehearsalIdentityOrigin);

    final auth = AlphaRehearsalAuth(store);
    await auth.applyGrant(grant, installId: 'install-1');
    final restoredStore = AlphaRehearsalStore(persistence: persistence);
    final restoredAuth = AlphaRehearsalAuth(restoredStore);
    final restored = await restoredAuth.restore(installId: 'install-1');
    expect(restored?.ownerId, grant.ownerId);
    expect(restored?.accessToken, startsWith(rehearsalCredentialPrefix));

    await restoredAuth.clear();
    final afterLogout = await AlphaRehearsalAuth(
      AlphaRehearsalStore(persistence: persistence),
    ).restore(installId: 'install-1');
    expect(afterLogout, isNull);
  });

  test('OTP 必须已发送且同 owner，过期/重用/尝试耗尽拒绝，身份稳定', () async {
    var now = DateTime.utc(2026, 9, 12);
    final p = MemoryRehearsalPersistence();
    final store = AlphaRehearsalStore(persistence: p);
    var executor = AlphaRehearsalCloudOperationExecutor(
      store: store,
      now: () => now,
    );
    CloudOperationInvocationContext context(String device) =>
        CloudOperationInvocationContext(
          surfaceId: 'login',
          clientPageId: 'login',
          actor: CloudOperationActorContext(deviceActorId: device),
        );
    Future<Object?> issue() => executor.send<Object?>(
      appCloudOperationContracts['user.authentication_challenge.SendOtp']!,
      context: context('a'),
      requestEncoder: () => const CloudOperationRequestPayload(
        body: {'phone': _syntheticPhoneIdentifier},
      ),
      responseDecoder: (w) => w,
    );
    Future<AuthSessionGrant> login({
      String device = 'a',
      String code = rehearsalOtpCode,
    }) => executor.send<AuthSessionGrant>(
      appCloudOperationContracts['user.account_session.LoginWithPhone']!,
      context: context(device),
      requestEncoder: () => CloudOperationRequestPayload(
        body: {'phone': _syntheticPhoneIdentifier, 'otpCode': code},
      ),
      responseDecoder: (w) =>
          AuthSessionGrant.fromWire(w! as Map<String, Object?>),
    );
    await expectLater(login(), throwsA(isA<Object>()));
    await issue();
    await expectLater(login(device: 'b'), throwsA(isA<Object>()));
    final first = await login();
    await expectLater(login(), throwsA(isA<Object>()));
    await issue();
    now = now.add(const Duration(minutes: 5));
    await expectLater(login(), throwsA(isA<Object>()));
    await issue();
    for (var n = 0; n < 5; n++) {
      await expectLater(login(code: 'bad'), throwsA(isA<Object>()));
    }
    expect(store.otpChallenges.values.last['attempts'], 5);
    await expectLater(login(), throwsA(isA<Object>()));
    executor = AlphaRehearsalCloudOperationExecutor(
      store: AlphaRehearsalStore(persistence: p),
      now: () => now,
    );
    await issue();
    final restored = await login();
    expect(restored.ownerId, first.ownerId);
    expect(restored.activePersona?.personaId, first.activePersona?.personaId);
  });

  test('换 snapshot digest 不恢复旧演练空间', () async {
    final persistence = MemoryRehearsalPersistence();
    final first = AlphaRehearsalStore(persistence: persistence);
    await first.commit(() {
      first.currentOwnerId = 'rehearsal.account.old';
      first.identities['rehearsal.account.old'] = <String, Object?>{
        'ownerId': 'rehearsal.account.old',
        'personaId': 'rehearsal.persona.old',
      };
    });
    final next = AlphaRehearsalStore(
      persistence: persistence,
      snapshotDigest: 'sha256:other',
    );
    await expectLater(next.ensureLoaded(), throwsA(isA<Object>()));
    expect(next.currentOwnerId, isNull);
    expect(next.identities, isEmpty);
  });
}

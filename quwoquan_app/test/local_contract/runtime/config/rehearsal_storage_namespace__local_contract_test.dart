// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-008
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/config/rehearsal_storage_namespace.dart';
import 'package:quwoquan_app/runtime/config/runtime_package_resolver.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_space_binding.dart';

// 复用真实签名/resolver fixture，不伪造 VerifiedRehearsalSpace。
import '../alpha_rehearsal/alpha_rehearsal_synthetic_login__local_contract_test.dart'
    as fixture;

void main() {
  test('旧算法golden保持，新增installId独立键且Alpha仅委托', () async {
    final runtime = await fixture.signedRuntime();
    final space = runtime.rehearsalSpace!;
    final namespace = RehearsalStorageNamespace(space);
    const oldAuth =
        'alpha.rehearsal.cc0acb05829f65b99046ce7ca8fae48cbc93030758e69a2c04751aacaea373e8';
    expect(namespace.authNamespace, oldAuth);
    expect(namespace.pendingOtpKey, '$oldAuth.pending_otp_attempt');
    expect(namespace.installIdKey, '$oldAuth.install_id');
    expect(namespace.installIdKey, isNot('auth.install_id'));
    final alpha = RehearsalSpaceBinding.verified(space);
    expect(alpha.isolatedAuthNamespace, namespace.authNamespace);
    expect(alpha.isolatedPendingOtpKey, namespace.pendingOtpKey);
    namespace.requireCurrent(space);
  });

  test('同空间新verified对象键稳定但旧requireCurrent拒绝，缺失也拒绝', () async {
    final first = (await fixture.signedRuntime()).rehearsalSpace!;
    final restart = (await fixture.signedRuntime()).rehearsalSpace!;
    final a = RehearsalStorageNamespace(first);
    final b = RehearsalStorageNamespace(restart);
    expect(a.authNamespace, b.authNamespace);
    expect(a.pendingOtpKey, b.pendingOtpKey);
    expect(a.installIdKey, b.installIdKey);
    expect(() => a.requireCurrent(restart), throwsA(isA<Object>()));
    expect(() => a.requireCurrent(null), throwsA(isA<Object>()));
    b.requireCurrent(restart);
  });

  test('snapshot和instance任一改变全部键隔离', () async {
    final a = RehearsalStorageNamespace(
      (await fixture.signedRuntime()).rehearsalSpace!,
    );
    final b = RehearsalStorageNamespace(
      (await fixture.signedRuntime(instance: 'space-b')).rehearsalSpace!,
    );
    final newDigest = 'sha256:${'e' * 64}';
    final changed = await fixture.signedRuntime(
      expectedSnapshot: newDigest,
      mutate: (doc) =>
          (doc['rehearsalSpace'] as Map)['snapshotDigest'] = newDigest,
    );
    final c = RehearsalStorageNamespace(changed.rehearsalSpace!);
    for (final next in [b, c]) {
      expect(next.authNamespace, isNot(a.authNamespace));
      expect(next.pendingOtpKey, isNot(a.pendingOtpKey));
      expect(next.installIdKey, isNot(a.installIdKey));
    }
  });

  test('standard/default拒绝，非法source不能获得verified空间', () async {
    final standard = (await fixture.signedRuntime(
      mode: 'standard',
      instance: 'default',
    )).rehearsalSpace!;
    expect(() => RehearsalStorageNamespace(standard), throwsA(isA<Object>()));
    final alpha = RehearsalSpaceBinding.verified(standard);
    expect(alpha.instanceId, 'default');
    expect(alpha.storageNamespace, isNull);
    await expectLater(
      fixture.signedRuntime(instance: 'default'),
      throwsA(isA<RuntimePackageValidationException>()),
    );
    await expectLater(
      fixture.signedRuntime(mutate: (doc) => doc['contentSource'] = 'remote'),
      throwsA(isA<RuntimePackageValidationException>()),
    );
  });
}

// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-008
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/alpha_rehearsal_observation.dart';

void main() {
  const binding =
      'sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb';
  const snapshot =
      'sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd';

  late List<List<Object?>> calls;
  late AlphaRehearsalObservation observation;

  Future<Object?> invoke(String method, [dynamic arguments]) async {
    calls.add(<Object?>[method, arguments]);
    return method == 'sealObservation'
        ? 'sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee'
        : null;
  }

  AlphaRehearsalObservation install({
    required String caseId,
    String attemptId = 'attempt-1',
    String generation = '1',
  }) {
    return AlphaRehearsalObservation.installForTest(
      caseId: caseId,
      attemptId: attemptId,
      generation: generation,
      binding: binding,
      snapshotDigest: snapshot,
      invoke: invoke,
    );
  }

  setUp(() {
    calls = <List<Object?>>[];
    AlphaRehearsalObservation.current?.invalidate();
  });

  tearDown(() {
    AlphaRehearsalObservation.current?.invalidate();
  });

  test('login-success 先 admission 再封存会话读回，不注入 PID 或 seal 时间', () async {
    observation = install(caseId: 'login-success');
    expect(identical(AlphaRehearsalObservation.current, observation), isTrue);
    await observation.requireAdmission();
    await observation.recordSessionEstablished(includeEditableControl: true);
    expect(calls.map((call) => call.first), [
      'bindStartupObservation',
      'requireObservationAdmission',
      'recordRedactedInput',
      'sealObservation',
    ]);
    final sealed = calls.last[1] as Map<String, Object?>;
    expect(sealed.containsKey('processId'), isFalse);
    expect(sealed.containsKey('sealedAtMonotonicMs'), isFalse);
    expect(sealed['observations'], [
      {
        'source': 'ui-control',
        'status': 'observed',
        'detail': 'unique-editable-control',
      },
      {
        'source': 'rehearsal-session-readback',
        'status': 'observed',
        'detail': 'session-established',
      },
    ]);
  });

  test('login-error 只接受 mismatch 后的可恢复错误读回', () async {
    observation = install(caseId: 'login-error');
    await observation.requireAdmission();
    await observation.recordRecoverableAuthError();
    final sealed = calls.last[1] as Map<String, Object?>;
    expect(sealed['observations'], [
      {
        'source': 'ui-control',
        'status': 'observed',
        'detail': 'unique-editable-control',
      },
      {
        'source': 'rehearsal-auth-error-readback',
        'status': 'observed',
        'detail': 'recoverable-error-observed',
      },
    ]);
  });

  test('local-write 与 private-continuation 分别封存 command-query 读回', () async {
    observation = install(caseId: 'local-write');
    await observation.recordLikeCommandQueryReadback();
    expect((calls.single[1] as Map)['observations'], [
      {
        'source': 'local-command-query-readback',
        'status': 'observed',
        'detail': 'command-query-readback',
      },
    ]);
    observation.invalidate();
    observation = install(caseId: 'private-continuation');
    await observation.recordLikeCommandQueryReadback();
    expect((calls.last[1] as Map)['observations'], [
      {
        'source': 'continuation-query-readback',
        'status': 'observed',
        'detail': 'continued-once-readback',
      },
    ]);
  });

  test('拒绝边界按 catalog source 记一次 attemptCount', () async {
    observation = install(caseId: 'network-refusal');
    observation.recordRefusal('native-network-attempt');
    await Future<void>.delayed(Duration.zero);
    expect((calls.single[1] as Map)['observations'], [
      {
        'source': 'native-network-attempt',
        'status': 'observed',
        'detail': 'refused-at-side-effect-boundary',
        'attemptCount': 1,
      },
    ]);
  });

  test('失效后禁止继续采集，也不把旧 current 留给下一 scope', () {
    observation = install(caseId: 'local-write');
    observation.invalidate();
    expect(AlphaRehearsalObservation.current, isNull);
    expect(
      () => observation.recordRefusal('native-network-attempt'),
      throwsStateError,
    );
  });
}

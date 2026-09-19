import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/generated/values/user/account/authentication_challenge.values.dart';
import 'package:quwoquan_cloud_contracts/generated/values/user/account/account_session.values.dart';

// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-013
void main() {
  final identity = 'alpha-synthetic:${'a' * 32}';
  test('正式生成七类型解码与typed失败，不含真实凭据', () {
    final label = SyntheticIdentityLabel.fromWire({'value': identity});
    expect(
      BeginSyntheticChallenge.fromWire({
        'identity': label.toWire(),
        'requestKey': 'b' * 32,
      }).identity.value,
      identity,
    );
    expect(
      SyntheticChallengeView.fromWire({
        'challengeId': 'alpha-challenge:${'a' * 32}',
        'confirmationHint': 'alpha-rehearsal-confirm',
        'expiresInSeconds': 300,
      }).expiresInSeconds,
      300,
    );
    expect(
      SyntheticLoginEvidence.fromWire({
        'identityLabel': identity,
        'confirmationHint': 'alpha-rehearsal-confirm',
      }).identityLabel,
      identity,
    );
    expect(
      CompleteSyntheticChallenge.fromWire({
        'identityLabel': identity,
        'challengeId': 'alpha-challenge:${'a' * 32}',
        'confirmationHint': 'alpha-rehearsal-confirm',
        'requestKey': 'a' * 32,
      }).identityLabel,
      identity,
    );
    expect(
      SyntheticSessionResult.fromWire({
        'accountId': 'alpha-account:${'a' * 32}',
        'personaId': 'alpha-persona:${'b' * 32}',
      }).toWire().keys,
      unorderedEquals(['accountId', 'personaId']),
    );
    expect(
      SyntheticLoginFailure.fromWire({'reason': 'expired'}).reason,
      SyntheticLoginFailureReason.expired,
    );
  });
  test('受限错误确认可进入typed端口但不能作为展示或公开证据', () {
    final input = <String, Object?>{
      'identityLabel': identity,
      'challengeId': 'alpha-challenge:${'a' * 32}',
      'confirmationHint': 'alpha-rehearsal-reject',
      'requestKey': 'b' * 32,
    };
    expect(
      CompleteSyntheticChallenge.fromWire(input).confirmationHint,
      'alpha-rehearsal-reject',
    );
    expect(
      () => SyntheticChallengeView.fromWire({
        'challengeId': input['challengeId'],
        'confirmationHint': input['confirmationHint'],
        'expiresInSeconds': 300,
      }),
      throwsA(anything),
    );
    expect(
      () => SyntheticLoginEvidence.fromWire({
        'identityLabel': identity,
        'confirmationHint': input['confirmationHint'],
      }),
      throwsA(anything),
    );
    for (final value in <Object?>[
      null,
      1,
      '123456',
      '00000000000',
      'synthetic.invalid',
      'alpha-rehearsal-unknown',
      'alpha-rehearsal-${'a' * 100}',
      ' alpha-rehearsal-reject',
      'alpha-rehearsal-reject\n',
      'alpha-rehearsal-ｒｅｊｅｃｔ',
    ]) {
      expect(
        () => CompleteSyntheticChallenge.fromWire({
          ...input,
          'confirmationHint': value,
        }),
        throwsA(anything),
      );
    }
  });
  test('非法值缺失额外字段错类型及Unicode全部拒绝', () {
    for (final value in <Object?>[
      null,
      1,
      true,
      ' $identity',
      '$identity ',
      '$identity\n',
      '０００００００００００',
      '00000000000',
      'alpha-synthetic:${'A' * 32}',
    ]) {
      expect(
        () => SyntheticIdentityLabel.fromWire({'value': value}),
        throwsA(anything),
      );
    }
    expect(() => SyntheticIdentityLabel.fromWire({}), throwsA(anything));
    expect(
      () => SyntheticIdentityLabel.fromWire({'value': identity, 'phone': 'x'}),
      throwsA(anything),
    );
    expect(
      () => BeginSyntheticChallenge.fromWire({
        'identity': {'value': identity, 'unknown': true},
        'requestKey': 'b' * 32,
      }),
      throwsA(anything),
    );
    expect(
      () => BeginSyntheticChallenge.fromWire({
        'identity': null,
        'requestKey': 'b' * 32,
      }),
      throwsA(anything),
    );
    expect(
      () => SyntheticLoginFailure.fromWire({'reason': 'unknown'}),
      throwsA(anything),
    );
    expect(
      () => SyntheticLoginEvidence.fromWire({
        'identityLabel': identity,
        'confirmationHint': '123456',
      }),
      throwsA(anything),
    );
    for (final seconds in [0, 301]) {
      expect(
        () => SyntheticChallengeView.fromWire({
          'challengeId': 'alpha-challenge:${'a' * 32}',
          'confirmationHint': 'alpha-rehearsal-confirm',
          'expiresInSeconds': seconds,
        }),
        throwsA(anything),
      );
    }
  });
}

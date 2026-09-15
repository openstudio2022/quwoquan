// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-013
import 'dart:async';
import 'dart:convert';

import 'package:crypto/crypto.dart' as crypto;
import 'package:cryptography/cryptography.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/handlers/synthetic_login_ports.dart';
import 'package:quwoquan_app/runtime/config/runtime_package_resolver.dart';
import 'package:quwoquan_app/runtime/platform/file_storage_gateway.dart';
import 'package:quwoquan_cloud_contracts/generated/values/user/account/authentication_challenge.values.dart';
import 'package:quwoquan_cloud_contracts/generated/values/user/account/account_session.values.dart';

class PrivateStorage implements FileStorageGateway, AtomicFileStorageGateway {
  final files = <String, String>{};
  final calls = <String>[];
  bool fail = false;
  Completer<void>? entered;
  Completer<void>? release;
  @override
  bool get isSupported => true;
  @override
  Future<String> applicationSupportPath() async => '/synthetic-private';
  @override
  Future<void> ensureDirectory(String path) async {
    calls.add('dir:$path');
  }

  @override
  Future<bool> exists(String path) async {
    calls.add('exists:$path');
    return files.containsKey(path);
  }

  @override
  Future<String> readAsString(String path) async {
    calls.add('read:$path');
    return files[path]!;
  }

  @override
  Future<void> writeAsStringAtomically(
    String path,
    String contents, {
    void Function()? beforeCommit,
  }) async {
    entered?.complete();
    if (release != null) await release!.future;
    beforeCommit?.call();
    if (fail) throw StateError('injected');
    calls.add('write:$path');
    files[path] = contents;
  }

  @override
  Future<void> delete(String path) async {
    calls.add('delete:$path');
    files.remove(path);
  }

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      throw StateError('Unexpected I/O');
}

final snapshot = 'sha256:${'d' * 64}';
Future<ResolvedRuntimePackage> signedRuntime({
  String instance = 'space-a',
  String mode = 'isolated',
  String? expectedSnapshot,
  void Function(Map<String, Object?>)? mutate,
}) async {
  final algorithm = Ed25519();
  final key = await algorithm.newKeyPair();
  final keys = {'offline': base64.encode((await key.extractPublicKey()).bytes)};
  String digest(Object value) =>
      'sha256:${crypto.sha256.convert(utf8.encode(canonicalJsonEncode(value)))}';
  final trust = <String, Object?>{
    'schema': 'app-runtime-config-trust',
    'buildProfile': 'nonprod',
    'signatureAlgorithm': 'ed25519',
    'trustedPublicKeys': keys,
  };
  final doc = <String, Object?>{
    'schema': 'app-offline-bootstrap-document',
    'environment': 'alpha',
    'buildProfile': 'nonprod',
    'target': 'alpha-local',
    'launchPolicy': 'test_live',
    'contentSource': 'bundled_snapshot',
    'sourceGitSha': 'a' * 40,
    'sourceTreeDigest': 'sha256:${'b' * 64}',
    'trustEnvelopeDigest': digest(trust),
    'rehearsalSpace': {
      'mode': mode,
      'snapshotDigest': snapshot,
      'instanceId': instance,
    },
    'runtime': {'appRuntimeEnv': 'alpha'},
    'payloadDigest': '',
    'signatureAlgorithm': 'ed25519',
    'signatureKeyId': 'offline',
    'trustedPublicKeys': keys,
  };
  mutate?.call(doc);
  doc['payloadDigest'] = digest(doc);
  doc['signature'] = base64.encode(
    (await algorithm.sign(
      utf8.encode(canonicalJsonEncode(doc)),
      keyPair: key,
    )).bytes,
  );
  return RuntimePackageResolver().resolve(
    runtimePackage: doc,
    expectedTarget: 'alpha-local',
    trustedBuildProfile: 'nonprod',
    trustedPublicKeys: keys,
    expectedOfflineSnapshotDigest: expectedSnapshot ?? snapshot,
  );
}

Matcher failure(SyntheticLoginFailureReason reason) =>
    isA<SyntheticLoginFailure>().having((e) => e.reason, 'reason', reason);
void main() {
  late ResolvedRuntimePackage runtime;
  late ResolvedRuntimePackage? current;
  late PrivateStorage storage;
  late AlphaSyntheticLoginPorts ports;
  late DateTime now;
  setUp(() async {
    runtime = await signedRuntime();
    current = runtime;
    storage = PrivateStorage();
    now = DateTime.utc(2026, 9, 13);
    ports = AlphaSyntheticLoginPorts(
      space: runtime.rehearsalSpace!,
      currentSpace: () => current?.rehearsalSpace,
      gateway: storage,
      now: () => now,
    );
  });
  BeginSyntheticChallenge beginInput(SyntheticIdentityLabel label) =>
      BeginSyntheticChallenge(
        identity: label,
        requestKey: ports.createRequestKey(),
      );
  CompleteSyntheticChallenge completeInput(
    SyntheticIdentityLabel label,
    SyntheticChallengeView view, {
    String? key,
  }) => CompleteSyntheticChallenge(
    identityLabel: label.value,
    challengeId: view.challengeId,
    confirmationHint: view.confirmationHint,
    requestKey: key ?? ports.createRequestKey(),
  );
  CompleteSyntheticChallenge rejectInput(
    SyntheticIdentityLabel label,
    SyntheticChallengeView view, {
    String? key,
  }) => CompleteSyntheticChallenge(
    identityLabel: label.value,
    challengeId: view.challengeId,
    confirmationHint: 'alpha-rehearsal-reject',
    requestKey: key ?? ports.createRequestKey(),
  );
  Map<String, dynamic> persistedChallenge(String id) {
    final envelope = jsonDecode(storage.files.values.single) as Map;
    return Map<String, dynamic>.from(
      ((envelope['records'] as Map)['synthetic.challenges'] as Map)[id] as Map,
    );
  }

  test('正式reject正确identity逐次1..5锁定，错误重放幂等且跨payload冲突，重启保持锁定', () async {
    final label = ports.createIdentityLabel();
    final view = await ports.begin(beginInput(label));
    final requests = <CompleteSyntheticChallenge>[];
    for (var attempt = 1; attempt <= 5; attempt++) {
      final command = rejectInput(label, view);
      requests.add(command);
      final reason = attempt == 5
          ? SyntheticLoginFailureReason.attemptsexceeded
          : SyntheticLoginFailureReason.mismatch;
      await expectLater(ports.complete(command), throwsA(failure(reason)));
      expect(persistedChallenge(view.challengeId)['attempts'], attempt);
      await expectLater(ports.complete(command), throwsA(failure(reason)));
      expect(persistedChallenge(view.challengeId)['attempts'], attempt);
      expect(persistedChallenge(view.challengeId)['used'], false);
      expect(await ports.restore(), isNull);
    }
    await expectLater(
      ports.complete(
        completeInput(label, view, key: requests.first.requestKey),
      ),
      throwsA(failure(SyntheticLoginFailureReason.conflict)),
    );
    final restartedRuntime = await signedRuntime();
    final restarted = AlphaSyntheticLoginPorts(
      space: restartedRuntime.rehearsalSpace!,
      currentSpace: () => restartedRuntime.rehearsalSpace,
      gateway: storage,
      now: () => now,
    );
    await expectLater(
      restarted.complete(completeInput(label, view)),
      throwsA(failure(SyntheticLoginFailureReason.attemptsexceeded)),
    );
    await expectLater(
      restarted.complete(requests.first),
      throwsA(failure(SyntheticLoginFailureReason.mismatch)),
    );
    expect(persistedChallenge(view.challengeId)['attempts'], 5);
    expect(await restarted.restore(), isNull);
  });

  test('reject写失败不保存attempt和身份，new store重试后锁定前confirm成功', () async {
    final label = ports.createIdentityLabel();
    final view = await ports.begin(beginInput(label));
    final command = rejectInput(label, view);
    final before = Map.of(storage.files);
    storage.fail = true;
    await expectLater(
      ports.complete(command),
      throwsA(failure(SyntheticLoginFailureReason.storageunavailable)),
    );
    expect(storage.files, before);
    expect(persistedChallenge(view.challengeId)['attempts'], 0);
    storage.fail = false;
    final restartedRuntime = await signedRuntime();
    final restarted = AlphaSyntheticLoginPorts(
      space: restartedRuntime.rehearsalSpace!,
      currentSpace: () => restartedRuntime.rehearsalSpace,
      gateway: storage,
      now: () => now,
    );
    await expectLater(
      restarted.complete(command),
      throwsA(failure(SyntheticLoginFailureReason.mismatch)),
    );
    expect(persistedChallenge(view.challengeId)['attempts'], 1);
    expect(await restarted.restore(), isNull);
    final success = await restarted.complete(completeInput(label, view));
    expect(success.accountId, startsWith('alpha-account:'));
    expect(persistedChallenge(view.challengeId)['used'], true);
    expect((await restarted.restore())!.toWire(), success.toWire());
  });

  test('并发相同reject只计一次，并发不同request只计到五次且无身份', () async {
    final label = ports.createIdentityLabel();
    final view = await ports.begin(beginInput(label));
    final first = rejectInput(label, view);
    await Future.wait(
      List.generate(
        4,
        (_) => expectLater(
          ports.complete(first),
          throwsA(failure(SyntheticLoginFailureReason.mismatch)),
        ),
      ),
    );
    expect(persistedChallenge(view.challengeId)['attempts'], 1);
    final commands = List.generate(6, (_) => rejectInput(label, view));
    await Future.wait(
      commands.map(
        (command) => expectLater(
          ports.complete(command),
          throwsA(isA<SyntheticLoginFailure>()),
        ),
      ),
    );
    expect(persistedChallenge(view.challengeId)['attempts'], 5);
    expect(persistedChallenge(view.challengeId)['used'], false);
    expect(await ports.restore(), isNull);
  });

  test('reject慢写跨space或同space新runtime或dispose均在提交前拒绝', () async {
    for (final change in ['space', 'runtime', 'dispose']) {
      final selected = await signedRuntime();
      ResolvedRuntimePackage? active = selected;
      final private = PrivateStorage();
      final local = AlphaSyntheticLoginPorts(
        space: selected.rehearsalSpace!,
        currentSpace: () => active?.rehearsalSpace,
        gateway: private,
        now: () => now,
      );
      final label = local.createIdentityLabel();
      final view = await local.begin(
        BeginSyntheticChallenge(
          identity: label,
          requestKey: local.createRequestKey(),
        ),
      );
      final input = CompleteSyntheticChallenge(
        identityLabel: label.value,
        challengeId: view.challengeId,
        confirmationHint: 'alpha-rehearsal-reject',
        requestKey: local.createRequestKey(),
      );
      final before = Map.of(private.files);
      private.entered = Completer<void>();
      private.release = Completer<void>();
      final rejected = expectLater(
        local.complete(input),
        throwsA(failure(SyntheticLoginFailureReason.unavailable)),
      );
      await private.entered!.future;
      if (change == 'dispose') {
        local.dispose();
      } else {
        active = await signedRuntime(
          instance: change == 'space' ? 'space-b' : 'space-a',
        );
      }
      private.release!.complete();
      await rejected;
      expect(private.files, before);
    }
  });

  test('reject仅提交值允许，展示与证据仍const且非法输入不归一化', () async {
    final label = ports.createIdentityLabel();
    final view = await ports.begin(beginInput(label));
    expect(() => rejectInput(label, view), returnsNormally);
    for (final input in [
      ' alpha-rehearsal-reject',
      'alpha-rehearsal-reject ',
      'alpha-rehearsal-reject\n',
      'alpha-rehearsal-unknown',
      'alpha-rehearsal-ｒｅｊｅｃｔ',
      'user@example.invalid',
    ]) {
      expect(
        () => CompleteSyntheticChallenge(
          identityLabel: label.value,
          challengeId: view.challengeId,
          confirmationHint: input,
          requestKey: ports.createRequestKey(),
        ),
        throwsArgumentError,
      );
    }
    expect(
      () => SyntheticLoginEvidence(
        identityLabel: label.value,
        confirmationHint: 'alpha-rehearsal-reject',
      ),
      throwsArgumentError,
    );
    expect(
      () => SyntheticChallengeView(
        challengeId: view.challengeId,
        confirmationHint: 'alpha-rehearsal-reject',
        expiresInSeconds: 300,
      ),
      throwsArgumentError,
    );
    expect(persistedChallenge(view.challengeId)['attempts'], 0);
  });

  test('签名空间positive、并发begin/complete幂等、新store恢复、旧空间sentinel0', () async {
    final old =
        '/synthetic-private/alpha_rehearsal/${snapshot.replaceAll(':', '_')}_default.json';
    storage.files[old] = 'sentinel';
    final label = ports.createIdentityLabel();
    final cmd = beginInput(label);
    final views = await Future.wait([ports.begin(cmd), ports.begin(cmd)]);
    expect(views[0].toWire(), views[1].toWire());
    final completion = completeInput(label, views[0]);
    final results = await Future.wait([
      ports.complete(completion),
      ports.complete(completion),
    ]);
    expect(results[0].toWire(), results[1].toWire());
    expect(
      results[0].toWire().keys,
      unorderedEquals(['accountId', 'personaId']),
    );
    expect(
      () => SyntheticLoginEvidence.fromWire({
        'identityLabel': label.value,
        'confirmationHint': views[0].confirmationHint,
        'accountId': results[0].accountId,
      }),
      throwsFormatException,
    );
    final restartedRuntime = await signedRuntime();
    final restart = AlphaSyntheticLoginPorts(
      space: restartedRuntime.rehearsalSpace!,
      currentSpace: () => restartedRuntime.rehearsalSpace,
      gateway: storage,
      now: () => now,
    );
    expect((await restart.restore())!.toWire(), results[0].toWire());
    await expectLater(
      ports.complete(completeInput(label, views[0])),
      throwsA(failure(SyntheticLoginFailureReason.conflict)),
    );
    final fresh = await ports.begin(beginInput(label));
    expect(
      (await ports.complete(completeInput(label, fresh))).toWire(),
      results[0].toWire(),
    );
    expect(storage.calls.where((c) => c.endsWith(old)), isEmpty);
    expect(storage.files[old], 'sentinel');
    expect(storage.files.values.join(), isNot(contains('accessToken')));
  });
  test('default/错runtime/source/snapshot未发均拒绝且不碰存储', () async {
    final standard = await signedRuntime(instance: 'default', mode: 'standard');
    expect(
      () => AlphaSyntheticLoginPorts(
        space: standard.rehearsalSpace!,
        currentSpace: () => standard.rehearsalSpace,
        gateway: storage,
      ),
      throwsA(failure(SyntheticLoginFailureReason.unavailable)),
    );
    expect(
      () => AlphaSyntheticLoginPorts(
        space: runtime.rehearsalSpace!,
        currentSpace: () => null,
        gateway: storage,
      ),
      throwsA(failure(SyntheticLoginFailureReason.unavailable)),
    );
    await expectLater(
      signedRuntime(expectedSnapshot: 'sha256:${'e' * 64}'),
      throwsA(isA<RuntimePackageValidationException>()),
    );
    await expectLater(
      signedRuntime(mutate: (d) => d['contentSource'] = 'remote'),
      throwsA(isA<RuntimePackageValidationException>()),
    );
    expect(storage.calls, isEmpty);
    final label = ports.createIdentityLabel();
    final unknown = SyntheticChallengeView(
      challengeId: 'alpha-challenge:${'a' * 32}',
      confirmationHint: 'alpha-rehearsal-confirm',
      expiresInSeconds: 300,
    );
    await expectLater(
      ports.complete(completeInput(label, unknown)),
      throwsA(failure(SyntheticLoginFailureReason.mismatch)),
    );
    expect(await ports.restore(), isNull);
  });
  test('到期与begin同key不同payload冲突', () async {
    final label = ports.createIdentityLabel();
    final input = beginInput(label);
    final view = await ports.begin(input);
    await expectLater(
      ports.begin(
        BeginSyntheticChallenge(
          identity: ports.createIdentityLabel(),
          requestKey: input.requestKey,
        ),
      ),
      throwsA(failure(SyntheticLoginFailureReason.conflict)),
    );
    now = now.add(const Duration(seconds: 300));
    await expectLater(
      ports.begin(input),
      throwsA(failure(SyntheticLoginFailureReason.expired)),
    );
    await expectLater(
      ports.complete(completeInput(label, view)),
      throwsA(failure(SyntheticLoginFailureReason.expired)),
    );
    expect(await ports.restore(), isNull);
  });
  test('错标识五次锁定、失败同key重放不重复计数，错确认被generated拒绝', () async {
    final label = ports.createIdentityLabel();
    final view = await ports.begin(beginInput(label));
    final wrong = ports.createIdentityLabel();
    expect(
      () => CompleteSyntheticChallenge(
        identityLabel: label.value,
        challengeId: view.challengeId,
        confirmationHint: 'wrong',
        requestKey: ports.createRequestKey(),
      ),
      throwsArgumentError,
    );
    final first = completeInput(wrong, view);
    for (var n = 0; n < 2; n++) {
      await expectLater(
        ports.complete(first),
        throwsA(failure(SyntheticLoginFailureReason.mismatch)),
      );
    }
    for (var n = 2; n <= 5; n++) {
      await expectLater(
        ports.complete(completeInput(wrong, view)),
        throwsA(
          failure(
            n == 5
                ? SyntheticLoginFailureReason.attemptsexceeded
                : SyntheticLoginFailureReason.mismatch,
          ),
        ),
      );
    }
    await expectLater(
      ports.complete(completeInput(label, view)),
      throwsA(failure(SyntheticLoginFailureReason.attemptsexceeded)),
    );
    expect(await ports.restore(), isNull);
  });
  test('跨空间challenge拒绝；相同label分配独立身份', () async {
    final label = ports.createIdentityLabel();
    final view = await ports.begin(beginInput(label));
    final a = await ports.complete(completeInput(label, view));
    final other = await signedRuntime(instance: 'space-b');
    final b = AlphaSyntheticLoginPorts(
      space: other.rehearsalSpace!,
      currentSpace: () => other.rehearsalSpace,
      gateway: storage,
    );
    await expectLater(
      b.complete(completeInput(label, view)),
      throwsA(failure(SyntheticLoginFailureReason.mismatch)),
    );
    final bv = await b.begin(
      BeginSyntheticChallenge(
        identity: label,
        requestKey: b.createRequestKey(),
      ),
    );
    final bs = await b.complete(
      CompleteSyntheticChallenge(
        identityLabel: label.value,
        challengeId: bv.challengeId,
        confirmationHint: bv.confirmationHint,
        requestKey: b.createRequestKey(),
      ),
    );
    expect(bs.accountId, isNot(a.accountId));
  });
  test('写盘失败无身份，retry成功；result validator失败不持久成功', () async {
    final label = ports.createIdentityLabel();
    final view = await ports.begin(beginInput(label));
    final input = completeInput(label, view);
    final old = Map.of(storage.files);
    storage.fail = true;
    await expectLater(
      ports.complete(input),
      throwsA(failure(SyntheticLoginFailureReason.storageunavailable)),
    );
    expect(storage.files, old);
    storage.fail = false;
    expect(await ports.restore(), isNull);
    final invalid = AlphaSyntheticLoginPorts(
      space: runtime.rehearsalSpace!,
      currentSpace: () => current?.rehearsalSpace,
      gateway: storage,
      now: () => now,
      randomHex: () => 'bad',
    );
    await expectLater(
      invalid.complete(input),
      throwsA(failure(SyntheticLoginFailureReason.storageunavailable)),
    );
    expect(await ports.restore(), isNull);
    expect(
      (await ports.complete(input)).accountId,
      startsWith('alpha-account:'),
    );
  });
  test('begin写失败无挑战，坏持久result decoder拒绝且不改字节', () async {
    final label = ports.createIdentityLabel();
    final input = beginInput(label);
    storage.fail = true;
    await expectLater(
      ports.begin(input),
      throwsA(failure(SyntheticLoginFailureReason.storageunavailable)),
    );
    expect(storage.files, isEmpty);
    storage.fail = false;
    final view = await ports.begin(input);
    final completion = completeInput(label, view);
    await ports.complete(completion);
    final path = storage.files.keys.single;
    final envelope = jsonDecode(storage.files[path]!) as Map<String, dynamic>;
    (((envelope['records'] as Map)['synthetic.session'] as Map)['active']
            as Map)['accountId'] =
        'canonical-creator-not-allowed';
    storage.files[path] = jsonEncode(envelope);
    final corrupted = storage.files[path];
    final restarted = AlphaSyntheticLoginPorts(
      space: runtime.rehearsalSpace!,
      currentSpace: () => current?.rehearsalSpace,
      gateway: storage,
      now: () => now,
    );
    await expectLater(
      restarted.restore(),
      throwsA(failure(SyntheticLoginFailureReason.storageunavailable)),
    );
    expect(storage.files[path], corrupted);
  });

  test('旧decoder阶段：正确输入必须匹配持久challenge提示，缺提示不放行', () async {
    final label = ports.createIdentityLabel();
    final view = await ports.begin(beginInput(label));
    final input = completeInput(label, view);
    final path = storage.files.keys.single;
    final envelope = jsonDecode(storage.files[path]!) as Map<String, dynamic>;
    final row =
        ((envelope['records'] as Map)['synthetic.challenges']
                as Map)[view.challengeId]
            as Map;
    expect(row['confirmationHint'], view.confirmationHint);
    // 仅测试私有持久记录缺字段故障，不模拟合法 reject 端到端。
    row.remove('confirmationHint');
    storage.files[path] = jsonEncode(envelope);
    final restarted = AlphaSyntheticLoginPorts(
      space: runtime.rehearsalSpace!,
      currentSpace: () => current?.rehearsalSpace,
      gateway: storage,
      now: () => now,
    );
    final old = storage.files[path];
    storage.fail = true;
    await expectLater(
      restarted.complete(input),
      throwsA(failure(SyntheticLoginFailureReason.storageunavailable)),
    );
    expect(storage.files[path], old);
    storage.fail = false;
    for (var i = 0; i < 2; i++) {
      await expectLater(
        restarted.complete(input),
        throwsA(failure(SyntheticLoginFailureReason.mismatch)),
      );
    }
    final saved = jsonDecode(storage.files[path]!) as Map;
    final challenge =
        ((saved['records'] as Map)['synthetic.challenges']
                as Map)[view.challengeId]
            as Map;
    expect(challenge['attempts'], 1);
    expect(challenge['used'], false);
    expect(await restarted.restore(), isNull);
    await expectLater(
      restarted.complete(
        CompleteSyntheticChallenge(
          identityLabel: ports.createIdentityLabel().value,
          challengeId: view.challengeId,
          confirmationHint: view.confirmationHint,
          requestKey: input.requestKey,
        ),
      ),
      throwsA(failure(SyntheticLoginFailureReason.conflict)),
    );
  });

  test('current runtime getter失败映射unavailable，不执行存储', () async {
    final before = List<String>.of(storage.calls);
    expect(
      () => AlphaSyntheticLoginPorts(
        space: runtime.rehearsalSpace!,
        currentSpace: () => throw StateError('injected getter failure'),
        gateway: storage,
      ),
      throwsA(failure(SyntheticLoginFailureReason.unavailable)),
    );
    expect(storage.calls, before);
  });

  test('慢写期间runtime切换fence，disposal后拒绝且无成功发布', () async {
    final label = ports.createIdentityLabel();
    final input = beginInput(label);
    storage.entered = Completer<void>();
    storage.release = Completer<void>();
    final flight = ports.begin(input);
    final rejected = expectLater(
      flight,
      throwsA(failure(SyntheticLoginFailureReason.unavailable)),
    );
    await storage.entered!.future;
    current = await signedRuntime(instance: 'space-b');
    storage.release!.complete();
    await rejected;
    expect(storage.files, isEmpty);
    ports.dispose();
    await expectLater(
      ports.restore(),
      throwsA(failure(SyntheticLoginFailureReason.unavailable)),
    );
  });
}

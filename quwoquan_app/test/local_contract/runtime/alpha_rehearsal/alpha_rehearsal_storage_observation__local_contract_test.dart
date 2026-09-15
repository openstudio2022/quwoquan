// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-008
import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/config/generated/app_launch_contract.g.dart';
import 'package:quwoquan_app/runtime/config/rehearsal_storage_namespace.dart';
import 'package:quwoquan_app/runtime/config/rehearsal_storage_observer.dart';
import 'package:quwoquan_app/runtime/config/runtime_package_resolver.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_space_binding.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_store.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/alpha_rehearsal_install.dart';
import 'package:quwoquan_app/runtime/config/generated/offline_content_bundle_identity.g.dart';

import 'alpha_rehearsal_synthetic_login__local_contract_test.dart' as fixture;

class DelayedReadStorage extends fixture.PrivateStorage {
  bool failRead = false;
  Completer<void>? readEntered;
  Completer<void>? readRelease;
  @override
  Future<String> readAsString(String path) async {
    readEntered?.complete();
    if (readRelease != null) await readRelease!.future;
    if (failRead) throw StateError('injected read failure');
    return super.readAsString(path);
  }
}

void main() {
  late VerifiedRehearsalSpace space;
  late VerifiedRehearsalSpace? current;
  late String? generation;
  late String? attempt;
  late RehearsalStorageObserver observer;
  late fixture.PrivateStorage storage;
  setUp(() async {
    space = (await fixture.signedRuntime()).rehearsalSpace!;
    current = space;
    generation = '1';
    attempt = 'actual-attempt-1';
    observer = RehearsalStorageObserver(
      space: space,
      currentSpace: () => current,
      startupAttemptId: attempt,
      generation: generation,
      currentStartupAttemptId: () => attempt,
      currentGeneration: () => generation,
    );
    storage = fixture.PrivateStorage();
  });
  FileRehearsalPersistence persistence() => FileRehearsalPersistence.bound(
    gateway: storage,
    binding: RehearsalSpaceBinding.verified(space),
    observation: observer.attach('rehearsal', RehearsalStorageNamespace(space)),
  );

  test('canonical用途摘要golden，不包含真实路径或账户输入', () {
    final p = persistence();
    expect(
      observer.read().bindingDigest,
      'sha256:af8fff75e5ecd71e3d38880f0064abfb1dc77e67ca75e142c590376f30c4c733',
    );
    expect(
      p.observation!.read().namespaceDigest,
      'sha256:59dfb9480f69c3fac4e4f740bf72a240c9b950c20bbbc158978ee5aa44c8d04a',
    );
  });

  test('真实read失败或迟到均不记成功，attempt变化清旧摘要', () async {
    final io = DelayedReadStorage();
    final path =
        '/synthetic-private/alpha_rehearsal/${space.snapshotDigest.replaceAll(':', '_')}_${space.instanceId}.json';
    io.files[path] = 'private-payload';
    final p = FileRehearsalPersistence.bound(
      gateway: io,
      binding: RehearsalSpaceBinding.verified(space),
      observation: observer.attach(
        'rehearsal',
        RehearsalStorageNamespace(space),
      ),
    );
    io.failRead = true;
    await expectLater(p.read(), throwsStateError);
    expect(observer.read().rehearsal.successfulOperations, isEmpty);
    io.failRead = false;
    io.readEntered = Completer<void>();
    io.readRelease = Completer<void>();
    final rejected = expectLater(p.read(), throwsA(isA<Object>()));
    await io.readEntered!.future;
    attempt = 'next-attempt';
    io.readRelease!.complete();
    await rejected;
    expect(observer.read().rehearsal.successfulOperations, isEmpty);
    expect(observer.read().startupAttemptId, isEmpty);
    expect(observer.read().bindingDigest, isEmpty);
  });

  test('构造与观察均无IO，真实write/read后记成功，exists-only不算read', () async {
    final p = persistence();
    expect(
      observer.read().rehearsal.state,
      RehearsalConsumerObservationState.constructed,
    );
    expect(
      observer.read().auth.state,
      RehearsalConsumerObservationState.notObserved,
    );
    expect(storage.calls, isEmpty);
    expect(await p.read(), isNull);
    expect(
      observer.read().rehearsal.state,
      RehearsalConsumerObservationState.constructed,
    );
    final calls = List.of(storage.calls);
    observer.read();
    observer.read();
    expect(storage.calls, calls);
    await p.write('payload-private');
    expect(observer.read().rehearsal.successfulOperations, [
      RehearsalSuccessfulOperation.write,
    ]);
    expect(await p.read(), 'payload-private');
    expect(observer.read().rehearsal.successfulOperations.toSet(), {
      RehearsalSuccessfulOperation.read,
      RehearsalSuccessfulOperation.write,
    });
    final wire = observer.read().toWire().toString();
    expect(wire, isNot(contains('payload-private')));
    expect(wire, isNot(contains('/synthetic-private')));
    expect(
      RehearsalStorageObservation.fromWire(observer.read().toWire()).status,
      RehearsalObservationStatus.available,
    );
  });

  test('失败write不记成功；额外fence失败不记delete；重复成功集合去重', () async {
    final p = persistence();
    storage.fail = true;
    await expectLater(p.write('not-committed'), throwsStateError);
    expect(observer.read().rehearsal.successfulOperations, isEmpty);
    expect(
      () => p.observation!.recordSuccess(
        RehearsalSuccessfulOperation.delete,
        fence: () => throw StateError('failed'),
      ),
      throwsStateError,
    );
    expect(observer.read().rehearsal.successfulOperations, isEmpty);
    storage.fail = false;
    await p.write('ok');
    await p.write('ok');
    expect(observer.read().rehearsal.successfulOperations, [
      RehearsalSuccessfulOperation.write,
    ]);
  });

  test('慢写generation失效不提交且清空摘要，旧句柄不能污染新实例', () async {
    final p = persistence();
    storage.entered = Completer<void>();
    storage.release = Completer<void>();
    final rejected = expectLater(p.write('late'), throwsA(isA<Object>()));
    await storage.entered!.future;
    generation = '2';
    storage.release!.complete();
    await rejected;
    expect(storage.files, isEmpty);
    final observation = observer.read();
    expect(observation.status, RehearsalObservationStatus.unavailable);
    expect(
      observation.configurationState,
      RehearsalConfigurationObservationState.invalidated,
    );
    expect(observation.bindingDigest, isEmpty);
    expect(observation.rehearsal.namespaceDigest, isEmpty);
    expect(observation.rehearsal.successfulOperations, isEmpty);
    expect(
      () => p.observation!.recordSuccess(RehearsalSuccessfulOperation.write),
      throwsA(isA<Object>()),
    );
  });

  test('实际空read语义可由owner记录，consumer替换旧句柄失效且不清新事实', () {
    final namespace = RehearsalStorageNamespace(space);
    final old = observer.attach('auth', namespace);
    old.recordSuccess(RehearsalSuccessfulOperation.read);
    expect(
      observer.read().auth.state,
      RehearsalConsumerObservationState.ioObserved,
    );
    old.invalidate();
    final next = observer.attach('auth', namespace);
    next.recordSuccess(RehearsalSuccessfulOperation.write);
    expect(old.read().state, RehearsalConsumerObservationState.invalidated);
    expect(observer.read().auth.successfulOperations, [
      RehearsalSuccessfulOperation.write,
    ]);
    expect(
      () => old.recordSuccess(RehearsalSuccessfulOperation.delete),
      throwsA(isA<Object>()),
    );
  });

  test('缺真实attempt或generation保持unavailable，未知consumer及非法身份拒绝', () {
    for (final missingAttempt in [true, false]) {
      final a = missingAttempt ? null : attempt;
      final g = missingAttempt ? generation : null;
      final unbound = RehearsalStorageObserver(
        space: space,
        currentSpace: () => current,
        startupAttemptId: a,
        generation: g,
        currentStartupAttemptId: () => a,
        currentGeneration: () => g,
      );
      unbound.attach('rehearsal', RehearsalStorageNamespace(space));
      expect(unbound.read().status, RehearsalObservationStatus.unavailable);
      expect(
        unbound.read().rehearsal.state,
        RehearsalConsumerObservationState.notObserved,
      );
      expect(unbound.read().startupAttemptId, isEmpty);
    }
    expect(
      () => observer.attach('unknown-key', RehearsalStorageNamespace(space)),
      throwsArgumentError,
    );
    expect(
      () => RehearsalStorageObserver(
        space: space,
        currentSpace: () => current,
        startupAttemptId: 'bad space',
        generation: '01',
        currentStartupAttemptId: () => 'bad space',
        currentGeneration: () => '01',
      ),
      throwsFormatException,
    );
  });

  test('四consumer摘要不同，实际space/attempt变更均失效，旧空间sentinel独立', () async {
    final ns = RehearsalStorageNamespace(space);
    for (final name in ['auth', 'installId', 'pending', 'rehearsal']) {
      observer.attach(name, ns);
    }
    final snapshot = observer.read();
    expect(
      {
        snapshot.auth.namespaceDigest,
        snapshot.installId.namespaceDigest,
        snapshot.pending.namespaceDigest,
        snapshot.rehearsal.namespaceDigest,
      }.length,
      4,
    );
    final sameSpaceNewObject = (await fixture.signedRuntime()).rehearsalSpace!;
    current = sameSpaceNewObject;
    expect(observer.read().status, RehearsalObservationStatus.unavailable);
    expect(storage.calls, isEmpty);
  });

  test('composition只透传实例观察，dispose清本consumer，不捏造其它consumerIO', () async {
    final selected = (await fixture.signedRuntime(
      expectedSnapshot: offlineContentManifestDigest,
      mutate: (d) => (d['rehearsalSpace'] as Map)['snapshotDigest'] =
          offlineContentManifestDigest,
    )).rehearsalSpace!;
    final scope = RehearsalStorageObserver(
      space: selected,
      currentSpace: () => selected,
      startupAttemptId: 'actual-start',
      generation: '1',
      currentStartupAttemptId: () => 'actual-start',
      currentGeneration: () => '1',
    );
    final composition = createAlphaRehearsalComposition(
      space: selected,
      currentSpace: () => selected,
      gatewayFactory: () => storage,
      storageObserver: scope,
    );
    expect(composition.storageObserver, same(scope));
    expect(
      scope.read().rehearsal.state,
      RehearsalConsumerObservationState.constructed,
    );
    expect(storage.calls, isEmpty);
    await composition.store.commit(() {
      composition.store.currentOwnerId = 'private-test';
    });
    expect(scope.read().rehearsal.successfulOperations, [
      RehearsalSuccessfulOperation.write,
    ]);
    expect(
      scope.read().auth.state,
      RehearsalConsumerObservationState.notObserved,
    );
    composition.dispose();
    expect(
      scope.read().rehearsal.state,
      RehearsalConsumerObservationState.invalidated,
    );
  });
}

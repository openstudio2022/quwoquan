// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-008
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/executor/rehearsal_cloud_operation_executor.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_store.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/handlers/handler_registry.dart';
import 'package:quwoquan_app/runtime/platform/file_storage_gateway_io.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

class FaultPersistence implements RehearsalPersistence {
  String? value;
  bool fail = false;
  Completer<void>? entered;
  Completer<void>? release;
  @override
  Future<String?> read() async => value;
  @override
  Future<void> write(String contents, {void Function()? beforeCommit}) async {
    entered?.complete();
    if (release != null) await release!.future;
    beforeCommit?.call();
    if (fail) throw StateError('injected disk failure');
    value = contents;
  }
}

AlphaRehearsalCloudOperationExecutor executorFor(AlphaRehearsalStore store) {
  store.records['content.local_posts'] = {
    'post-1': {'postId': 'post-1'},
  };
  return AlphaRehearsalCloudOperationExecutor(
    store: store,
    registry: const AlphaRehearsalHandlerRegistry(),
  );
}

void main() {
  test('持久失败与等待时工作副本不可见，重启保留旧状态', () async {
    final p = FaultPersistence();
    final s = AlphaRehearsalStore(persistence: p);
    await s.commit(() {
      s.currentOwnerId = 'old';
    });
    final old = p.value;
    p.entered = Completer<void>();
    p.release = Completer<void>();
    p.fail = true;
    final write = s.commit(() {
      s.currentOwnerId = 'new';
    });
    final rejected = expectLater(write, throwsA(isA<Object>()));
    await p.entered!.future;
    expect(s.currentOwnerId, 'old');
    p.release!.complete();
    await rejected;
    expect(s.currentOwnerId, 'old');
    expect(p.value, old);
    final restored = AlphaRehearsalStore(persistence: p);
    await restored.ensureLoaded();
    expect(restored.currentOwnerId, 'old');
  });
  test('取消穿过慢写时在原子点前阻断', () async {
    final p = FaultPersistence()
      ..entered = Completer<void>()
      ..release = Completer<void>();
    final s = AlphaRehearsalStore(persistence: p);
    final cancel = CloudOperationCancellationSignal();
    final e = executorFor(s);
    final result = e.send<Object?>(
      appCloudOperationContracts['content.content_reaction.LikePost']!,
      context: CloudOperationInvocationContext(
        surfaceId: 'test',
        clientPageId: 'test',
        actor: const CloudOperationActorContext(personaId: 'a'),
        cancellation: cancel,
      ),
      requestEncoder: () => const CloudOperationRequestPayload(
        pathParameters: {'postId': 'post-1'},
      ),
      responseDecoder: (w) => w,
    );
    final rejected = expectLater(
      result,
      throwsA(isA<CloudOperationCancelledException>()),
    );
    await p.entered!.future;
    cancel.cancel();
    p.release!.complete();
    await rejected;
    expect(s.reactions, isEmpty);
    expect(s.events, isEmpty);
    expect(p.value, isNull);
  });
  test('decoder 故障不提交业务、幂等或事件', () async {
    final s = AlphaRehearsalStore();
    final e = executorFor(s);
    await expectLater(
      e.send<Object?>(
        appCloudOperationContracts['content.content_reaction.LikePost']!,
        context: const CloudOperationInvocationContext(
          surfaceId: 'test',
          clientPageId: 'test',
          actor: CloudOperationActorContext(personaId: 'a'),
          idempotencyKey: 'same',
        ),
        requestEncoder: () => const CloudOperationRequestPayload(
          pathParameters: {'postId': 'post-1'},
        ),
        responseDecoder: (_) =>
            throw const FormatException('injected decode failure'),
      ),
      throwsFormatException,
    );
    expect(s.reactions, isEmpty);
    expect(s.idempotency, isEmpty);
    expect(s.events, isEmpty);
  });
  test('幂等按 actor operation request 隔离并与事件原子提交', () async {
    final p = FaultPersistence();
    final s = AlphaRehearsalStore(persistence: p);
    final e = executorFor(s);
    Future<Object?> send(String actor, String op) => e.send<Object?>(
      appCloudOperationContracts[op]!,
      context: CloudOperationInvocationContext(
        surfaceId: 'test',
        clientPageId: 'test',
        actor: CloudOperationActorContext(personaId: actor),
        idempotencyKey: 'same',
      ),
      requestEncoder: () => const CloudOperationRequestPayload(
        pathParameters: {'postId': 'post-1'},
      ),
      responseDecoder: (w) => w,
    );
    const like = 'content.content_reaction.LikePost';
    final first = await send('a', like);
    expect(await send('a', like), first);
    await send('b', like);
    await send('a', 'content.content_reaction.UnlikePost');
    expect(s.idempotency.length, 3);
    expect(s.events.length, 3);
    final restored = AlphaRehearsalStore(persistence: p);
    await restored.ensureLoaded();
    expect(restored.events.length, 3);
    expect(restored.reactions['a::post-1']!['liked'], false);
  });
  test('reset fence 使旧在途提交失效', () async {
    final s = AlphaRehearsalStore();
    final started = Completer<void>();
    final release = Completer<void>();
    final fence = s.captureFence('a');
    final work = s.commit(() async {
      s.currentOwnerId = 'late';
      started.complete();
      await release.future;
    }, beforeCommit: fence);
    final rejected = expectLater(
      work,
      throwsA(isA<CloudOperationCancelledException>()),
    );
    await started.future;
    final reset = s.resetSpace();
    release.complete();
    await rejected;
    await reset;
    expect(s.currentOwnerId, isNull);
    expect(s.spaceGeneration, 1);
  });
  test('损坏、版本、instance、snapshot 不符均拒绝而不清盘', () async {
    for (final key in ['formatVersion', 'instanceId', 'snapshotDigest']) {
      final p = FaultPersistence();
      final s = AlphaRehearsalStore(persistence: p);
      await s.commit(() {
        s.currentOwnerId = 'old';
      });
      final json = jsonDecode(p.value!) as Map<String, dynamic>;
      json[key] = 'invalid';
      p.value = jsonEncode(json);
      final old = p.value;
      await expectLater(
        AlphaRehearsalStore(persistence: p).ensureLoaded(),
        throwsA(isA<Object>()),
      );
      expect(p.value, old);
    }
  });
  test('真实文件 atomic replace fence 失败保留旧字节', () async {
    final dir = await Directory.systemTemp.createTemp('rehearsal-atomic-');
    addTearDown(() => dir.delete(recursive: true));
    final path = '${dir.path}/state.json';
    const gateway = IoFileStorageGateway();
    await gateway.writeAsStringAtomically(path, 'old');
    await expectLater(
      gateway.writeAsStringAtomically(
        path,
        'new',
        beforeCommit: () => throw const CloudOperationCancelledException(),
      ),
      throwsA(isA<CloudOperationCancelledException>()),
    );
    expect(await File(path).readAsString(), 'old');
    await gateway.writeAsStringAtomically(path, 'new');
    expect(await File(path).readAsString(), 'new');
  });
}

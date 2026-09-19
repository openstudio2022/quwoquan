// spec_ref: specs/feature-tree/discovery-content/content-display-consistency/viewer-profile-state-sync-contract/spec.md#gwt-003
// spec_ref: specs/feature-tree/discovery-content/content-display-consistency/viewer-profile-state-sync-contract/spec.md#gwt-004
import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/transport/state_sync/client_state_sync.dart';
import 'package:quwoquan_app/runtime/transport/state_sync/client_state_sync_outbox_engine.dart';

void main() {
  group('durable client state sync outbox', () {
    test('strict config rejects stringified values', () {
      expect(
        () => ClientStateSyncConfig.fromMap(<String, dynamic>{
          'max_batch_size': '20',
          'flush_on_network_recovered': 'true',
        }, fallback: ClientStateSyncConfig.defaults()),
        throwsFormatException,
      );
    });

    test(
      'durable acceptance persists stable command identity before returning',
      () async {
        final h = _Harness();
        addTearDown(h.dispose);
        await h.engine.enqueueFollow(
          personaId: 'p1',
          currentFollowing: false,
          shouldFollow: true,
          sourceSurfaceId: 'userProfile',
          idempotencyKey: 'key-1',
          mutationBasis: 'basis-1',
          expectedVersion: 7,
          actorRef: 'actor-a',
        );
        final e = h.engine.state.entries.single;
        expect(e.idempotencyKey, 'key-1');
        expect(e.mutationBasis, 'basis-1');
        expect(e.expectedVersion, 7);
        expect(e.intentRevision, 1);
        expect(e.actorRef, 'actor-a');
        expect(h.store.value, isNotNull);
        final restored = ClientStateSyncOutboxState.fromMap(h.store.value!)
            .entries
            .single;
        expect(restored.idempotencyKey, 'key-1');
        expect(restored.expectedVersion, 7);
      },
    );

    test('storage failure rejects durable acceptance', () async {
      final store = _Store()..writeFailure = StateError('disk full');
      final h = _Harness(store: store);
      addTearDown(h.dispose);
      await expectLater(
        h.engine.enqueueFollow(
          personaId: 'p',
          currentFollowing: false,
          shouldFollow: true,
          sourceSurfaceId: 'userProfile',
          idempotencyKey: 'k',
          mutationBasis: 'b',
          expectedVersion: 0,
          actorRef: 'a',
        ),
        throwsStateError,
      );
      expect(
        h.engine.state.entries,
        isEmpty,
        reason: 'failed persistence must not publish pending state',
      );
      store.writeFailure = null;
      await h.engine.enqueueFollow(
        personaId: 'p2',
        currentFollowing: false,
        shouldFollow: true,
        sourceSurfaceId: 'userProfile',
        idempotencyKey: 'k2',
        mutationBasis: 'b2',
        expectedVersion: 0,
        actorRef: 'a',
      );
      expect(
        h.engine.state.entries.single.objectId,
        'p2',
        reason: 'a failed write must not poison the serial writer chain',
      );
    });

    test('hydrate merges untouched disk object but never overwrites newer local object', () async {
      final gate = Completer<void>();
      final store = _Store(readGate: gate);
      store.value = <String, dynamic>{
        'entries': <Object?>[
          _entryMap('profile:follow:changed', 'profile', 'changed', 1),
          _entryMap('profile:follow:untouched', 'profile', 'untouched', 2),
        ],
      };
      final h = _Harness(store: store);
      addTearDown(h.dispose);
      final hydration = h.engine.hydrate();
      await Future<void>.delayed(Duration.zero);
      await h.engine.enqueueFollow(
        personaId: 'changed',
        currentFollowing: false,
        shouldFollow: true,
        sourceSurfaceId: 'userProfile',
        idempotencyKey: 'local-key',
        mutationBasis: 'local-basis',
        expectedVersion: 3,
        actorRef: 'actor',
      );
      gate.complete();
      await hydration;
      final byId = {for (final e in h.engine.state.entries) e.objectId: e};
      expect(byId['changed']!.idempotencyKey, 'local-key');
      expect(byId['untouched']!.idempotencyKey, 'disk-key-untouched');
    });

    test('hydrate never resurrects a locally deleted object even when disk revision is larger', () async {
      final gate = Completer<void>();
      final store = _Store(readGate: gate)
        ..value = <String, dynamic>{
          'entries': <Object?>[
            _entryMap('profile:follow:deleted', 'profile', 'deleted', 99),
          ],
        };
      final h = _Harness(store: store);
      addTearDown(h.dispose);
      final hydration = h.engine.hydrate();
      await Future<void>.delayed(Duration.zero);
      await h.engine.enqueueFollow(
        personaId: 'deleted',
        currentFollowing: false,
        shouldFollow: true,
        sourceSurfaceId: 'userProfile',
        idempotencyKey: 'new',
        mutationBasis: 'basis',
        expectedVersion: 0,
        actorRef: 'actor',
      );
      await h.engine.enqueueFollow(
        personaId: 'deleted',
        currentFollowing: true,
        shouldFollow: false,
        sourceSurfaceId: 'userProfile',
        idempotencyKey: 'remove',
        mutationBasis: 'basis2',
        expectedVersion: 1,
        actorRef: 'actor',
      );
      expect(h.engine.state.entries, isEmpty);
      gate.complete();
      await hydration;
      expect(h.engine.state.entries, isEmpty);
    });

    test(
      'same target has at most one flight and committed receipt removes entry',
      () async {
        final h = _Harness(config: _immediate);
        addTearDown(h.dispose);
        await h.engine.enqueueFollow(
          personaId: 'p',
          currentFollowing: false,
          shouldFollow: true,
          sourceSurfaceId: 'userProfile',
          idempotencyKey: 'key',
          mutationBasis: 'basis',
          expectedVersion: 0,
          actorRef: 'actor',
        );
        h.executor.gate = Completer<void>();
        final first = h.engine.flushNow();
        await Future<void>.delayed(Duration.zero);
        final second = h.engine.flushNow();
        expect(h.executor.entries.length, 1);
        h.executor.gate!.complete();
        await Future.wait([first, second]);
        expect(h.engine.state.entries, isEmpty);
      },
    );

    test(
      'age only pauses sends; authority recovery decides expired terminal',
      () async {
        final store = _Store()
          ..value = <String, dynamic>{
            'entries': <Object?>[
              _entryMap(
                'profile:follow:expired',
                'profile',
                'expired',
                1,
                firstQueuedAt: DateTime.now().toUtc().subtract(
                  const Duration(hours: 73),
                ),
              ),
            ],
          };
        final h = _Harness(store: store, config: _immediate);
        addTearDown(h.dispose);
        h.recoverer.receipt = const ClientStateSyncReceipt(
          outcome: ClientStateSyncReceiptOutcome.expired,
          replayed: false,
        );
        await h.engine.hydrate();
        await h.engine.flushNow();
        expect(h.executor.entries, isEmpty);
        expect(h.recoverer.entries.length, 1);
        expect(h.terminalFailures.length, 1);
        expect(h.engine.state.entries, isEmpty);
      },
    );

    test(
      'history unavailable keeps unknown paused instead of rolling back',
      () async {
        final store = _Store()
          ..value = <String, dynamic>{
            'entries': <Object?>[
              _entryMap(
                'profile:follow:unknown',
                'profile',
                'unknown',
                1,
                firstQueuedAt: DateTime.now().toUtc().subtract(
                  const Duration(hours: 73),
                ),
              ),
            ],
          };
        final h = _Harness(store: store, config: _immediate);
        addTearDown(h.dispose);
        h.recoverer.receipt = const ClientStateSyncReceipt(
          outcome: ClientStateSyncReceiptOutcome.historyUnavailable,
          replayed: false,
        );
        await h.engine.hydrate();
        await h.engine.flushNow();
        expect(h.terminalFailures, isEmpty);
        expect(h.engine.state.entries.single.pausedUnknown, isTrue);
      },
    );

    test(
      'legacy record without stable command identity is deleted, never resent',
      () async {
        final store = _Store()
          ..value = <String, dynamic>{
            'entries': <Object?>[
              <String, Object?>{
                'coalesceKey': 'profile:follow:legacy',
                'objectType': 'profile',
                'objectId': 'legacy',
                'intentType': 'follow',
                'desiredBoolValue': true,
                'nextFlushAt': DateTime.now().toUtc().toIso8601String(),
                'firstQueuedAt': DateTime.now().toUtc().toIso8601String(),
                'retryCount': 0,
              },
            ],
          };
        final h = _Harness(store: store);
        addTearDown(h.dispose);
        await h.engine.hydrate();
        expect(h.engine.state.entries, isEmpty);
        expect(h.executor.entries, isEmpty);
      },
    );

    test('entry and byte limits fail before durable acceptance', () async {
      final h = _Harness(
        config: const ClientStateSyncConfig(
          flushDelay: Duration(hours: 1),
          retryDelay: Duration(minutes: 5),
          maxBatchSize: 20,
          maxPendingAge: Duration(hours: 72),
          flushOnForegroundResume: true,
          flushOnNetworkRecovered: true,
          maxEntries: 1,
          maxPersistedBytes: 1024,
        ),
      );
      addTearDown(h.dispose);
      await h.engine.enqueueFollow(
        personaId: 'a',
        currentFollowing: false,
        shouldFollow: true,
        sourceSurfaceId: 'userProfile',
        idempotencyKey: 'k1',
        mutationBasis: 'b1',
        expectedVersion: 0,
        actorRef: 'actor',
      );
      await expectLater(
        h.engine.enqueueFollow(
          personaId: 'b',
          currentFollowing: false,
          shouldFollow: true,
          sourceSurfaceId: 'userProfile',
          idempotencyKey: 'k2',
          mutationBasis: 'b2',
          expectedVersion: 0,
          actorRef: 'actor',
        ),
        throwsStateError,
      );
    });
  });
}

Map<String, Object?> _entryMap(
  String key,
  String objectType,
  String objectId,
  int revision, {
  DateTime? firstQueuedAt,
}) => <String, Object?>{
  'coalesceKey': key,
  'objectType': objectType,
  'objectId': objectId,
  'intentType': 'follow',
  'desiredBoolValue': true,
  'confirmedBoolValue': false,
  'sourceSurfaceId': 'userProfile',
  'nextFlushAt': DateTime.now().toUtc().toIso8601String(),
  'firstQueuedAt': (firstQueuedAt ?? DateTime.now().toUtc()).toIso8601String(),
  'retryCount': 0,
  'idempotencyKey': 'disk-key-$objectId',
  'mutationBasis': 'disk-basis-$objectId',
  'expectedVersion': 0,
  'intentRevision': revision,
  'actorRef': 'actor',
  'pausedUnknown': false,
};

const _config = ClientStateSyncConfig(
  flushDelay: Duration(hours: 1),
  retryDelay: Duration(minutes: 5),
  maxBatchSize: 20,
  maxPendingAge: Duration(hours: 72),
  flushOnForegroundResume: true,
  flushOnNetworkRecovered: true,
);
const _immediate = ClientStateSyncConfig(
  flushDelay: Duration.zero,
  retryDelay: Duration(minutes: 5),
  maxBatchSize: 20,
  maxPendingAge: Duration(hours: 72),
  flushOnForegroundResume: true,
  flushOnNetworkRecovered: true,
);

final class _Harness {
  _Harness({_Store? store, ClientStateSyncConfig? config})
    : store = store ?? _Store() {
    engine = ClientStateSyncOutboxEngine(
      readConfig: () => config ?? _config,
      readPersistedState: this.store.read,
      writePersistedState: this.store.write,
      executeEntry: executor.call,
      recoverEntry: recoverer.call,
      onStateChanged: (_) {},
      onTerminalFailure: terminalFailures.add,
    );
  }
  final _Store store;
  final _Executor executor = _Executor();
  final _Recoverer recoverer = _Recoverer();
  final List<ClientStateSyncOutboxEntry> terminalFailures = [];
  late final ClientStateSyncOutboxEngine engine;
  void dispose() => engine.dispose();
}

final class _Store {
  _Store({this.readGate});
  Map<String, dynamic>? value;
  final Completer<void>? readGate;
  Object? writeFailure;
  Future<Map<String, dynamic>?> read() async {
    final snapshot = value == null ? null : Map<String, dynamic>.from(value!);
    if (readGate != null) {
      await readGate!.future;
    }
    return snapshot;
  }

  Future<void> write(Map<String, dynamic> next) async {
    if (writeFailure != null) throw writeFailure!;
    value = next;
  }
}

final class _Executor {
  final List<ClientStateSyncOutboxEntry> entries = [];
  Completer<void>? gate;
  ClientStateSyncReceipt receipt = const ClientStateSyncReceipt(
    outcome: ClientStateSyncReceiptOutcome.committed,
    replayed: false,
    committedVersion: 1,
    changed: true,
  );
  Future<ClientStateSyncReceipt> call(ClientStateSyncOutboxEntry e) async {
    entries.add(e);
    if (gate != null) await gate!.future;
    return receipt;
  }
}

final class _Recoverer {
  final List<ClientStateSyncOutboxEntry> entries = [];
  ClientStateSyncReceipt receipt = const ClientStateSyncReceipt(
    outcome: ClientStateSyncReceiptOutcome.historyUnavailable,
    replayed: false,
  );
  Future<ClientStateSyncReceipt> call(ClientStateSyncOutboxEntry e) async {
    entries.add(e);
    return receipt;
  }
}

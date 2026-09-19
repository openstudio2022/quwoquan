import 'dart:async';
import 'dart:convert';

import 'package:quwoquan_app/runtime/transport/state_sync/client_state_sync.dart';

typedef ClientStateSyncConfigReader = ClientStateSyncConfig Function();
typedef ClientStateSyncOutboxReader = Future<Map<String, dynamic>?> Function();
typedef ClientStateSyncOutboxWriter = Future<void> Function(
  Map<String, dynamic> value,
);
typedef ClientStateSyncEntryExecutor = Future<ClientStateSyncReceipt> Function(
  ClientStateSyncOutboxEntry entry,
);
typedef ClientStateSyncEntryRecoverer = Future<ClientStateSyncReceipt> Function(
  ClientStateSyncOutboxEntry entry,
);
typedef ClientStateSyncStateListener = void Function(
  ClientStateSyncOutboxState state,
);
typedef ClientStateSyncTerminalFailureListener = void Function(
  ClientStateSyncOutboxEntry entry,
);

/// Durable client intent engine. A command becomes accepted only after the
/// entry carrying stable key/basis/version/actor has been persisted. Local age
/// only pauses new sends; the owning service receipt decides terminal outcome.
final class ClientStateSyncOutboxEngine {
  ClientStateSyncOutboxEngine({
    required this.readConfig,
    required this.readPersistedState,
    required this.writePersistedState,
    required this.executeEntry,
    required this.recoverEntry,
    required this.onStateChanged,
    required this.onTerminalFailure,
  });

  final ClientStateSyncConfigReader readConfig;
  final ClientStateSyncOutboxReader readPersistedState;
  final ClientStateSyncOutboxWriter writePersistedState;
  final ClientStateSyncEntryExecutor executeEntry;
  final ClientStateSyncEntryRecoverer recoverEntry;
  final ClientStateSyncStateListener onStateChanged;
  final ClientStateSyncTerminalFailureListener onTerminalFailure;

  Timer? _flushTimer;
  final Map<String, bool> _inFlightDesiredValues = <String, bool>{};
  final Map<String, int> _objectRevisions = <String, int>{};
  final Set<String> _touchedKeys = <String>{};
  Future<void> _admissionTail = Future<void>.value();
  ClientStateSyncOutboxState _state = const ClientStateSyncOutboxState();
  Future<void> _writeTail = Future<void>.value();
  bool _terminallyPurged = false;
  bool _disposed = false;

  ClientStateSyncOutboxState get state => _state;

  Future<void> hydrate() async {
    final raw = await readPersistedState();
    await _admissionTail;
    if (_disposed || _terminallyPurged || raw == null) return;
    try {
      final disk = ClientStateSyncOutboxState.fromMap(raw).entries;
      final byKey = <String, ClientStateSyncOutboxEntry>{
        for (final entry in _state.entries) entry.coalesceKey: entry,
      };
      for (final entry in disk) {
        final current = byKey[entry.coalesceKey];
        final localRevision = _objectRevisions[entry.coalesceKey] ?? 0;
        if (_touchedKeys.contains(entry.coalesceKey) ||
            localRevision > entry.intentRevision) {
          continue;
        }
        if (current == null || current.intentRevision < entry.intentRevision) {
          byKey[entry.coalesceKey] = entry;
        }
      }
      _setState(
        ClientStateSyncOutboxState(
          entries: _dropResolvedEntries(byKey.values.toList(growable: false)),
        ),
      );
    } on FormatException {
      // Invalid legacy records cannot be upgraded into a new write command: the
      // stable key/basis/version cannot be reconstructed honestly.
      // Corrupt legacy storage must not erase newly accepted in-memory intents.
      await _persistState();
    }
    _scheduleNextFlush();
  }

  Future<void> enqueueFollow({
    required String personaId,
    required bool currentFollowing,
    required bool shouldFollow,
    required String sourceSurfaceId,
    required String idempotencyKey,
    required String mutationBasis,
    required int expectedVersion,
    required String actorRef,
    bool flushImmediately = false,
  }) => _upsertEntry(
    objectType: 'profile',
    objectId: personaId,
    intentType: 'follow',
    currentBoolValue: currentFollowing,
    desiredBoolValue: shouldFollow,
    sourceSurfaceId: sourceSurfaceId,
    idempotencyKey: idempotencyKey,
    mutationBasis: mutationBasis,
    expectedVersion: expectedVersion,
    actorRef: actorRef,
    flushImmediately: flushImmediately,
  );

  Future<void> enqueuePostLike({
    required String postId,
    required bool currentLiked,
    required bool isLiked,
    required String idempotencyKey,
    required String mutationBasis,
    required int expectedVersion,
    required String actorRef,
    bool flushImmediately = false,
  }) => _upsertEntry(
    objectType: 'post',
    objectId: postId,
    intentType: 'like',
    currentBoolValue: currentLiked,
    desiredBoolValue: isLiked,
    idempotencyKey: idempotencyKey,
    mutationBasis: mutationBasis,
    expectedVersion: expectedVersion,
    actorRef: actorRef,
    flushImmediately: flushImmediately,
  );

  Future<void> flushNow() async {
    await _admissionTail;
    if (_disposed || _terminallyPurged) return;
    final config = readConfig();
    final now = DateTime.now();
    final expired = _state.entries
        .where(
          (e) =>
              !_isInFlight(e.coalesceKey) &&
              e.hasPendingDelta &&
              !e.pausedUnknown &&
              now.difference(e.firstQueuedAt) > config.maxPendingAge,
        )
        .toList(growable: false);
    for (final entry in expired) {
      _replaceEntry(entry.copyWith(pausedUnknown: true));
    }
    if (expired.isNotEmpty) await _persistState();
    final paused = _state.entries
        .where(
          (e) =>
              e.pausedUnknown &&
              !_isInFlight(e.coalesceKey) &&
              !e.nextFlushAt.isAfter(now),
        )
        .take(config.maxBatchSize)
        .toList(growable: false);
    for (final entry in paused) {
      await _recover(entry);
    }
    final due = _state.entries
        .where(
          (e) =>
              !e.pausedUnknown &&
              !_isInFlight(e.coalesceKey) &&
              e.hasPendingDelta &&
              !e.nextFlushAt.isAfter(now),
        )
        .take(config.maxBatchSize)
        .map((e) => e.coalesceKey)
        .toList(growable: false);
    for (final key in due) {
      if (_disposed || _terminallyPurged) {
        break;
      }
      final entry = _entryForKey(key);
      if (entry == null ||
          _isInFlight(key) ||
          entry.pausedUnknown ||
          !entry.hasPendingDelta) {
        continue;
      }
      _inFlightDesiredValues[key] = entry.desiredBoolValue;
      try {
        final receipt = await executeEntry(entry);
        _applyReceipt(key, entry, receipt);
      } catch (_) {
        _onFlushFailed(key, config);
      } finally {
        _inFlightDesiredValues.remove(key);
      }
    }
    await _persistState();
    _scheduleNextFlush();
  }

  Future<void> _recover(ClientStateSyncOutboxEntry entry) async {
    _inFlightDesiredValues[entry.coalesceKey] = entry.desiredBoolValue;
    try {
      final receipt = await recoverEntry(entry);
      _applyReceipt(entry.coalesceKey, entry, receipt);
    } catch (_) {
      final current = _entryForKey(entry.coalesceKey);
      if (current != null) {
        _replaceEntry(
          current.copyWith(
            pausedUnknown: true,
            nextFlushAt: DateTime.now().add(readConfig().retryDelay),
          ),
        );
      }
    } finally {
      _inFlightDesiredValues.remove(entry.coalesceKey);
    }
  }

  void _applyReceipt(
    String key,
    ClientStateSyncOutboxEntry flushed,
    ClientStateSyncReceipt receipt,
  ) {
    switch (receipt.outcome) {
      case ClientStateSyncReceiptOutcome.committed:
        final current = _entryForKey(key);
        if (current == null) return;
        final reconciled = current.copyWith(
          confirmedBoolValue: flushed.desiredBoolValue,
          retryCount: 0,
          pausedUnknown: false,
          expectedVersion: receipt.committedVersion ?? current.expectedVersion,
        );
        if (!reconciled.hasPendingDelta) {
          _removeEntry(key);
        } else {
          _replaceEntry(reconciled);
        }
      case ClientStateSyncReceiptOutcome.rejected:
      case ClientStateSyncReceiptOutcome.expired:
        _removeEntry(key);
        onTerminalFailure(flushed);
      case ClientStateSyncReceiptOutcome.historyUnavailable:
        // History loss is not proof of failure. Keep the intent paused and ask
        // the owning read/recovery UI for an explicit new user decision.
        _replaceEntry(
          flushed.copyWith(
            pausedUnknown: true,
            nextFlushAt: DateTime.now().add(readConfig().retryDelay),
          ),
        );
    }
  }

  Future<void> _upsertEntry({
    required String objectType,
    required String objectId,
    required String intentType,
    required bool? currentBoolValue,
    required bool desiredBoolValue,
    String sourceSurfaceId = '',
    required String idempotencyKey,
    required String mutationBasis,
    required int expectedVersion,
    required String actorRef,
    required bool flushImmediately,
  }) async {
    final previous = _admissionTail;
    final result = previous
        .catchError((Object _) {})
        .then(
          (_) => _upsertEntryInternal(
            objectType: objectType,
            objectId: objectId,
            intentType: intentType,
            currentBoolValue: currentBoolValue,
            desiredBoolValue: desiredBoolValue,
            sourceSurfaceId: sourceSurfaceId,
            idempotencyKey: idempotencyKey,
            mutationBasis: mutationBasis,
            expectedVersion: expectedVersion,
            actorRef: actorRef,
            flushImmediately: flushImmediately,
          ),
        );
    _admissionTail = result.catchError((Object _) {});
    await result;
    if (flushImmediately) {
      await flushNow();
    }
  }

  Future<void> _upsertEntryInternal({
    required String objectType,
    required String objectId,
    required String intentType,
    required bool? currentBoolValue,
    required bool desiredBoolValue,
    String sourceSurfaceId = '',
    required String idempotencyKey,
    required String mutationBasis,
    required int expectedVersion,
    required String actorRef,
    required bool flushImmediately,
  }) async {
    if (_disposed || _terminallyPurged) {
      throw StateError('client state sync outbox is unavailable');
    }
    if (idempotencyKey.trim().isEmpty ||
        mutationBasis.trim().isEmpty ||
        actorRef.trim().isEmpty ||
        expectedVersion < 0) {
      throw ArgumentError('durable command identity is incomplete');
    }
    final config = readConfig(),
        now = DateTime.now(),
        key = '$objectType:$intentType:$objectId',
        existing = _entryForKey(key);
    final confirmed = existing?.confirmedBoolValue ?? currentBoolValue;
    if (!_isInFlight(key) &&
        confirmed != null &&
        confirmed == desiredBoolValue) {
      final next = ClientStateSyncOutboxState(
        entries: _state.entries
            .where((e) => e.coalesceKey != key)
            .toList(growable: false),
      );
      await _persistSnapshot(next);
      _removeEntry(key);
      _touchedKeys.add(key);
      _scheduleNextFlush();
      return;
    }
    final revision =
        (existing?.intentRevision ?? _objectRevisions[key] ?? 0) + 1;
    final entry = ClientStateSyncOutboxEntry(
      coalesceKey: key,
      objectType: objectType,
      objectId: objectId,
      intentType: intentType,
      desiredBoolValue: desiredBoolValue,
      sourceSurfaceId: sourceSurfaceId,
      nextFlushAt: flushImmediately ? now : now.add(config.flushDelay),
      firstQueuedAt: existing?.firstQueuedAt ?? now,
      confirmedBoolValue: confirmed,
      retryCount: 0,
      idempotencyKey: idempotencyKey,
      mutationBasis: mutationBasis,
      expectedVersion: expectedVersion,
      intentRevision: revision,
      actorRef: actorRef,
    );
    final next = [..._state.entries.where((e) => e.coalesceKey != key), entry];
    if (next.length > config.maxEntries) {
      throw StateError('client state sync outbox entry capacity exceeded');
    }
    final encodedBytes = utf8
        .encode(jsonEncode(ClientStateSyncOutboxState(entries: next).toMap()))
        .length;
    if (encodedBytes > config.maxPersistedBytes) {
      throw StateError('client state sync outbox byte capacity exceeded');
    }
    final accepted = ClientStateSyncOutboxState(entries: next);
    await _persistSnapshot(accepted); // publish only after durable acceptance
    _objectRevisions[key] = revision;
    _touchedKeys.add(key);
    _setState(accepted);
    _scheduleNextFlush();
  }

  void _onFlushFailed(String key, ClientStateSyncConfig config) {
    final current = _entryForKey(key);
    if (current == null || !current.hasPendingDelta) return;
    final now = DateTime.now();
    if (now.difference(current.firstQueuedAt) > config.maxPendingAge) {
      _replaceEntry(current.copyWith(pausedUnknown: true));
      return;
    }
    _replaceEntry(
      current.copyWith(
        retryCount: current.retryCount + 1,
        nextFlushAt: now.add(config.retryDelay),
      ),
    );
  }

  void _scheduleNextFlush() {
    _flushTimer?.cancel();
    if (_disposed || _terminallyPurged) return;
    final times = _state.entries
        .where((e) => !_isInFlight(e.coalesceKey) && e.hasPendingDelta)
        .map((e) => e.nextFlushAt)
        .toList();
    if (times.isEmpty) return;
    final at = times.reduce((a, b) => a.isBefore(b) ? a : b);
    final delay = at.difference(DateTime.now());
    _flushTimer = Timer(delay.isNegative ? Duration.zero : delay, flushNow);
  }

  bool _isInFlight(String key) => _inFlightDesiredValues.containsKey(key);
  ClientStateSyncOutboxEntry? _entryForKey(String key) {
    for (final e in _state.entries.reversed) {
      if (e.coalesceKey == key) return e;
    }
    return null;
  }

  void _replaceEntry(ClientStateSyncOutboxEntry entry) {
    _setState(
      ClientStateSyncOutboxState(
        entries: [
          ..._state.entries.where((e) => e.coalesceKey != entry.coalesceKey),
          entry,
        ],
      ),
    );
  }

  void _removeEntry(String key) {
    _touchedKeys.add(key);
    _objectRevisions[key] = (_objectRevisions[key] ?? 0) + 1;
    _setState(
      ClientStateSyncOutboxState(
        entries: _state.entries
            .where((e) => e.coalesceKey != key)
            .toList(growable: false),
      ),
    );
  }

  List<ClientStateSyncOutboxEntry> _dropResolvedEntries(
    List<ClientStateSyncOutboxEntry> entries,
  ) => entries.where((e) => e.hasPendingDelta).toList(growable: false);
  Future<void> _persistState() => _persistSnapshot(_state);
  Future<void> _persistSnapshot(ClientStateSyncOutboxState snapshot) {
    if (_disposed || _terminallyPurged) return Future<void>.value();
    final encoded = snapshot.toMap();
    final write = _writeTail
        .catchError((Object _) {})
        .then((_) => writePersistedState(encoded));
    _writeTail = write.catchError((Object _) {});
    return write;
  }

  void purgeForTerminalAccountClosure() {
    _terminallyPurged = true;
    _flushTimer?.cancel();
    _inFlightDesiredValues.clear();
    _objectRevisions.clear();
    _touchedKeys.clear();
    _setState(const ClientStateSyncOutboxState());
  }

  void dispose() {
    _disposed = true;
    _flushTimer?.cancel();
    _inFlightDesiredValues.clear();
  }

  void _setState(ClientStateSyncOutboxState next) {
    _state = next;
    onStateChanged(next);
  }
}

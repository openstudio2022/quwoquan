import 'dart:async';

import 'package:quwoquan_app/runtime/transport/state_sync/client_state_sync.dart';

typedef ClientStateSyncConfigReader = ClientStateSyncConfig Function();
typedef ClientStateSyncOutboxReader = Future<Map<String, dynamic>?> Function();
typedef ClientStateSyncOutboxWriter =
    Future<void> Function(Map<String, dynamic> value);
typedef ClientStateSyncEntryExecutor =
    Future<void> Function(ClientStateSyncOutboxEntry entry);
typedef ClientStateSyncStateListener =
    void Function(ClientStateSyncOutboxState state);

/// Runtime transport engine for coalescing and retrying client interaction
/// intents. Domain operation mapping, persistence technology and composition
/// stay outside this library behind typed callbacks.
final class ClientStateSyncOutboxEngine {
  ClientStateSyncOutboxEngine({
    required this.readConfig,
    required this.readPersistedState,
    required this.writePersistedState,
    required this.executeEntry,
    required this.onStateChanged,
  });

  final ClientStateSyncConfigReader readConfig;
  final ClientStateSyncOutboxReader readPersistedState;
  final ClientStateSyncOutboxWriter writePersistedState;
  final ClientStateSyncEntryExecutor executeEntry;
  final ClientStateSyncStateListener onStateChanged;

  Timer? _flushTimer;
  final Map<String, bool> _inFlightDesiredValues = <String, bool>{};
  ClientStateSyncOutboxState _state = const ClientStateSyncOutboxState();
  bool _terminallyPurged = false;
  bool _disposed = false;

  ClientStateSyncOutboxState get state => _state;

  Future<void> hydrate() async {
    final raw = await readPersistedState();
    if (_disposed || _terminallyPurged || raw == null) {
      return;
    }
    try {
      _setState(
        _state.copyWith(
          entries: _dropResolvedEntries(
            ClientStateSyncOutboxState.fromMap(raw).entries,
          ),
        ),
      );
    } on FormatException {
      _setState(const ClientStateSyncOutboxState());
      await writePersistedState(_state.toMap());
    }
    _scheduleNextFlush();
  }

  void enqueueFollow({
    required String personaId,
    required bool currentFollowing,
    required bool shouldFollow,
    required String sourceSurfaceId,
    bool flushImmediately = false,
  }) {
    _upsertEntry(
      objectType: 'profile',
      objectId: personaId,
      intentType: 'follow',
      currentBoolValue: currentFollowing,
      desiredBoolValue: shouldFollow,
      sourceSurfaceId: sourceSurfaceId,
      flushImmediately: flushImmediately,
    );
  }

  void enqueuePostLike({
    required String postId,
    required bool currentLiked,
    required bool isLiked,
    bool flushImmediately = false,
  }) {
    _upsertEntry(
      objectType: 'post',
      objectId: postId,
      intentType: 'like',
      currentBoolValue: currentLiked,
      desiredBoolValue: isLiked,
      flushImmediately: flushImmediately,
    );
  }

  Future<void> flushNow() async {
    if (_disposed || _terminallyPurged) {
      return;
    }
    final config = readConfig();
    final now = DateTime.now();
    final dueKeys = _state.entries
        .where(
          (entry) =>
              !_isInFlight(entry.coalesceKey) &&
              entry.hasPendingDelta &&
              !entry.nextFlushAt.isAfter(now),
        )
        .take(config.maxBatchSize)
        .map((entry) => entry.coalesceKey)
        .toList(growable: false);
    if (dueKeys.isEmpty) {
      _scheduleNextFlush();
      return;
    }

    for (final coalesceKey in dueKeys) {
      if (_disposed || _terminallyPurged) {
        break;
      }
      final entry = _entryForKey(coalesceKey);
      if (entry == null ||
          _isInFlight(coalesceKey) ||
          !entry.hasPendingDelta ||
          entry.nextFlushAt.isAfter(DateTime.now())) {
        continue;
      }
      _inFlightDesiredValues[coalesceKey] = entry.desiredBoolValue;
      try {
        await executeEntry(entry);
        if (!_disposed && !_terminallyPurged) {
          _onFlushSucceeded(
            coalesceKey: coalesceKey,
            flushedDesiredBoolValue: entry.desiredBoolValue,
          );
        }
      } catch (_) {
        if (!_disposed && !_terminallyPurged) {
          _onFlushFailed(coalesceKey: coalesceKey, config: config);
        }
      } finally {
        _inFlightDesiredValues.remove(coalesceKey);
      }
    }
    if (_disposed || _terminallyPurged) {
      return;
    }
    unawaited(_persistState());
    _scheduleNextFlush();
  }

  void _upsertEntry({
    required String objectType,
    required String objectId,
    required String intentType,
    required bool? currentBoolValue,
    required bool desiredBoolValue,
    String sourceSurfaceId = '',
    required bool flushImmediately,
  }) {
    if (_disposed || _terminallyPurged) {
      return;
    }
    final config = readConfig();
    final now = DateTime.now();
    final coalesceKey = '$objectType:$intentType:$objectId';
    final existingEntry = _entryForKey(coalesceKey);
    final confirmedBoolValue =
        existingEntry?.confirmedBoolValue ?? currentBoolValue;
    if (!_isInFlight(coalesceKey) &&
        confirmedBoolValue != null &&
        confirmedBoolValue == desiredBoolValue) {
      _removeEntry(coalesceKey);
      unawaited(_persistState());
      _scheduleNextFlush();
      return;
    }
    _replaceEntry(
      ClientStateSyncOutboxEntry(
        coalesceKey: coalesceKey,
        objectType: objectType,
        objectId: objectId,
        intentType: intentType,
        desiredBoolValue: desiredBoolValue,
        sourceSurfaceId: sourceSurfaceId,
        nextFlushAt: flushImmediately ? now : now.add(config.flushDelay),
        confirmedBoolValue: confirmedBoolValue,
        retryCount: existingEntry?.retryCount ?? 0,
      ),
    );
    unawaited(_persistState());
    _scheduleNextFlush();
  }

  void _scheduleNextFlush() {
    _flushTimer?.cancel();
    if (_disposed || _terminallyPurged || _state.entries.isEmpty) return;
    final wakeTimes = _state.entries
        .where(
          (entry) => !_isInFlight(entry.coalesceKey) && entry.hasPendingDelta,
        )
        .map((entry) => entry.nextFlushAt)
        .toList(growable: false);
    if (wakeTimes.isEmpty) {
      return;
    }
    final nextWakeAt = wakeTimes.reduce((a, b) => a.isBefore(b) ? a : b);
    final delay = nextWakeAt.difference(DateTime.now());
    _flushTimer = Timer(delay.isNegative ? Duration.zero : delay, flushNow);
  }

  bool _isInFlight(String coalesceKey) {
    return _inFlightDesiredValues.containsKey(coalesceKey);
  }

  ClientStateSyncOutboxEntry? _entryForKey(String coalesceKey) {
    for (final entry in _state.entries.reversed) {
      if (entry.coalesceKey == coalesceKey) {
        return entry;
      }
    }
    return null;
  }

  void _replaceEntry(ClientStateSyncOutboxEntry entry) {
    final nextEntries = List<ClientStateSyncOutboxEntry>.from(_state.entries)
      ..removeWhere((item) => item.coalesceKey == entry.coalesceKey)
      ..add(entry);
    _setState(_state.copyWith(entries: nextEntries));
  }

  void _removeEntry(String coalesceKey) {
    _setState(
      _state.copyWith(
        entries: _state.entries
            .where((entry) => entry.coalesceKey != coalesceKey)
            .toList(growable: false),
      ),
    );
  }

  void _onFlushSucceeded({
    required String coalesceKey,
    required bool flushedDesiredBoolValue,
  }) {
    final currentEntry = _entryForKey(coalesceKey);
    if (currentEntry == null) {
      return;
    }
    final reconciledEntry = currentEntry.copyWith(
      confirmedBoolValue: flushedDesiredBoolValue,
      retryCount: 0,
    );
    if (!reconciledEntry.hasPendingDelta) {
      _removeEntry(coalesceKey);
      return;
    }
    _replaceEntry(reconciledEntry);
  }

  void _onFlushFailed({
    required String coalesceKey,
    required ClientStateSyncConfig config,
  }) {
    final currentEntry = _entryForKey(coalesceKey);
    if (currentEntry == null) {
      return;
    }
    if (!currentEntry.hasPendingDelta) {
      _removeEntry(coalesceKey);
      return;
    }
    _replaceEntry(
      currentEntry.copyWith(
        retryCount: currentEntry.retryCount + 1,
        nextFlushAt: DateTime.now().add(config.retryDelay),
      ),
    );
  }

  List<ClientStateSyncOutboxEntry> _dropResolvedEntries(
    List<ClientStateSyncOutboxEntry> entries,
  ) {
    return entries
        .where((entry) => entry.hasPendingDelta)
        .toList(growable: false);
  }

  Future<void> _persistState() async {
    if (_disposed || _terminallyPurged) {
      return;
    }
    await writePersistedState(_state.toMap());
  }

  void purgeForTerminalAccountClosure() {
    _terminallyPurged = true;
    _flushTimer?.cancel();
    _flushTimer = null;
    _inFlightDesiredValues.clear();
    _setState(const ClientStateSyncOutboxState());
  }

  void dispose() {
    _disposed = true;
    _flushTimer?.cancel();
    _flushTimer = null;
    _inFlightDesiredValues.clear();
  }

  void _setState(ClientStateSyncOutboxState nextState) {
    _state = nextState;
    if (!_disposed) {
      onStateChanged(nextState);
    }
  }
}

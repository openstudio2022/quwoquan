import 'dart:async';
import 'dart:convert';
import 'dart:developer' as developer;
import 'dart:math';

import 'package:quwoquan_app/runtime/shell/startup/startup_native_journal_adapter.dart';
import 'package:quwoquan_app/runtime/observability/startup/startup_telemetry_support.dart';
import 'package:quwoquan_cloud_contracts/generated/ops_contracts.dart'
    as ops_contracts;
import 'package:shared_preferences/shared_preferences.dart';

/// 启动遥测仅用于一次启动的可靠性诊断，禁止承载账号、内容、异常文本或堆栈。
enum StartupTelemetryPhase {
  nativePreFlutter('native_pre_flutter'),
  dartBootstrap('dart_bootstrap'),
  configurationValidation('configuration_validation'),
  flutterFirstFrame('flutter_first_frame'),
  routerPreload('router_preload'),
  routerReady('router_ready'),
  routerFailure('router_failure'),
  shellFirstPaint('shell_first_paint'),
  homeFeedFirstUsable('home_feed_first_usable'),
  terminal('terminal'),
  recovery('recovery');

  const StartupTelemetryPhase(this.wireName);

  final String wireName;
}

final class _PendingStartupTelemetryRecord {
  const _PendingStartupTelemetryRecord({
    required this.phase,
    required this.elapsedMs,
    required this.outcome,
    required this.recoverySurface,
    required this.recoveryLifecycle,
    required this.recoveryMount,
    required this.recoveryPhase,
    required this.recoveryAction,
    required this.failureCode,
    required this.failureSource,
    required this.deadlineOrigin,
    required this.networkClass,
  });

  final StartupTelemetryPhase phase;
  final int elapsedMs;
  final String outcome;
  final ops_contracts.StartupRecoverySurface? recoverySurface;
  final ops_contracts.StartupRecoveryLifecycle? recoveryLifecycle;
  final ops_contracts.StartupRecoveryMount? recoveryMount;
  final ops_contracts.StartupRecoveryPhase? recoveryPhase;
  final ops_contracts.StartupRecoveryAction? recoveryAction;
  final String failureCode;
  final String failureSource;
  final String deadlineOrigin;
  final String networkClass;
}

final class StartupAttempt {
  const StartupAttempt({
    required this.id,
    required this.proof,
    required this.startedAt,
  });

  final String id;
  final String proof;
  final DateTime startedAt;
}

final class StartupTelemetryEvent {
  const StartupTelemetryEvent({
    required this.eventId,
    required this.attemptId,
    required this.sequence,
    required this.phase,
    required this.phaseDurationMs,
    required this.elapsedMs,
    required this.outcome,
    required this.occurredAt,
    required this.platform,
    required this.runtimeEnv,
    required this.appVersion,
    required this.networkClass,
    required this.failureCode,
    required this.failureSource,
    required this.deadlineOrigin,
    this.recoverySurface,
    this.recoveryLifecycle,
    this.recoveryMount,
    this.recoveryPhase,
    this.recoveryAction,
  });

  final String eventId;
  final String attemptId;
  final int sequence;
  final StartupTelemetryPhase phase;
  final int phaseDurationMs;
  final int elapsedMs;
  final String outcome;
  final DateTime occurredAt;
  final String platform;
  final String runtimeEnv;
  final String appVersion;
  final String networkClass;
  final ops_contracts.StartupRecoverySurface? recoverySurface;
  final ops_contracts.StartupRecoveryLifecycle? recoveryLifecycle;
  final ops_contracts.StartupRecoveryMount? recoveryMount;
  final ops_contracts.StartupRecoveryPhase? recoveryPhase;
  final ops_contracts.StartupRecoveryAction? recoveryAction;
  final String failureCode;
  final String failureSource;
  final String deadlineOrigin;

  bool get isRecoveryTelemetry =>
      phase == StartupTelemetryPhase.recovery &&
      recoverySurface != null &&
      recoveryLifecycle != null &&
      recoveryMount != null &&
      recoveryPhase != null &&
      recoveryAction != null;

  Map<String, Object?> toJson() {
    return <String, Object?>{
      'eventId': eventId,
      'attemptId': attemptId,
      'sequence': sequence,
      'phase': phase.wireName,
      'phaseDurationMs': phaseDurationMs,
      'elapsedMs': elapsedMs,
      'outcome': outcome,
      'occurredAt': occurredAt.toUtc().toIso8601String(),
      'platform': platform,
      'runtimeEnv': runtimeEnv,
      if (appVersion.isNotEmpty) 'appVersion': appVersion,
      if (networkClass.isNotEmpty) 'networkClass': networkClass,
      if (recoverySurface != null) 'recoverySurface': recoverySurface!.wireName,
      if (recoveryLifecycle != null)
        'recoveryLifecycle': recoveryLifecycle!.wireName,
      if (recoveryMount != null) 'recoveryMount': recoveryMount!.wireName,
      if (recoveryPhase != null) 'recoveryPhase': recoveryPhase!.wireName,
      if (recoveryAction != null) 'recoveryAction': recoveryAction!.wireName,
      if (failureCode.isNotEmpty) 'failureCode': failureCode,
      if (failureSource.isNotEmpty) 'failureSource': failureSource,
      if (deadlineOrigin.isNotEmpty) 'deadlineOrigin': deadlineOrigin,
    };
  }
}

final class StartupTelemetryBatchAck {
  const StartupTelemetryBatchAck({
    required this.acceptedCount,
    required this.duplicateCount,
  });

  final int acceptedCount;
  final int duplicateCount;

  bool acknowledges(int expectedCount) =>
      acceptedCount + duplicateCount == expectedCount;
}

abstract interface class StartupTelemetryTransport {
  Future<StartupTelemetryBatchAck> report(
    List<StartupTelemetryEvent> events, {
    required String proof,
  });
}

abstract interface class StartupJournalStore {
  Future<List<String>> readEvents();

  Future<void> writeEvents(List<String> encodedEvents);

  Future<String?> readProof();

  Future<void> writeProof(String proof);
}

final class SharedPreferencesStartupJournalStore
    implements StartupJournalStore {
  // SharedPreferences keys are frozen canonical bytes for existing installs.
  static const _eventsKey = 'startup_telemetry_journal_v1';
  static const _proofKey = 'startup_telemetry_proof_v1';

  Future<SharedPreferences> get _preferences => SharedPreferences.getInstance();

  @override
  Future<List<String>> readEvents() async {
    final values = (await _preferences).getStringList(_eventsKey);
    return List<String>.from(values ?? const <String>[]);
  }

  @override
  Future<void> writeEvents(List<String> encodedEvents) async {
    await (await _preferences).setStringList(_eventsKey, encodedEvents);
  }

  @override
  Future<String?> readProof() async =>
      (await _preferences).getString(_proofKey);

  @override
  Future<void> writeProof(String proof) async {
    await (await _preferences).setString(_proofKey, proof);
  }
}

/// 本地 journal 独立于登录 actor 分区；仅在服务端完整 ACK 后才删除。
final class StartupJournal {
  StartupJournal(this._store, {this.maxEvents = 128});

  final StartupJournalStore _store;
  final int maxEvents;

  Future<List<StartupTelemetryEvent>> read() async {
    final rawEvents = await _store.readEvents();
    final events = <StartupTelemetryEvent>[];
    for (final raw in rawEvents) {
      try {
        final decoded = jsonDecode(raw);
        if (decoded is Map) {
          final event = _parseStoredStartupTelemetryEvent(
            decoded.map((key, value) => MapEntry(key.toString(), value)),
          );
          if (event != null) {
            events.add(event);
          }
        }
      } catch (_) {
        // 单条损坏记录不可阻断后续启动；下次写入时会被丢弃。
      }
    }
    return events;
  }

  /// Returns the number of oldest events evicted by the bounded queue.
  Future<int> append(StartupTelemetryEvent event) async {
    final rawEvents = await _store.readEvents();
    final knownEventIds = <String>{};
    for (final raw in rawEvents) {
      try {
        final decoded = jsonDecode(raw);
        if (decoded is Map) {
          final event = _parseStoredStartupTelemetryEvent(
            decoded.map((key, value) => MapEntry(key.toString(), value)),
          );
          if (event != null) {
            knownEventIds.add(event.eventId);
          }
        }
      } catch (_) {
        // 损坏记录继续保留，避免在 journal 写入失败时丢失其他有效事件。
      }
    }
    if (knownEventIds.contains(event.eventId)) {
      return 0;
    }
    final next = <String>[...rawEvents, jsonEncode(event.toJson())];
    final overflow = next.length - maxEvents;
    await _store.writeEvents(overflow > 0 ? next.sublist(overflow) : next);
    return overflow > 0 ? overflow : 0;
  }

  Future<void> acknowledge(List<StartupTelemetryEvent> sent) async {
    final acknowledged = sent.map((event) => event.eventId).toSet();
    final remaining = <String>[];
    for (final raw in await _store.readEvents()) {
      try {
        final decoded = jsonDecode(raw);
        final eventId = decoded is Map ? decoded['eventId']?.toString() : '';
        if (!acknowledged.contains(eventId)) {
          remaining.add(raw);
        }
      } catch (_) {
        // 损坏项不具备可靠 ID，继续保留直至容量策略清理。
        remaining.add(raw);
      }
    }
    await _store.writeEvents(remaining);
  }

  Future<String> proof() async {
    // proof 只用于匿名入口限流/校验；服务端按每批 canonical body 计算
    // batch digest，不能把该长期凭据当作跨批幂等键。
    final existing = (await _store.readProof())?.trim() ?? '';
    if (StartupTelemetrySupport.isValidProof(existing)) {
      return existing;
    }
    final next = StartupTelemetrySupport.randomUrlSafeToken(32);
    await _store.writeProof(next);
    return next;
  }

  Future<_NativeStartupJournal> _importNativeJournal() async {
    final nativeJournal = await readStartupNativeJournal();
    final attemptId = nativeJournal.attemptId.trim();
    final rawEvents = List<String>.from(nativeJournal.events)
      ..sort(
        (left, right) => _rawStartupTelemetrySequence(
          left,
        ).compareTo(_rawStartupTelemetrySequence(right)),
      );
    if (rawEvents.isEmpty) {
      return _NativeStartupJournal(
        attemptId: attemptId,
        events: const [],
        sourceCleared: true,
      );
    }
    final imported = <StartupTelemetryEvent>[];
    var persistedEveryValidEvent = true;
    for (final raw in rawEvents) {
      StartupTelemetryEvent? event;
      try {
        final decoded = jsonDecode(raw);
        if (decoded is! Map) {
          continue;
        }
        event = _parseStoredStartupTelemetryEvent(
          decoded.map((key, value) => MapEntry(key.toString(), value)),
        );
        if (event == null) {
          continue;
        }
      } catch (_) {
        // 受损 native 记录不应阻断 Flutter 首帧；清掉无法解析的项可避免永久重试。
        continue;
      }
      imported.add(event);
      try {
        await append(event);
      } catch (_) {
        // 可靠 journal 暂不可写时，不能清掉 native 来源；下一次可用时按 eventId 去重补传。
        persistedEveryValidEvent = false;
      }
    }
    if (persistedEveryValidEvent) {
      try {
        await clearStartupNativeJournal();
        return _NativeStartupJournal(
          attemptId: attemptId,
          events: imported,
          sourceCleared: true,
        );
      } catch (_) {
        // 只要来源未确认清理，就在 flush 前继续尝试导入，避免首帧期存储竞态丢事件。
      }
    }
    return _NativeStartupJournal(
      attemptId: attemptId,
      events: imported,
      sourceCleared: false,
    );
  }
}

int _rawStartupTelemetrySequence(String raw) {
  try {
    final decoded = jsonDecode(raw);
    if (decoded is Map) {
      return int.tryParse(decoded['sequence']?.toString() ?? '') ?? 1 << 30;
    }
  } catch (_) {
    // 受损记录会在导入循环中被忽略；这里排到末尾即可。
  }
  return 1 << 30;
}

final class _NativeStartupJournal {
  const _NativeStartupJournal({
    required this.attemptId,
    required this.events,
    required this.sourceCleared,
  });

  final String attemptId;
  final List<StartupTelemetryEvent> events;
  final bool sourceCleared;
}

const Set<String> _alwaysReportedStartupOutcomes = <String>{
  'failed',
  'bootstrap_failure',
  'native_first_frame_timeout',
  'startup_deadline',
  'bootstrap_error',
  'unhandled_rejection',
  'pagehide_before_first_frame',
  'journal_drop',
};

/// 固定哈希避免依赖进程随机化的 [String.hashCode]，使同一次启动在离线补传时保持同一采样决策。
bool _isStartupAttemptDetailedSampled(String attemptId) {
  var hash = 0x811c9dc5;
  for (final codeUnit in attemptId.codeUnits) {
    hash ^= codeUnit;
    hash = (hash * 0x01000193) & 0x7fffffff;
  }
  return hash % 5 == 0;
}

/// 单进程协调器：先落盘，再非阻塞上报；失败、部分 ACK 或离线时保留原事件。
final class StartupTelemetryReporter {
  static const int _maxRemoteBatchSize = 32;

  factory StartupTelemetryReporter({
    required StartupJournal journal,
    StartupTelemetryTransport? transport,
    required String platform,
    required String runtimeEnv,
    required String appVersion,
    String initialAttemptId = '',
    bool Function(String attemptId)? isDetailedAttemptSampled,
  }) {
    return StartupTelemetryReporter._(
      journal,
      transport,
      platform,
      runtimeEnv,
      appVersion,
      initialAttemptId,
      isDetailedAttemptSampled ?? _isStartupAttemptDetailedSampled,
    );
  }

  StartupTelemetryReporter._(
    this._journal,
    this._transport,
    this._platform,
    this._runtimeEnv,
    this._appVersion,
    this._initialAttemptId,
    this._isDetailedAttemptSampled,
  );

  final StartupJournal _journal;
  StartupTelemetryTransport? _transport;
  final String _platform;
  final String _runtimeEnv;
  final String _appVersion;
  final String _initialAttemptId;
  final bool Function(String attemptId) _isDetailedAttemptSampled;
  late final StartupAttempt _attempt;
  Future<void>? _startFuture;
  Future<void> _serial = Future<void>.value();
  int _sequence = 0;
  int _lastElapsedMs = 0;
  bool _nativePreFlutterImported = false;
  bool _nativeJournalDrained = false;
  bool _terminalRecorded = false;
  final List<StartupTelemetryEvent> _volatilePending =
      <StartupTelemetryEvent>[];
  int _journalDroppedEvents = 0;

  void attachTransport(StartupTelemetryTransport transport) {
    final current = _transport;
    if (current != null && !identical(current, transport)) {
      throw StateError('startup telemetry transport is already attached');
    }
    _transport = transport;
  }

  Future<void> start() {
    return _startFuture ??= _start();
  }

  Future<void> _start() async {
    var nativeAttemptId = '';
    try {
      final nativeJournal = await _journal._importNativeJournal();
      nativeAttemptId = nativeJournal.attemptId;
      _nativeJournalDrained = nativeJournal.sourceCleared;
      _absorbNativeEvents(nativeJournal.events, attemptId: nativeAttemptId);
    } catch (_) {
      // SharedPreferences / IndexedDB 不可用时退回内存尝试，不阻断启动。
    }
    var proof = '';
    try {
      proof = await _journal.proof();
    } catch (_) {
      proof = StartupTelemetrySupport.randomUrlSafeToken(32);
    }
    _attempt = StartupAttempt(
      id: StartupTelemetrySupport.isValidAttemptId(nativeAttemptId)
          ? nativeAttemptId
          : StartupTelemetrySupport.isValidAttemptId(_initialAttemptId)
          ? _initialAttemptId
          : StartupTelemetrySupport.randomUrlSafeToken(24),
      proof: proof,
      startedAt: DateTime.now().toUtc(),
    );
    try {
      for (final event in await _journal.read()) {
        if (event.attemptId == _attempt.id) {
          _sequence = max(_sequence, event.sequence);
          _lastElapsedMs = max(_lastElapsedMs, event.elapsedMs);
          _nativePreFlutterImported |=
              event.phase == StartupTelemetryPhase.nativePreFlutter;
          _terminalRecorded |= event.phase == StartupTelemetryPhase.terminal;
        }
      }
    } catch (_) {
      // 读取历史队列失败时继续使用新的 sequence。
    }
  }

  Future<void> record({
    required StartupTelemetryPhase phase,
    required int elapsedMs,
    required String outcome,
    ops_contracts.StartupRecoverySurface? recoverySurface,
    ops_contracts.StartupRecoveryLifecycle? recoveryLifecycle,
    ops_contracts.StartupRecoveryMount? recoveryMount,
    ops_contracts.StartupRecoveryPhase? recoveryPhase,
    ops_contracts.StartupRecoveryAction? recoveryAction,
    String failureCode = '',
    String failureSource = '',
    String deadlineOrigin = '',
    String networkClass = '',
  }) {
    _serial = _serial
        .then((_) async {
          await start();
          if (!_hasCanonicalRecoveryShape(
            phase: phase,
            recoverySurface: recoverySurface,
            recoveryLifecycle: recoveryLifecycle,
            recoveryMount: recoveryMount,
            recoveryPhase: recoveryPhase,
            recoveryAction: recoveryAction,
          )) {
            return;
          }
          if (phase == StartupTelemetryPhase.nativePreFlutter &&
              _nativePreFlutterImported) {
            return;
          }
          if (phase == StartupTelemetryPhase.terminal && _terminalRecorded) {
            return;
          }
          final normalizedElapsed = elapsedMs.clamp(0, 86400000).toInt();
          final duration = max(0, normalizedElapsed - _lastElapsedMs);
          _lastElapsedMs = normalizedElapsed;
          final event = StartupTelemetryEvent(
            eventId: '${_attempt.id}_${++_sequence}',
            attemptId: _attempt.id,
            sequence: _sequence,
            phase: phase,
            phaseDurationMs: duration,
            elapsedMs: normalizedElapsed,
            outcome: StartupTelemetrySupport.sanitizeEnum(
              outcome,
              StartupTelemetrySupport.outcomes,
              fallback: 'unknown',
            ),
            occurredAt: DateTime.now().toUtc(),
            platform: StartupTelemetrySupport.sanitizeEnum(
              _platform,
              StartupTelemetrySupport.platforms,
              fallback: 'unknown',
            ),
            runtimeEnv: StartupTelemetrySupport.sanitizeEnum(
              _runtimeEnv,
              StartupTelemetrySupport.runtimeEnvs,
              fallback: 'unknown',
            ),
            appVersion: StartupTelemetrySupport.sanitizeAppVersion(_appVersion),
            networkClass: StartupTelemetrySupport.sanitizeEnum(
              networkClass,
              StartupTelemetrySupport.networkClasses,
              fallback: '',
            ),
            recoverySurface: recoverySurface,
            recoveryLifecycle: recoveryLifecycle,
            recoveryMount: recoveryMount,
            recoveryPhase: recoveryPhase,
            recoveryAction: recoveryAction,
            failureCode: StartupTelemetrySupport.sanitizeEnum(
              failureCode,
              StartupTelemetrySupport.failureCodes,
              fallback: '',
            ),
            failureSource: StartupTelemetrySupport.sanitizeEnum(
              failureSource,
              StartupTelemetrySupport.failureSources,
              fallback: '',
            ),
            deadlineOrigin: StartupTelemetrySupport.sanitizeEnum(
              deadlineOrigin,
              StartupTelemetrySupport.deadlineOrigins,
              fallback: '',
            ),
          );
          try {
            _journalDroppedEvents += await _journal.append(event);
          } catch (_) {
            _volatilePending.add(event);
          }
          _terminalRecorded |= phase == StartupTelemetryPhase.terminal;
        })
        .catchError((_) {
          // Journal 自身不得反向阻断启动；下一次记录仍可继续。
        });
    return _serial;
  }

  Future<void> flush() {
    _serial = _serial
        .then((_) async {
          await start();
          await _retryNativeJournalImportIfNeeded();
          await _persistVolatileEventsIfPossible();
          await _recordJournalDropIfNeeded();
          while (true) {
            final pending = await _reportablePendingEvents();
            if (pending.isEmpty) {
              return;
            }
            final recoveryBatch = pending.first.isRecoveryTelemetry;
            final batch = pending
                .where((event) => event.isRecoveryTelemetry == recoveryBatch)
                .take(_maxRemoteBatchSize)
                .toList(growable: false);
            final transport = _transport;
            if (transport == null) {
              return;
            }
            final ack = await transport.report(batch, proof: _attempt.proof);
            if (!ack.acknowledges(batch.length)) {
              return;
            }
            for (final attemptId
                in batch.map((event) => event.attemptId).toSet()) {
              developer.log(
                'QWQStartup startup_telemetry_ack attemptId=$attemptId '
                'acceptedCount=${ack.acceptedCount} '
                'duplicateCount=${ack.duplicateCount}',
                name: 'QWQStartup',
              );
            }
            try {
              await _journal.acknowledge(batch);
            } catch (_) {
              // 已确认的内存项仍可安全移除；磁盘项会被服务端按 eventId 去重。
              final acknowledged = batch.map((event) => event.eventId).toSet();
              _volatilePending.removeWhere(
                (event) => acknowledged.contains(event.eventId),
              );
              return;
            }
            final acknowledged = batch.map((event) => event.eventId).toSet();
            _volatilePending.removeWhere(
              (event) => acknowledged.contains(event.eventId),
            );
          }
        })
        .catchError((_) {
          // 网络错误、限流和部分 ACK 都保留 journal，等待本次或下次成功启动。
        });
    return _serial;
  }

  Future<void> _persistVolatileEventsIfPossible() async {
    if (_volatilePending.isEmpty) {
      return;
    }
    final persisted = <String>{};
    for (final event in _volatilePending) {
      try {
        _journalDroppedEvents += await _journal.append(event);
        persisted.add(event.eventId);
      } catch (_) {
        // 插件尚未延后注册完成时继续保留内存副本。
      }
    }
    _volatilePending.removeWhere((event) => persisted.contains(event.eventId));
  }

  Future<void> _retryNativeJournalImportIfNeeded() async {
    if (_nativeJournalDrained) {
      return;
    }
    try {
      final nativeJournal = await _journal._importNativeJournal();
      _nativeJournalDrained = nativeJournal.sourceCleared;
      _absorbNativeEvents(nativeJournal.events, attemptId: _attempt.id);
    } catch (_) {
      // 启动 journal 仍不可用时继续保留 native 来源，不阻断当前 Shell。
    }
  }

  Future<void> _recordJournalDropIfNeeded() async {
    if (_journalDroppedEvents == 0) {
      return;
    }
    _journalDroppedEvents = 0;
    final event = StartupTelemetryEvent(
      eventId: '${_attempt.id}_${++_sequence}',
      attemptId: _attempt.id,
      sequence: _sequence,
      phase: StartupTelemetryPhase.terminal,
      phaseDurationMs: 0,
      elapsedMs: _lastElapsedMs,
      outcome: 'journal_drop',
      occurredAt: DateTime.now().toUtc(),
      platform: StartupTelemetrySupport.sanitizeEnum(
        _platform,
        StartupTelemetrySupport.platforms,
        fallback: 'unknown',
      ),
      runtimeEnv: StartupTelemetrySupport.sanitizeEnum(
        _runtimeEnv,
        StartupTelemetrySupport.runtimeEnvs,
        fallback: 'unknown',
      ),
      appVersion: StartupTelemetrySupport.sanitizeAppVersion(_appVersion),
      networkClass: '',
      failureCode: '',
      failureSource: '',
      deadlineOrigin: '',
    );
    try {
      await _journal.append(event);
    } catch (_) {
      _volatilePending.add(event);
    }
  }

  Future<List<StartupTelemetryEvent>> _pendingEvents() async {
    final byId = <String, StartupTelemetryEvent>{
      for (final event in _volatilePending) event.eventId: event,
    };
    try {
      for (final event in await _journal.read()) {
        byId[event.eventId] = event;
      }
    } catch (_) {
      // 仅用内存项继续尝试；ACK 后仍会保留无法读出的磁盘项以供下次补传。
    }
    final pending = byId.values.toList(growable: false)
      ..sort((left, right) {
        final sequenceOrder = left.sequence.compareTo(right.sequence);
        return sequenceOrder != 0
            ? sequenceOrder
            : left.eventId.compareTo(right.eventId);
      });
    return pending;
  }

  Future<List<StartupTelemetryEvent>> _reportablePendingEvents() async {
    final pending = await _pendingEvents();
    final sampledOut = pending
        .where((event) => !_shouldReport(event))
        .toList(growable: false);
    if (sampledOut.isNotEmpty) {
      try {
        await _journal.acknowledge(sampledOut);
        final discarded = sampledOut.map((event) => event.eventId).toSet();
        _volatilePending.removeWhere(
          (event) => discarded.contains(event.eventId),
        );
      } catch (_) {
        // 无法确认清理时保留原记录；下一轮会再次决定是否采样。
      }
    }
    return pending.where(_shouldReport).toList(growable: false);
  }

  bool _shouldReport(StartupTelemetryEvent event) {
    if (event.phase == StartupTelemetryPhase.nativePreFlutter ||
        event.phase == StartupTelemetryPhase.terminal ||
        event.phase == StartupTelemetryPhase.recovery ||
        event.phase == StartupTelemetryPhase.routerFailure ||
        event.failureCode.isNotEmpty ||
        _alwaysReportedStartupOutcomes.contains(event.outcome)) {
      return true;
    }
    return _isDetailedAttemptSampled(event.attemptId);
  }

  void _absorbNativeEvents(
    Iterable<StartupTelemetryEvent> events, {
    required String attemptId,
  }) {
    for (final event in events) {
      if (event.attemptId != attemptId) {
        continue;
      }
      _sequence = max(_sequence, event.sequence);
      _lastElapsedMs = max(_lastElapsedMs, event.elapsedMs);
      _nativePreFlutterImported |=
          event.phase == StartupTelemetryPhase.nativePreFlutter;
      _terminalRecorded |= event.phase == StartupTelemetryPhase.terminal;
    }
  }
}

/// 启动路径共享的 best-effort 门面。
///
/// 配置失败或尚未装配 transport 时事件不会抛回 UI；成功装配后每次写入均先持久化，
/// 由 [flush] 尝试发送未确认的历史启动记录。
final class StartupTelemetryRuntime {
  StartupTelemetryRuntime._();

  static final StartupTelemetryRuntime instance = StartupTelemetryRuntime._();

  StartupTelemetryReporter? _reporter;
  final List<_PendingStartupTelemetryRecord> _preFirstFrameRecords =
      <_PendingStartupTelemetryRecord>[];
  bool _firstFrameActivated = false;
  bool _activationComplete = false;
  bool _safeTerminalReached = false;
  Future<void>? _activation;

  bool get isInitialized => _reporter != null;

  /// 安装唯一 journal/reporter。该调用可以发生在 runtime config 校验之前，
  /// 但不会触发远端请求；transport 必须由 [attachTransport] 在校验后单独挂接。
  void initialize(StartupTelemetryReporter reporter) {
    final current = _reporter;
    if (current != null && !identical(current, reporter)) {
      throw StateError('startup telemetry reporter is already initialized');
    }
    _reporter = reporter;
    if (_firstFrameActivated && !_activationComplete && _activation == null) {
      _activation = _activate(reporter);
      unawaited(_activation!);
    }
  }

  /// runtime config 已完成 canonical 校验后，才允许把同一个 journal 接到 Remote。
  void attachTransport(StartupTelemetryTransport transport) {
    final reporter = _reporter;
    if (reporter == null) {
      throw StateError('startup telemetry reporter is not initialized');
    }
    reporter.attachTransport(transport);
    if (_safeTerminalReached && _activationComplete) {
      unawaited(reporter.flush());
    }
  }

  void resetForTesting() {
    _reporter = null;
    _preFirstFrameRecords.clear();
    _firstFrameActivated = false;
    _activationComplete = false;
    _safeTerminalReached = false;
    _activation = null;
  }

  /// 首帧已经真实提交后才允许读写 durable journal 或导入 native journal。
  ///
  /// 这不是 safe terminal：远端 HTTP 仍需等到 router shell / recovery 实际绘制。
  void activateAfterFirstFrame() {
    if (_firstFrameActivated) {
      return;
    }
    _firstFrameActivated = true;
    final reporter = _reporter;
    if (reporter == null) {
      return;
    }
    _activation = _activate(reporter);
    unawaited(_activation!);
  }

  Future<void> _activate(StartupTelemetryReporter reporter) async {
    try {
      await reporter.start();
      while (_preFirstFrameRecords.isNotEmpty) {
        final batch = List<_PendingStartupTelemetryRecord>.from(
          _preFirstFrameRecords,
        );
        _preFirstFrameRecords.clear();
        for (final record in batch) {
          await reporter.record(
            phase: record.phase,
            elapsedMs: record.elapsedMs,
            outcome: record.outcome,
            recoverySurface: record.recoverySurface,
            recoveryLifecycle: record.recoveryLifecycle,
            recoveryMount: record.recoveryMount,
            recoveryPhase: record.recoveryPhase,
            recoveryAction: record.recoveryAction,
            failureCode: record.failureCode,
            failureSource: record.failureSource,
            deadlineOrigin: record.deadlineOrigin,
            networkClass: record.networkClass,
          );
        }
      }
    } catch (_) {
      // 启动遥测不能反向阻断已经展示的 Flutter 首帧。
    } finally {
      _activationComplete = true;
      if (_safeTerminalReached) {
        unawaited(reporter.flush());
      }
    }
  }

  /// 只有可操作 Shell 或 Flutter recovery 已真实绘制后才允许远端补传。
  void markSafeTerminal() {
    _safeTerminalReached = true;
    final reporter = _reporter;
    if (reporter != null && _activationComplete) {
      unawaited(reporter.flush());
    }
  }

  void record({
    required StartupTelemetryPhase phase,
    required int elapsedMs,
    required String outcome,
    ops_contracts.StartupRecoverySurface? recoverySurface,
    ops_contracts.StartupRecoveryLifecycle? recoveryLifecycle,
    ops_contracts.StartupRecoveryMount? recoveryMount,
    ops_contracts.StartupRecoveryPhase? recoveryPhase,
    ops_contracts.StartupRecoveryAction? recoveryAction,
    String failureCode = '',
    String failureSource = '',
    String deadlineOrigin = '',
    String networkClass = '',
  }) {
    final pending = _PendingStartupTelemetryRecord(
      phase: phase,
      elapsedMs: elapsedMs,
      outcome: outcome,
      recoverySurface: recoverySurface,
      recoveryLifecycle: recoveryLifecycle,
      recoveryMount: recoveryMount,
      recoveryPhase: recoveryPhase,
      recoveryAction: recoveryAction,
      failureCode: failureCode,
      failureSource: failureSource,
      deadlineOrigin: deadlineOrigin,
      networkClass: networkClass,
    );
    final reporter = _reporter;
    if (reporter == null || !_activationComplete) {
      _preFirstFrameRecords.add(pending);
      return;
    }
    final write = reporter.record(
      phase: pending.phase,
      elapsedMs: pending.elapsedMs,
      outcome: pending.outcome,
      recoverySurface: pending.recoverySurface,
      recoveryLifecycle: pending.recoveryLifecycle,
      recoveryMount: pending.recoveryMount,
      recoveryPhase: pending.recoveryPhase,
      recoveryAction: pending.recoveryAction,
      failureCode: pending.failureCode,
      failureSource: pending.failureSource,
      deadlineOrigin: pending.deadlineOrigin,
      networkClass: pending.networkClass,
    );
    if (_safeTerminalReached) {
      unawaited(write.then((_) => reporter.flush()));
    } else {
      unawaited(write);
    }
  }

  void flush() {
    final reporter = _reporter;
    if (reporter != null && _safeTerminalReached && _activationComplete) {
      unawaited(reporter.flush());
    }
  }
}

/// `page.app.startup_recovery` 的唯一 typed telemetry session。
///
/// Session 只写入 [StartupTelemetryRuntime] 已拥有的 journal；它不创建第二个
/// outbox，也不接受自由字符串 surface/mount/phase/action。单个真实挂载期间的
/// 重复 lifecycle 会按 canonical tuple 去重。
final class RecoverySurfaceTelemetrySession {
  RecoverySurfaceTelemetrySession({
    required this.mount,
    required ops_contracts.StartupRecoveryPhase initialPhase,
    required this.elapsedMs,
    String failureCode = '',
    String failureSource = '',
  }) : _phase = initialPhase {
    _record(
      lifecycle: ops_contracts.StartupRecoveryLifecycle.enter,
      action: ops_contracts.StartupRecoveryAction.none,
      outcome: 'entered',
    );
    if (failureCode.trim().isNotEmpty || failureSource.trim().isNotEmpty) {
      failure(failureCode: failureCode, failureSource: failureSource);
    }
  }

  final ops_contracts.StartupRecoveryMount mount;
  final int Function() elapsedMs;
  final Set<String> _emitted = <String>{};
  ops_contracts.StartupRecoveryPhase _phase;
  bool _closed = false;

  ops_contracts.StartupRecoveryPhase get phase => _phase;

  void phaseChanged(ops_contracts.StartupRecoveryPhase next) {
    if (_closed || next == _phase) {
      return;
    }
    _phase = next;
    _record(
      lifecycle: ops_contracts.StartupRecoveryLifecycle.phaseChange,
      action: ops_contracts.StartupRecoveryAction.none,
      outcome: 'observed',
    );
  }

  void externalAction({
    required ops_contracts.StartupRecoveryAction action,
    required String outcome,
  }) {
    if (_closed ||
        action == ops_contracts.StartupRecoveryAction.none ||
        action == ops_contracts.StartupRecoveryAction.runtimeReentry) {
      return;
    }
    _record(
      lifecycle: ops_contracts.StartupRecoveryLifecycle.externalAction,
      action: action,
      outcome: outcome,
    );
  }

  void runtimeReentry({required String outcome}) {
    if (_closed) {
      return;
    }
    _record(
      lifecycle: ops_contracts.StartupRecoveryLifecycle.runtimeReentry,
      action: ops_contracts.StartupRecoveryAction.runtimeReentry,
      outcome: outcome,
    );
  }

  void failure({String failureCode = '', String failureSource = ''}) {
    if (_closed) {
      return;
    }
    _record(
      lifecycle: ops_contracts.StartupRecoveryLifecycle.failure,
      action: ops_contracts.StartupRecoveryAction.none,
      outcome: 'failed',
      failureCode: failureCode,
      failureSource: failureSource,
    );
  }

  void exit({required String outcome}) {
    if (_closed) {
      return;
    }
    _record(
      lifecycle: ops_contracts.StartupRecoveryLifecycle.exit,
      action: ops_contracts.StartupRecoveryAction.none,
      outcome: outcome,
    );
    _closed = true;
  }

  void _record({
    required ops_contracts.StartupRecoveryLifecycle lifecycle,
    required ops_contracts.StartupRecoveryAction action,
    required String outcome,
    String failureCode = '',
    String failureSource = '',
  }) {
    final key = <String>[
      lifecycle.wireName,
      _phase.wireName,
      action.wireName,
      outcome,
      failureCode.trim(),
      failureSource.trim(),
    ].join('|');
    if (!_emitted.add(key)) {
      return;
    }
    StartupTelemetryRuntime.instance.record(
      phase: StartupTelemetryPhase.recovery,
      elapsedMs: elapsedMs(),
      outcome: outcome,
      recoverySurface:
          ops_contracts.StartupRecoverySurface.pageAppStartupRecovery,
      recoveryLifecycle: lifecycle,
      recoveryMount: mount,
      recoveryPhase: _phase,
      recoveryAction: action,
      failureCode: failureCode,
      failureSource: failureSource,
    );
  }
}

bool _hasCanonicalRecoveryShape({
  required StartupTelemetryPhase phase,
  required ops_contracts.StartupRecoverySurface? recoverySurface,
  required ops_contracts.StartupRecoveryLifecycle? recoveryLifecycle,
  required ops_contracts.StartupRecoveryMount? recoveryMount,
  required ops_contracts.StartupRecoveryPhase? recoveryPhase,
  required ops_contracts.StartupRecoveryAction? recoveryAction,
}) {
  final hasAny =
      recoverySurface != null ||
      recoveryLifecycle != null ||
      recoveryMount != null ||
      recoveryPhase != null ||
      recoveryAction != null;
  if (phase != StartupTelemetryPhase.recovery) {
    return !hasAny;
  }
  return recoverySurface ==
          ops_contracts.StartupRecoverySurface.pageAppStartupRecovery &&
      recoveryLifecycle != null &&
      recoveryMount != null &&
      recoveryPhase != null &&
      recoveryAction != null;
}

T? _parseRecoveryEnum<T>(
  Object? raw,
  String path,
  T Function(Object? value, String path) parse,
) {
  if (raw == null || raw.toString().trim().isEmpty) {
    return null;
  }
  try {
    return parse(raw, path);
  } on FormatException {
    return null;
  }
}

StartupTelemetryEvent? _parseStoredStartupTelemetryEvent(
  Map<String, Object?> json,
) {
  StartupTelemetryPhase? phase;
  for (final candidate in StartupTelemetryPhase.values) {
    if (candidate.wireName == json['phase']?.toString()) {
      phase = candidate;
      break;
    }
  }
  final eventId = json['eventId']?.toString().trim() ?? '';
  final attemptId = json['attemptId']?.toString().trim() ?? '';
  final sequence = StartupTelemetrySupport.asInt(json['sequence']);
  final phaseDurationMs = StartupTelemetrySupport.asInt(
    json['phaseDurationMs'],
  );
  final elapsedMs = StartupTelemetrySupport.asInt(json['elapsedMs']);
  final occurredAt = DateTime.tryParse(
    json['occurredAt']?.toString() ?? '',
  )?.toUtc();
  if (phase == null ||
      !StartupTelemetrySupport.isValidAttemptId(eventId) ||
      !StartupTelemetrySupport.isValidAttemptId(attemptId) ||
      sequence < 0 ||
      sequence > 10000 ||
      eventId != '${attemptId}_$sequence' ||
      phaseDurationMs < 0 ||
      phaseDurationMs > 60000 ||
      elapsedMs < 0 ||
      elapsedMs > 86400000 ||
      occurredAt == null) {
    return null;
  }
  final recoverySurface =
      _parseRecoveryEnum<ops_contracts.StartupRecoverySurface>(
        json['recoverySurface'],
        'startupTelemetry.recoverySurface',
        ops_contracts.StartupRecoverySurface.fromWire,
      );
  final recoveryLifecycle =
      _parseRecoveryEnum<ops_contracts.StartupRecoveryLifecycle>(
        json['recoveryLifecycle'],
        'startupTelemetry.recoveryLifecycle',
        ops_contracts.StartupRecoveryLifecycle.fromWire,
      );
  final recoveryMount = _parseRecoveryEnum<ops_contracts.StartupRecoveryMount>(
    json['recoveryMount'],
    'startupTelemetry.recoveryMount',
    ops_contracts.StartupRecoveryMount.fromWire,
  );
  final recoveryPhase = _parseRecoveryEnum<ops_contracts.StartupRecoveryPhase>(
    json['recoveryPhase'],
    'startupTelemetry.recoveryPhase',
    ops_contracts.StartupRecoveryPhase.fromWire,
  );
  final recoveryAction =
      _parseRecoveryEnum<ops_contracts.StartupRecoveryAction>(
        json['recoveryAction'],
        'startupTelemetry.recoveryAction',
        ops_contracts.StartupRecoveryAction.fromWire,
      );
  final hasNonBlankRecoveryWire = <String>[
    'recoverySurface',
    'recoveryLifecycle',
    'recoveryMount',
    'recoveryPhase',
    'recoveryAction',
  ].any((key) => (json[key]?.toString().trim() ?? '').isNotEmpty);
  if (phase != StartupTelemetryPhase.recovery && hasNonBlankRecoveryWire) {
    return null;
  }
  if (!_hasCanonicalRecoveryShape(
    phase: phase,
    recoverySurface: recoverySurface,
    recoveryLifecycle: recoveryLifecycle,
    recoveryMount: recoveryMount,
    recoveryPhase: recoveryPhase,
    recoveryAction: recoveryAction,
  )) {
    // 旧 `phase=recovery` 只有自由字符串 surface，缺少 canonical lifecycle、
    // mount、phase、action；硬切后必须丢弃，不能 dual-read 或补默认值。
    return null;
  }
  return StartupTelemetryEvent(
    eventId: eventId,
    attemptId: attemptId,
    sequence: sequence,
    phase: phase,
    phaseDurationMs: phaseDurationMs,
    elapsedMs: elapsedMs,
    outcome: StartupTelemetrySupport.sanitizeEnum(
      json['outcome']?.toString() ?? '',
      StartupTelemetrySupport.outcomes,
      fallback: 'unknown',
    ),
    occurredAt: occurredAt,
    platform: StartupTelemetrySupport.sanitizeEnum(
      json['platform']?.toString() ?? '',
      StartupTelemetrySupport.platforms,
      fallback: 'unknown',
    ),
    runtimeEnv: StartupTelemetrySupport.sanitizeEnum(
      json['runtimeEnv']?.toString() ?? '',
      StartupTelemetrySupport.runtimeEnvs,
      fallback: 'unknown',
    ),
    appVersion: StartupTelemetrySupport.sanitizeAppVersion(
      json['appVersion']?.toString() ?? '',
    ),
    networkClass: StartupTelemetrySupport.sanitizeEnum(
      json['networkClass']?.toString() ?? '',
      StartupTelemetrySupport.networkClasses,
      fallback: '',
    ),
    recoverySurface: recoverySurface,
    recoveryLifecycle: recoveryLifecycle,
    recoveryMount: recoveryMount,
    recoveryPhase: recoveryPhase,
    recoveryAction: recoveryAction,
    failureCode: StartupTelemetrySupport.sanitizeEnum(
      json['failureCode']?.toString() ?? '',
      StartupTelemetrySupport.failureCodes,
      fallback: '',
    ),
    failureSource: StartupTelemetrySupport.sanitizeEnum(
      json['failureSource']?.toString() ?? '',
      StartupTelemetrySupport.failureSources,
      fallback: '',
    ),
    deadlineOrigin: StartupTelemetrySupport.sanitizeEnum(
      json['deadlineOrigin']?.toString() ?? '',
      StartupTelemetrySupport.deadlineOrigins,
      fallback: '',
    ),
  );
}

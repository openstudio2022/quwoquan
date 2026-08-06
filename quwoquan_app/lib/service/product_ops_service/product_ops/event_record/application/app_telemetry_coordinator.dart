// ignore_for_file: prefer_initializing_formals

import 'dart:async';
import 'dart:developer' as developer;

import 'package:quwoquan_app/runtime/context/actor_queue_partition.dart';
import 'package:quwoquan_app/runtime/observability/generated/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_context_provider.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_outbox.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_reporter.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_session_store.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_transport.dart';
import 'package:quwoquan_app/runtime/transport/actor_queue/actor_queue_storage.dart';

/// 保持 Reporter 调用面稳定，同时在登录、登出或切号时原子替换 actor-scoped
/// outbox。旧主体队列只删除，绝不使用新主体凭据重放。
final class AppTelemetryCoordinator implements AppTelemetryRecorder {
  AppTelemetryCoordinator({
    required AppTelemetrySessionStore sessionStore,
    required AppTelemetryContextProvider contextProvider,
    required ActorQueueStorage queueStorage,
    required AppTelemetryTransport transport,
    required ActorQueuePartition initialPartition,
    required String initialActorKey,
  }) : _sessionStore = sessionStore,
       _contextProvider = contextProvider,
       _queueStorage = queueStorage,
       _transport = transport {
    _sessionStore.updateActor(initialActorKey, reason: 'telemetry_bind');
    _active = _createActive(initialPartition);
  }

  final AppTelemetrySessionStore _sessionStore;
  final AppTelemetryContextProvider _contextProvider;
  final ActorQueueStorage _queueStorage;
  final AppTelemetryTransport _transport;
  late _ActiveTelemetryReporter _active;
  bool _disposed = false;

  void transition({
    required ActorQueuePartition partition,
    required String actorKey,
  }) {
    if (_disposed) return;
    _sessionStore.updateActor(actorKey, reason: 'auth_actor_changed');
    if (_active.partition.key == partition.key) return;
    final previous = _active;
    _active = _createActive(partition);
    unawaited(previous.reporter.dispose());
    unawaited(
      previous.outbox.purge().catchError((Object error, StackTrace stackTrace) {
        developer.log(
          'telemetry old actor outbox purge failed',
          name: 'AppTelemetryCoordinator',
          error: error,
          stackTrace: stackTrace,
        );
      }),
    );
  }

  @override
  Future<AppTelemetryRecordResult> record(
    AppTelemetryPayload payload, {
    String? pageName,
    DateTime? occurredAt,
  }) => _active.reporter.record(
    payload,
    pageName: pageName,
    occurredAt: occurredAt,
  );

  @override
  Future<AppTelemetryFlushResult> flush() => _active.reporter.flush();

  @override
  void onNetworkAvailable() => _active.reporter.onNetworkAvailable();

  @override
  Future<void> clearPendingForLogout() => _active.outbox.purge();

  Future<void> dispose() async {
    if (_disposed) return;
    _disposed = true;
    await _active.reporter.dispose();
  }

  _ActiveTelemetryReporter _createActive(ActorQueuePartition partition) {
    final outbox = AppTelemetryOutbox(
      partition: partition,
      storage: _queueStorage,
      transport: _transport,
    );
    return _ActiveTelemetryReporter(
      partition: partition,
      outbox: outbox,
      reporter: AppTelemetryReporter(
        sessionStore: _sessionStore,
        contextProvider: _contextProvider,
        outbox: outbox,
      ),
    );
  }
}

final class _ActiveTelemetryReporter {
  const _ActiveTelemetryReporter({
    required this.partition,
    required this.outbox,
    required this.reporter,
  });

  final ActorQueuePartition partition;
  final AppTelemetryOutbox outbox;
  final AppTelemetryReporter reporter;
}

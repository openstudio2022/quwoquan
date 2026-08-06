import 'dart:async';
import 'dart:developer' as developer;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/observability/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/runtime/transport/cloud_request_headers.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/context/actor_queue_partition.dart';
import 'package:quwoquan_app/runtime/observability/generated/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/adapters/content_behavior_outbox_adapter.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/ops_event_record_dependencies.dart';
import 'package:quwoquan_app/runtime/di/runtime_observability_dependencies.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_context_provider.dart';
import 'package:quwoquan_app/service/product_ops_service/product_ops/event_record/application/app_telemetry_coordinator.dart';
import 'package:quwoquan_app/service/product_ops_service/product_ops/event_record/adapters/app_telemetry_transport_remote.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_outbox.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_reporter.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_session_store.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_transport.dart';
import 'package:quwoquan_app/runtime/transport/actor_queue/actor_queue_storage.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_page_experience_tracker.dart';

final actorQueueStorageProvider = Provider<ActorQueueStorage>((ref) {
  return ActorQueueStorage();
});

final actorQueueSessionBoundaryProvider = Provider<ActorQueueSessionBoundary>((
  ref,
) {
  return ActorQueueSessionBoundary(
    storage: ref.watch(actorQueueStorageProvider),
    queueNames: const <String>[
      kBehaviorPendingQueueBoxName,
      kAssistantLearningFactOutboxName,
    ],
  );
});

final appTelemetrySessionStoreProvider = Provider<AppTelemetrySessionStore>((
  ref,
) {
  return AppTelemetrySessionStore.instance;
});

final appTelemetryContextProvider = Provider<AppTelemetryContextProvider>((
  ref,
) {
  return AppTelemetryContextProvider.instance;
});

final appTelemetryTransportProvider = Provider<AppTelemetryTransport>((ref) {
  return CloudAppTelemetryTransport(
    ref.watch(opsEventRecordBatchWriterProvider),
  );
});

/// 产品事件与异常的唯一 production 组合入口。这里不提供运行时 Mock/Remote
/// 分支；local_contract 通过 Provider override 注入测试 recorder。
final appTelemetryReporterProvider = Provider<AppTelemetryRecorder>((ref) {
  final sessionStore = ref.watch(appTelemetrySessionStoreProvider);
  final contextProvider = ref.watch(appTelemetryContextProvider);
  if (!sessionStore.isInitialized || !contextProvider.isInitialized) {
    // 完整应用在 runApp 前由 app_bootstrap.bootstrapForColdStart 同步就绪；
    // 局部 widget test / golden / 预览不会经过该入口，必须明确拒绝入云
    // 而不是伪造产品会话。
    return const _UnavailableAppTelemetryRecorder();
  }
  final queueStorage = ref.watch(actorQueueStorageProvider);
  final transport = ref.watch(appTelemetryTransportProvider);
  final initialAuth = ref.read(authSessionControllerProvider);
  final coordinator = AppTelemetryCoordinator(
    sessionStore: sessionStore,
    contextProvider: contextProvider,
    queueStorage: queueStorage,
    transport: transport,
    initialPartition: _partitionFor(initialAuth),
    initialActorKey: _actorKeyFor(initialAuth),
  );
  AppPageExperienceTracker.instance.attachReporter(coordinator);
  final networkSubscription = contextProvider.networkChanges.listen((value) {
    if (value != 'none') coordinator.onNetworkAvailable();
  });

  ref.listen<AuthSessionState>(authSessionControllerProvider, (previous, next) {
    if (previous != null) {
      unawaited(
        ref
            .read(actorQueueSessionBoundaryProvider)
            .transition(
              previous: _partitionFor(previous),
              current: _partitionFor(next),
            )
            .catchError((Object error, StackTrace stackTrace) {
              developer.log(
                'behavior queue session-boundary purge failed',
                name: 'ActorQueueSessionBoundary',
                error: error,
                stackTrace: stackTrace,
              );
            }),
      );
    }
    coordinator.transition(
      partition: _partitionFor(next),
      actorKey: _actorKeyFor(next),
    );
  });

  final runtimeLogger = ref.watch(runtimeLoggerProvider);
  AppExceptionTelemetryService.instance.bind(logger: runtimeLogger);
  ref.onDispose(() {
    AppExceptionTelemetryService.instance.unbind(runtimeLogger);
    AppPageExperienceTracker.instance.detachReporter(coordinator);
    unawaited(networkSubscription.cancel());
    unawaited(coordinator.dispose());
  });
  return coordinator;
});

ActorQueuePartition _partitionFor(AuthSessionState session) {
  final deviceId = (CloudRequestHeaders.deviceActorId ?? '').trim().isNotEmpty
      ? CloudRequestHeaders.deviceActorId!
      : session.installId;
  return ActorQueuePartition(
    environment: CloudRuntimeConfig.appRuntimeEnv,
    accountId: session.isAuthenticated ? session.ownerId : '',
    personaId: session.isAuthenticated ? session.activePersonaId : '',
    deviceId: deviceId,
  );
}

String _actorKeyFor(AuthSessionState session) =>
    session.isAuthenticated ? session.ownerId : '';

final class _UnavailableAppTelemetryRecorder implements AppTelemetryRecorder {
  const _UnavailableAppTelemetryRecorder();

  @override
  Future<void> clearPendingForLogout() async {}

  @override
  Future<AppTelemetryFlushResult> flush() async =>
      AppTelemetryFlushResult.empty;

  @override
  void onNetworkAvailable() {}

  @override
  Future<AppTelemetryRecordResult> record(
    AppTelemetryPayload payload, {
    String? pageName,
    DateTime? occurredAt,
  }) async => AppTelemetryRecordResult.rejected;
}

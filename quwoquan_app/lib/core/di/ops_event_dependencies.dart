import 'dart:async';
import 'dart:developer' as developer;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/context/actor_queue_partition.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/cloud/services/ops/ops_event_repository.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/di/app_data_source_mode.dart';
import 'package:quwoquan_app/core/di/cloud_http_client_provider.dart';
import 'package:quwoquan_app/infrastructure/local/actor_queue/actor_queue_storage.dart';

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
      kOpsEventQueueBoxName,
      kAppExceptionQueueBoxName,
    ],
  );
});

/// 统一 OpsEvent 组合入口，供 analytics、登录漏斗和全应用复用。
final opsEventRepositoryProvider = Provider<OpsEventRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  if (mode == AppDataSourceMode.mock) {
    AppExceptionTelemetryService.instance.unbind();
    return MockOpsEventRepository();
  }

  final session = ref.watch(authSessionControllerProvider);
  final queueStorage = ref.watch(actorQueueStorageProvider);
  final queuePartition = ActorQueuePartition(
    environment: CloudRuntimeConfig.appRuntimeEnv,
    accountId: session.ownerId,
    personaId: session.activeSubAccountId,
    deviceId: CloudRequestHeaders.deviceActorId ?? session.installId,
  );
  ref.listen<AuthSessionState>(authSessionControllerProvider, (previous, next) {
    if (previous == null) return;
    final previousPartition = ActorQueuePartition(
      environment: CloudRuntimeConfig.appRuntimeEnv,
      accountId: previous.ownerId,
      personaId: previous.activeSubAccountId,
      deviceId: CloudRequestHeaders.deviceActorId ?? previous.installId,
    );
    final currentPartition = ActorQueuePartition(
      environment: CloudRuntimeConfig.appRuntimeEnv,
      accountId: next.ownerId,
      personaId: next.activeSubAccountId,
      deviceId: CloudRequestHeaders.deviceActorId ?? next.installId,
    );
    unawaited(
      ref
          .read(actorQueueSessionBoundaryProvider)
          .transition(previous: previousPartition, current: currentPartition)
          .catchError((Object error, StackTrace stackTrace) {
            developer.log(
              'actor queue session-boundary purge failed',
              name: 'ActorQueueSessionBoundary',
              error: error,
              stackTrace: stackTrace,
            );
          }),
    );
  });
  final repository = RemoteOpsEventRepository(
    httpClient: ref.watch(cloudHttpClientProvider),
    queuePartition: queuePartition,
    queueStorage: queueStorage,
  );
  AppExceptionTelemetryService.instance.bind(
    eventRepository: repository,
    queuePartition: queuePartition,
    queueStorage: queueStorage,
  );
  ref.onDispose(repository.dispose);
  return repository;
});

import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/observability/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_learning_fact/application/assistant_learning_fact_outbox.dart';
import 'package:quwoquan_app/runtime/transport/cloud_request_headers.dart';
import 'package:quwoquan_app/runtime/context/actor_queue_partition.dart';
import 'package:quwoquan_app/runtime/di/ops_event_dependencies.dart';
import 'package:quwoquan_app/runtime/di/app_providers_app_state.dart';
import 'package:quwoquan_app/runtime/di/app_providers_client_sync.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// learning fact 追加的端侧待发队列规则：入队后立即尝试上行，失败按固定间隔重试，
/// 队列长度即 Notifier state。装配（Facet/存储/环境注入）留在组合根。
final class AssistantLearningFactOutboxNotifier extends Notifier<int> {
  static const Duration _retryInterval = Duration(seconds: 15);

  late AssistantLearningFactOutbox _outbox;
  Timer? _retryTimer;

  @override
  int build() {
    final accountId = ref.watch(resolvedOwnerUserIdProvider).trim();
    final personaId = ref.watch(currentUserIdProvider).trim();
    _outbox = AssistantLearningFactOutbox(
      ActorQueuePartition(
        environment: ref.watch(assistantLearningFactOutboxEnvironmentProvider),
        accountId: accountId,
        personaId: personaId,
        deviceId: CloudRequestHeaders.deviceActorId ?? '',
      ),
      ref.watch(actorQueueStorageProvider),
      ref.watch(assistantLearningFactAppendFacetProvider),
    );
    ref.onDispose(_outbox.dispose);
    ref.onDispose(() => _retryTimer?.cancel());
    unawaited(_restoreAndFlush());
    return 0;
  }

  Future<bool> enqueue(AssistantLearningFactAppendCommand fact) async {
    final persisted = await _outbox.enqueue(fact);
    if (!ref.mounted) {
      return persisted;
    }
    final pendingCount = await _outbox.pendingCount();
    if (!ref.mounted) {
      return persisted;
    }
    state = pendingCount;
    _scheduleRetry(pendingCount);
    if (persisted && ref.mounted) {
      unawaited(flush());
    }
    return persisted;
  }

  Future<void> flush() async {
    try {
      await _outbox.flush();
      if (!ref.mounted) {
        return;
      }
      final pendingCount = await _outbox.pendingCount();
      if (ref.mounted) {
        state = pendingCount;
        _scheduleRetry(pendingCount);
      }
    } catch (error, stackTrace) {
      // 学习事实同步失败静默会让助手个性化盲区不可发现，必须结构化上报。
      unawaited(
        AppExceptionTelemetryService.instance.recordHandledException(
          source: 'assistant.learning_fact_outbox.flush',
          error: error,
          stackTrace: stackTrace,
        ),
      );
    }
  }

  Future<void> _restoreAndFlush() async {
    try {
      if (!ref.mounted) {
        return;
      }
      final pendingCount = await _outbox.pendingCount();
      if (!ref.mounted) {
        return;
      }
      state = pendingCount;
      _scheduleRetry(pendingCount);
      if (pendingCount > 0) {
        await flush();
      }
    } catch (error, stackTrace) {
      unawaited(
        AppExceptionTelemetryService.instance.recordHandledException(
          source: 'assistant.learning_fact_outbox.restore',
          error: error,
          stackTrace: stackTrace,
        ),
      );
    }
  }

  void _scheduleRetry(int pendingCount) {
    _retryTimer?.cancel();
    _retryTimer = null;
    if (pendingCount <= 0 || !ref.mounted) {
      return;
    }
    _retryTimer = Timer(_retryInterval, () {
      if (ref.mounted) {
        unawaited(flush());
      }
    });
  }
}

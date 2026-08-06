import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/content_behavior_tracker.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_engagement_tracker.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_tracker_port.dart';
import 'package:quwoquan_app/runtime/di/feed_session_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/context/actor_queue_partition.dart';
import 'package:quwoquan_app/runtime/di/app_providers_app_state.dart';
import 'package:quwoquan_app/runtime/di/app_providers_content_facets.dart';
import 'package:quwoquan_app/runtime/di/content_dependencies.dart';
import 'package:quwoquan_app/runtime/di/ops_event_dependencies.dart';
import 'package:quwoquan_app/runtime/transport/cloud_request_headers.dart';

/// ContentBehaviorFact 的唯一 production 组合入口。
///
/// 四环境只装配 generated Remote command 与 actor-scoped durable outbox；
/// 业务页面和 tracker 只消费对象级 application port。
final behaviorRepositoryProvider = Provider<BehaviorRepository>((ref) {
  final feedSessionNotifier = ref.read(feedSessionProvider.notifier);
  final accountId = ref.watch(resolvedOwnerUserIdProvider).trim();
  final personaId = ref.watch(currentUserIdProvider).trim();
  final composition = ContentProductionComposition.behaviorRepository(
    writer: ref.watch(contentBehaviorCommandWriterProvider),
    queuePartition: ActorQueuePartition(
      environment: CloudRuntimeConfig.appRuntimeEnv,
      accountId: accountId,
      personaId: personaId,
      deviceId: CloudRequestHeaders.deviceActorId ?? '',
    ),
    queueStorage: ref.watch(actorQueueStorageProvider),
    feedSessionIdProvider: () => feedSessionNotifier.sessionId,
  );
  ref.onDispose(composition.dispose);
  return composition.repository;
});

/// 推荐反馈唯一上报端口。采集与计算逻辑不依赖 Remote/Hive 具体实现。
final behaviorReporterProvider = Provider<BehaviorReporter>(
  (ref) => ref.watch(behaviorRepositoryProvider),
);

final contentBehaviorTrackerProvider = Provider<ContentBehaviorTrackerPort>((
  ref,
) {
  final tracker = ContentBehaviorTracker(
    reporter: ref.watch(behaviorReporterProvider),
  );
  ref.onDispose(() => tracker.dispose());
  return tracker;
});

final contentEngagementTrackerProvider = Provider<ContentEngagementTracker>((
  ref,
) {
  final tracker = ContentEngagementTracker(
    reporter: ref.watch(behaviorReporterProvider),
  );
  ref.onDispose(() => tracker.dispose());
  return tracker;
});

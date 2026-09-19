import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/context/actor_queue_partition.dart';

/// 互动本地状态的唯一 actor 分区来源。
///
/// outbox、共享关系投影与内容互动投影必须落在同一 environment/account/persona/
/// device 维度：任何一个用固定全局 key 都会让切号后的旧快照污染新主体。
/// 身份来自 verified session，而不是从游客标记推断。
final actorInteractionPartitionProvider = Provider<ActorQueuePartition>((ref) {
  final session = ref.watch(authSessionControllerProvider);
  return ActorQueuePartition(
    environment:
        '${CloudRuntimeConfig.launchTarget}|${CloudRuntimeConfig.appEnvironment}',
    accountId: session.hasTrustedSession ? session.ownerId : '',
    personaId: session.hasTrustedSession ? session.activePersonaId : '',
    deviceId: session.installId,
  );
});

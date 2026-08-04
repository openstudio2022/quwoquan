import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_trace_context_store.dart';
import 'package:quwoquan_app/core/di/generated_operation_client_dependencies.dart';
import 'package:quwoquan_app/runtime/di/circle_dependencies.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    hide ContentDiscoveryFeedQuery;
import 'package:quwoquan_app/core/providers/app_providers_app_state.dart';
import 'package:quwoquan_app/core/providers/app_providers_chat_search.dart';
CloudOperationInvocationContext _circleOperationInvocationContext(
  Ref ref, {
  required AppUiSurface surface,
  required String clientPageId,
  required bool command,
  String? idempotencyKey,
}) {
  final accountId = ref.read(resolvedOwnerUserIdProvider).trim();
  final persona = ref.read(activePersonaContextProvider).asData?.value;
  final personaId = persona?.personaId.trim() ?? '';
  return CloudOperationInvocationContext(
    surfaceId: surface.id,
    clientPageId: clientPageId,
    routeId: surface.routeId,
    actor: CloudOperationActorContext(
      accountId: accountId.isEmpty ? null : accountId,
      personaId: personaId.isEmpty ? null : personaId,
    ),
    idempotencyKey: command
        ? (idempotencyKey ?? AppTraceContextStore.instance.newRequestId())
        : null,
  );
}

T _circlePort<T>(
  Ref ref,
  AppUiSurface surface,
  CircleProductionAdapter adapter,
) {
  return CircleProductionComposition.generatedAdapter<T>(
    adapter,
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId, {required command}) =>
        _circleOperationInvocationContext(
          ref,
          surface: surface,
          clientPageId: clientPageId,
          command: command,
        ),
  );
}

final circlesListDiscoveryFeedQueryProvider =
    Provider<CircleDiscoveryFeedQueryReader>(
      (ref) => _circlePort(
        ref,
        AppUiSurfaces.circlesList,
        CircleProductionAdapter.query,
      ),
    );

/// 圈子目录的 typed 查询能力；生产只装配 generated Remote reader。
final circlesListQueryProvider = Provider<CircleQueryReader>(
  (ref) => _circlePort(
    ref,
    AppUiSurfaces.circlesList,
    CircleProductionAdapter.query,
  ),
);

/// 圈子详情的 typed 查询能力；生产只装配 generated Remote reader。
final circleDetailQueryProvider = Provider<CircleQueryReader>(
  (ref) => _circlePort(
    ref,
    AppUiSurfaces.circleDetail,
    CircleProductionAdapter.query,
  ),
);

final circleDetailFeedQueryProvider = Provider<CircleFeedQueryReader>(
  (ref) => _circlePort(
    ref,
    AppUiSurfaces.circleDetail,
    CircleProductionAdapter.query,
  ),
);

final circleDetailPostPlacementCommandWriterProvider =
    Provider<CirclePostPlacementCommandWriter>((ref) {
      return CircleProductionComposition.generatedAdapter<
        CirclePostPlacementCommandWriter
      >(
        CircleProductionAdapter.postPlacement,
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId, idempotencyKey) =>
            _circleOperationInvocationContext(
              ref,
              surface: AppUiSurfaces.circleDetail,
              clientPageId: clientPageId,
              command: true,
              idempotencyKey: idempotencyKey,
            ),
      );
    });

/// 建圈动作归属圈子列表 surface（circlesList）。
final circlesListCircleLifecycleCommandWriterProvider =
    Provider<CircleLifecycleCommandWriter>(
      (ref) => _circlePort(
        ref,
        AppUiSurfaces.circlesList,
        CircleProductionAdapter.lifecycle,
      ),
    );

/// 圈主管理动作（更新/归档/板块配置）归属详情 surface（circleDetail）。
final circleDetailCircleLifecycleCommandWriterProvider =
    Provider<CircleLifecycleCommandWriter>(
      (ref) => _circlePort(
        ref,
        AppUiSurfaces.circleDetail,
        CircleProductionAdapter.lifecycle,
      ),
    );

final circleDetailCircleConfigurationCommandWriterProvider =
    Provider<CircleConfigurationCommandWriter>(
      (ref) => _circlePort(
        ref,
        AppUiSurfaces.circleDetail,
        CircleProductionAdapter.lifecycle,
      ),
    );

final circleDetailGroupQueryProvider = Provider<CircleGroupQueryReader>(
  (ref) => _circlePort(
    ref,
    AppUiSurfaces.circleDetail,
    CircleProductionAdapter.group,
  ),
);

final circleDetailFileCommandWriterProvider = Provider<CircleFileCommandWriter>(
  (ref) => _circlePort(
    ref,
    AppUiSurfaces.circleDetail,
    CircleProductionAdapter.file,
  ),
);

final circleDetailFileQueryProvider = Provider<CircleFileQueryReader>(
  (ref) => _circlePort(
    ref,
    AppUiSurfaces.circleDetail,
    CircleProductionAdapter.file,
  ),
);

final circleStatsGroupQueryProvider = Provider<CircleGroupQueryReader>(
  (ref) => _circlePort(
    ref,
    AppUiSurfaces.circleDetail,
    CircleProductionAdapter.group,
  ),
);

final globalSearchCircleGroupQueryProvider = Provider<CircleGroupQueryReader>(
  (ref) => _circlePort(
    ref,
    AppUiSurfaces.globalSearchSuggestions,
    CircleProductionAdapter.group,
  ),
);

final circleDetailMembershipCommandWriterProvider =
    Provider<CircleMembershipCommandWriter>(
      (ref) => _circlePort(
        ref,
        AppUiSurfaces.circleDetail,
        CircleProductionAdapter.membership,
      ),
    );

final circleDetailMembershipQueryProvider = Provider<CircleMembershipQuery>(
  (ref) => _circlePort(
    ref,
    AppUiSurfaces.circleDetail,
    CircleProductionAdapter.membership,
  ),
);

/// 圈子级审批（owner/admin）：命令与待审批队列按 circleDetail surface 装配。
final circleDetailMembershipModerationWriterProvider =
    Provider<CircleMembershipModerationWriter>(
      (ref) => _circlePort(
        ref,
        AppUiSurfaces.circleDetail,
        CircleProductionAdapter.membership,
      ),
    );

final circleDetailPendingMembershipQueryProvider =
    Provider<PendingCircleMembershipQuery>(
      (ref) => _circlePort(
        ref,
        AppUiSurfaces.circleDetail,
        CircleProductionAdapter.membership,
      ),
    );

final circleStatsMembershipQueryProvider = Provider<CircleMembershipQuery>(
  (ref) => _circlePort(
    ref,
    AppUiSurfaces.circleStats,
    CircleProductionAdapter.membership,
  ),
);

final homeFeedCircleMembershipQueryProvider = Provider<CircleMembershipQuery>(
  (ref) => _circlePort(
    ref,
    AppUiSurfaces.homeFeed,
    CircleProductionAdapter.membership,
  ),
);

final workBrowserCircleMembershipQueryProvider =
    Provider<CircleMembershipQuery>(
      (ref) => _circlePort(
        ref,
        AppUiSurfaces.workBrowser,
        CircleProductionAdapter.membership,
      ),
    );

final userProfileCircleMembershipQueryProvider =
    Provider<CircleMembershipQuery>(
      (ref) => _circlePort(
        ref,
        AppUiSurfaces.userProfile,
        CircleProductionAdapter.membership,
      ),
    );

final circleDetailBehaviorFactWriterProvider =
    Provider<CircleBehaviorFactWriter>((ref) {
      return CircleProductionComposition.generatedAdapter<
        CircleBehaviorFactWriter
      >(
        CircleProductionAdapter.behaviorFact,
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId) => _circleOperationInvocationContext(
          ref,
          surface: AppUiSurfaces.circleDetail,
          clientPageId: clientPageId,
          command: true,
        ),
      );
    });

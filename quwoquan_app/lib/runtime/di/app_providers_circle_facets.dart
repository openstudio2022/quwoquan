import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/observability/app_trace_context_store.dart';
import 'package:quwoquan_app/runtime/di/generated_operation_client_dependencies.dart';
import 'package:quwoquan_app/runtime/di/circle_dependencies.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_behavior_fact/application/public/circle_behavior_fact_appender.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_file/application/public/circle_file_ports.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_group/application/public/circle_group_ports.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_group_membership/application/public/circle_group_membership_access.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_group_membership/application/public/circle_group_membership_ports.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_membership/application/public/circle_membership_ports.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_post_placement/application/public/circle_post_placement_commands.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    hide ContentDiscoveryFeedQuery;
import 'package:quwoquan_app/runtime/di/app_providers_app_state.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';

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
    Provider<CirclePostPlacementCommands>((ref) {
      return CircleProductionComposition.generatedAdapter<
        CirclePostPlacementCommands
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

final circleDetailGroupQueryProvider = Provider<CircleGroupQueries>(
  (ref) => _circlePort(
    ref,
    AppUiSurfaces.circleDetail,
    CircleProductionAdapter.group,
  ),
);

/// 圈子详情默认公共群的 self membership facade；404 只在此处收敛为未加入。
final circleDetailGroupMembershipAccessProvider =
    Provider<CircleGroupMembershipAccess>((ref) {
      return CircleGroupMembershipAccess(
        commands: _circlePort<CircleGroupMembershipCommands>(
          ref,
          AppUiSurfaces.circleDetail,
          CircleProductionAdapter.groupMembership,
        ),
        queries: _circlePort<CircleGroupMembershipQueries>(
          ref,
          AppUiSurfaces.circleDetail,
          CircleProductionAdapter.groupMembership,
        ),
        isAbsent: (error) =>
            error is CloudException && error.type == CloudErrorType.notFound,
      );
    });

final circleDetailFileCommandWriterProvider = Provider<CircleFileWriter>(
  (ref) => _circlePort(
    ref,
    AppUiSurfaces.circleDetail,
    CircleProductionAdapter.file,
  ),
);

final circleDetailFileQueryProvider = Provider<CircleFileReader>(
  (ref) => _circlePort(
    ref,
    AppUiSurfaces.circleDetail,
    CircleProductionAdapter.file,
  ),
);

final circleStatsGroupQueryProvider = Provider<CircleGroupQueries>(
  (ref) => _circlePort(
    ref,
    AppUiSurfaces.circleDetail,
    CircleProductionAdapter.group,
  ),
);

final globalSearchCircleGroupQueryProvider = Provider<CircleGroupQueries>(
  (ref) => _circlePort(
    ref,
    AppUiSurfaces.globalSearchSuggestions,
    CircleProductionAdapter.group,
  ),
);

final circleDetailMembershipCommandWriterProvider =
    Provider<CircleMembershipCommands>(
      (ref) => _circlePort(
        ref,
        AppUiSurfaces.circleDetail,
        CircleProductionAdapter.membership,
      ),
    );

final circleDetailMembershipQueryProvider = Provider<CircleMembershipQueries>(
  (ref) => _circlePort(
    ref,
    AppUiSurfaces.circleDetail,
    CircleProductionAdapter.membership,
  ),
);

/// 圈子级审批（owner/admin）：命令与待审批队列按 circleDetail surface 装配。
final circleDetailMembershipModerationWriterProvider =
    Provider<ClientRequestBoundCircleMembershipModeration>(
      (ref) => CircleProductionComposition.generatedAdapter(
        CircleProductionAdapter.membership,
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext:
            (
              String clientPageId, {
              required bool command,
              String? idempotencyKey,
            }) => _circleOperationInvocationContext(
              ref,
              surface: AppUiSurfaces.circleDetail,
              clientPageId: clientPageId,
              command: command,
              idempotencyKey: idempotencyKey,
            ),
      ),
    );

final circleDetailPendingMembershipQueryProvider =
    Provider<PendingCircleMemberships>(
      (ref) => _circlePort(
        ref,
        AppUiSurfaces.circleDetail,
        CircleProductionAdapter.membership,
      ),
    );

final circleStatsMembershipQueryProvider = Provider<CircleMembershipQueries>(
  (ref) => _circlePort(
    ref,
    AppUiSurfaces.circleStats,
    CircleProductionAdapter.membership,
  ),
);

final homeFeedCircleMembershipQueryProvider = Provider<CircleMembershipQueries>(
  (ref) => _circlePort(
    ref,
    AppUiSurfaces.homeFeed,
    CircleProductionAdapter.membership,
  ),
);

final workBrowserCircleMembershipQueryProvider =
    Provider<CircleMembershipQueries>(
      (ref) => _circlePort(
        ref,
        AppUiSurfaces.workBrowser,
        CircleProductionAdapter.membership,
      ),
    );

final userProfileCircleMembershipQueryProvider =
    Provider<PersonaCircleMembershipQuery>(
      (ref) => _circlePort(
        ref,
        AppUiSurfaces.userProfile,
        CircleProductionAdapter.membership,
      ),
    );

final circleDetailBehaviorFactWriterProvider =
    Provider<CircleBehaviorFactAppender>((ref) {
      return CircleProductionComposition.generatedAdapter<
        CircleBehaviorFactAppender
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

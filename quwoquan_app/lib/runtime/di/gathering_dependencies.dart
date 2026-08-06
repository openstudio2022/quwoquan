import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart';
import 'package:quwoquan_app/runtime/di/app_providers_app_state.dart';
import 'package:quwoquan_app/runtime/di/circle_dependencies.dart';
import 'package:quwoquan_app/runtime/di/generated_operation_client_dependencies.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/circle/circle_request_page_ids.g.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_ports.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

/// Circle generated handoff 尚未覆盖目标 port 时的唯一 production 终态。
///
/// 调用方必须 override 对象级 typed port 做 local_contract；环境 App 不得回退到
/// legacy vertical source、测试专用数据源或本地合成结果。
T requireGatheringRemoteAdapter<T>(String portName) {
  throw RuntimeFailure(
    code: RuntimeFailureCodes.appSystemUnknownError,
    semanticReason: 'gathering_remote_adapter_unavailable',
    origin: RuntimeFailureOrigin.environment,
    kind: RuntimeFailureKind.unavailable,
    nature: RuntimeFailureNature.permanent,
    location: const RuntimeFailureLocation(
      businessObject: 'circle.gathering',
      functionModule: 'gathering_dependencies',
    ),
    context: RuntimeFailureContext(
      attributes: <RuntimeContextAttribute>[
        RuntimeContextAttribute(key: 'port', value: portName),
      ],
    ),
    recovery: const RuntimeRecoveryDirective(
      action: 'surface',
      disruptionLevel: 'fullPage',
    ),
  );
}

CloudOperationInvocationContext _gatheringInvocationContext(
  Ref ref, {
  required AppUiSurface surface,
  required String clientPageId,
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
    idempotencyKey: idempotencyKey,
  );
}

AppUiSurface _gatheringSurfaceForPageId(String clientPageId) {
  return switch (clientPageId) {
    CircleRequestPageIds.createGatheringDraft ||
    CircleRequestPageIds.publishGathering =>
      AppUiSurfaces.gatheringCreate,
    _ => AppUiSurfaces.gatheringDetail,
  };
}

T _gatheringPort<T>(Ref ref, CircleProductionAdapter adapter) {
  return CircleProductionComposition.generatedAdapter<T>(
    adapter,
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext:
        (String clientPageId, {String? idempotencyKey}) =>
            _gatheringInvocationContext(
              ref,
              surface: _gatheringSurfaceForPageId(clientPageId),
              clientPageId: clientPageId,
              idempotencyKey: idempotencyKey,
            ),
  );
}

/// Production 装配 generated Gathering command adapter。
final gatheringCommandWriterProvider = Provider<GatheringCommandWriter>(
  (ref) => _gatheringPort(ref, CircleProductionAdapter.gathering),
);

/// Production 装配 generated Gathering query adapter。
final gatheringQueryReaderProvider = Provider<GatheringQueryReader>(
  (ref) => _gatheringPort(ref, CircleProductionAdapter.gathering),
);

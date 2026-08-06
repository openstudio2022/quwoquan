import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart';
import 'package:quwoquan_app/runtime/di/app_providers_app_state.dart';
import 'package:quwoquan_app/runtime/di/chat_dependencies.dart';
import 'package:quwoquan_app/runtime/di/circle_dependencies.dart';
import 'package:quwoquan_app/runtime/di/generated_operation_client_dependencies.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/gathering_board_composer.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/gathering_board_ports.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

CloudOperationInvocationContext _chatBoardInvocationContext(
  Ref ref, {
  required AppUiSurface surface,
  required String clientPageId,
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
  );
}

CloudOperationInvocationContext _circleBoardInvocationContext(
  Ref ref,
  String clientPageId,
) {
  return _chatBoardInvocationContext(
    ref,
    surface: AppUiSurfaces.gatheringBoard,
    clientPageId: clientPageId,
  );
}

/// Chat generated Remote 看板 reader。
final gatheringBoardChatReaderProvider = Provider<GatheringBoardChatReader>(
  (ref) => ChatProductionComposition.gatheringBoardChatReader(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (surface, clientPageId, {idempotencyKey}) =>
        _chatBoardInvocationContext(
          ref,
          surface: surface,
          clientPageId: clientPageId,
        ),
  ),
);

/// Circle generated Remote 看板 reader。
final gatheringBoardCircleReaderProvider = Provider<GatheringBoardCircleReader>(
  (ref) => CircleProductionComposition.generatedAdapter<GatheringBoardCircleReader>(
    CircleProductionAdapter.gatheringBoardCircle,
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId) =>
        _circleBoardInvocationContext(ref, clientPageId),
  ),
);

/// 唯一 Board composition：Chat 先解析 canonical gatheringId，再读取 Circle。
final gatheringBoardQueryProvider = Provider<GatheringBoardQuery>(
  (ref) => GatheringBoardComposer(
    chatReader: ref.watch(gatheringBoardChatReaderProvider),
    circleReader: ref.watch(gatheringBoardCircleReaderProvider),
  ),
);

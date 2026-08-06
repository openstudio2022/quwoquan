import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/services/ops/event_record_batch_writer.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/di/generated_operation_client_dependencies.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final opsEventRecordBatchWriterProvider = Provider<OpsEventRecordBatchWriter>((
  ref,
) {
  return RemoteOpsEventRecordBatchWriter(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (String clientPageId, {required String idempotencyKey}) {
      final session = ref.read(authSessionControllerProvider);
      final accountId = session.isAuthenticated ? session.ownerId.trim() : '';
      final personaId = session.isAuthenticated
          ? session.activePersonaId.trim()
          : '';
      return CloudOperationInvocationContext(
        surfaceId: AppUiSurfaces.appShell.id,
        clientPageId: clientPageId,
        routeId: AppUiSurfaces.appShell.routeId,
        idempotencyKey: idempotencyKey,
        actor: CloudOperationActorContext(
          accountId: accountId.isEmpty ? null : accountId,
          personaId: personaId.isEmpty ? null : personaId,
        ),
      );
    },
  );
});

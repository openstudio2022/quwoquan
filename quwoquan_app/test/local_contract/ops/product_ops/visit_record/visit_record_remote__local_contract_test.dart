// spec_ref: specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/event-schema-governance/spec.md#gwt-001

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/services/ops/ops_visit_append_writer.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test(
    'RecordVisit uses the generated owner, appShell reachability, and header identity',
    () async {
      final executor = _VisitExecutor();
      final writer = RemoteOpsVisitAppendWriter(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: (clientPageId, {required idempotencyKey}) =>
            CloudOperationInvocationContext(
              surfaceId: AppUiSurfaces.appShell.id,
              routeId: AppUiSurfaces.appShell.routeId,
              clientPageId: clientPageId,
              idempotencyKey: idempotencyKey,
              actor: const CloudOperationActorContext(
                accountId: 'account-1',
                personaId: 'persona-1',
              ),
            ),
      );

      await writer.recordVisit(
        const OpsVisitReportInput(
          idempotencyKey: 'visit-intent-1',
          targetType: 'page',
          targetKey: 'page_discovery_recommend',
        ),
      );

      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.opsVisitRecordRecordVisit,
      );
      expect(executor.context?.surfaceId, AppUiSurfaces.appShell.id);
      expect(executor.context?.idempotencyKey, 'visit-intent-1');
      expect(executor.body, <String, Object?>{
        'targetType': 'page',
        'targetKey': 'page_discovery_recommend',
      });
      expect(executor.body, isNot(contains('userId')));
      expect(executor.body, isNot(contains('occurredAt')));
      expect(executor.body, isNot(contains('idempotencyKey')));
    },
  );

  test(
    'local retry storage codec rejects Cloud wire aliases and unknown fields',
    () {
      expect(
        () => OpsVisitReportInput.fromStorageJson(<String, dynamic>{
          'idempotencyKey': 'visit-intent-1',
          'targetType': 'page',
          'targetKey': 'page_home',
          'userId': 'must-not-be-accepted',
        }),
        throwsFormatException,
      );
    },
  );
}

final class _VisitExecutor implements CloudOperationExecutor {
  CloudOperationContract? operation;
  CloudOperationInvocationContext? context;
  Object? body;

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    this.operation = operation;
    this.context = context;
    body = requestEncoder().body;
    return responseDecoder(<String, Object?>{
      'targetType': 'page',
      'targetKey': 'page_discovery_recommend',
      'visitCount': 1,
      'occurredAt': '2026-08-04T00:00:00Z',
      'replayed': false,
    });
  }
}

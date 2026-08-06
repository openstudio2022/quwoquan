// spec_ref: specs/feature-tree/shared-homepage-network/homepage-claim-maintain-and-offline/homepage-offline-report-and-history-retention/spec.md#gwt-001
// readiness_case: homepage_status_report_create_homepage_status_report_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_status_report/adapters/homepage_status_report_remote.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_status_report/application/public/homepage_status_report_command_writer.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/entity/entity_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('状态上报 Remote 映射本地 Draft 并执行唯一 generated operation', () async {
    final executor = _RecordingExecutor(response: _statusReportResponse());
    final writer = RemoteHomepageStatusReportWriter(
      client: GeneratedCloudOperationClient(executor),
      invocationContext: _context,
    );

    final result = await writer.createStatusReport(
      homepageId: 'homepage-1',
      draft: HomepageStatusReportDraft(
        reason: 'incorrect_info',
        description: '地址已经变更',
        evidenceUrls: <String>['https://media.example/evidence'],
      ),
    );

    expect(
      executor.operation?.canonicalOperationId,
      AppCloudOperationIds.entityHomepageStatusReportCreateHomepageStatusReport,
    );
    expect(executor.pathParameters, <String, String>{
      'homepageId': 'homepage-1',
    });
    expect(executor.body, <String, Object?>{
      'reason': 'incorrect_info',
      'description': '地址已经变更',
      'evidenceUrls': <String>['https://media.example/evidence'],
    });
    expect(
      executor.context?.clientPageId,
      EntityRequestPageIds.createHomepageStatusReport,
    );
    expect(executor.context?.surfaceId, AppUiSurfaces.homepageStatusReport.id);
    expect(
      executor.context?.routeId,
      AppUiSurfaces.homepageStatusReport.routeId,
    );
    expect(executor.context?.idempotencyKey, 'status-report-intent-1');
    expect(result.reportId, 'report-1');
    expect(result.reason, HomepageStatusReportReason.incorrectInfo);
    expect(result.status, HomepageStatusReportStatus.pendingReview);
  });

  test('状态上报 Remote 对非 canonical 结果 fail closed', () async {
    final writer = RemoteHomepageStatusReportWriter(
      client: GeneratedCloudOperationClient(
        _RecordingExecutor(response: <String, Object?>{'id': 'report-1'}),
      ),
      invocationContext: _context,
    );

    await expectLater(
      writer.createStatusReport(
        homepageId: 'homepage-1',
        draft: HomepageStatusReportDraft(reason: 'offline'),
      ),
      throwsFormatException,
    );
  });
}

CloudOperationInvocationContext _context(
  String clientPageId,
  AppUiSurface surface,
) => CloudOperationInvocationContext(
  surfaceId: surface.id,
  routeId: surface.routeId,
  clientPageId: clientPageId,
  actor: const CloudOperationActorContext(
    accountId: 'account-1',
    personaId: 'persona-1',
  ),
  idempotencyKey: 'status-report-intent-1',
);

Map<String, Object?> _statusReportResponse() => <String, Object?>{
  'reportId': 'report-1',
  'homepageId': 'homepage-1',
  'reporterPersonaId': 'persona-1',
  'reason': 'incorrect_info',
  'status': 'pending_review',
  'description': '地址已经变更',
  'evidenceUrls': <String>['https://media.example/evidence'],
  'createdAt': '2026-08-05T00:00:00Z',
};

final class _RecordingExecutor implements CloudOperationExecutor {
  _RecordingExecutor({required this.response});

  final Object? response;
  CloudOperationContract? operation;
  CloudOperationInvocationContext? context;
  Map<String, String> pathParameters = const <String, String>{};
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
    final payload = requestEncoder();
    pathParameters = payload.pathParameters;
    body = payload.body;
    return responseDecoder(response);
  }
}

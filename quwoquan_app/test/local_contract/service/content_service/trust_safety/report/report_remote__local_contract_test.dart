// spec_ref: specs/feature-tree/discovery-content/content-display-consistency/content-action-intent-contract/spec.md#gwt-001
// readiness_case: report_create_report_app_local
// readiness_case: report_list_my_reports_app_local
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/trust_safety/report/adapters/report_command_remote.dart';
import 'package:quwoquan_app/service/content_service/trust_safety/report/adapters/report_query_remote.dart';
import 'package:quwoquan_app/service/content_service/trust_safety/report/application/public/content_report_ports.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  group('ContentReport remote ports', () {
    test(
      'writer sends the canonical typed command through generated client',
      () async {
        final executor = _RecordingExecutor(
          response: <String, Object?>{
            'id': 'report-1',
            'version': 1,
            'status': 'pending',
            'replayed': false,
          },
        );
        final ContentReportWriter writer = RemoteContentReportAdapter(
          client: GeneratedCloudOperationClient(executor),
          invocationContext: _invocationContext,
        );

        await writer.createReport(
          CreateContentReportCommand(
            targetId: 'post-1',
            targetType: ReportTargetType.post,
            reason: ReportReason.spam,
          ),
        );

        expect(
          executor.operation?.canonicalOperationId,
          AppCloudOperationIds.contentReportCreateReport,
        );
        expect(executor.body, <String, Object?>{
          'targetId': 'post-1',
          'targetType': 'post',
          'reason': 'spam',
        });
        expect(executor.contexts.single.clientPageId, isNotEmpty);
      },
    );

    test('reader returns the canonical private report page slice', () async {
      final executor = _RecordingExecutor(
        response: <String, Object?>{
          'items': <Object?>[
            <String, Object?>{
              'id': 'report-1',
              'targetType': 'post',
              'targetId': 'post-1',
              'reason': 'spam',
              'status': 'pending',
              'createdAt': '2026-07-20T00:00:00Z',
              'updatedAt': '2026-07-20T00:00:00Z',
            },
          ],
        },
      );
      final ContentMyReportsReader reader = RemoteContentReportQueryAdapter(
        client: GeneratedCloudOperationClient(executor),
        invocationContext: _invocationContext,
      );

      final page = await reader.listMyReports(
        ContentMyReportsQuery(limit: 10),
      );

      expect(
        executor.operation?.canonicalOperationId,
        AppCloudOperationIds.contentReportListMyReports,
      );
      expect(executor.queryParameters, <String, String>{'limit': '10'});
      expect(page.items.single.status, ReportStatus.pending);
      expect(executor.contexts.single.clientPageId, isNotEmpty);
    });
  });
}

CloudOperationInvocationContext _invocationContext(String clientPageId) {
  return CloudOperationInvocationContext(
    surfaceId: 'report-test',
    clientPageId: clientPageId,
    actor: const CloudOperationActorContext(personaId: 'persona-1'),
  );
}

final class _RecordingExecutor implements CloudOperationExecutor {
  _RecordingExecutor({this.response});

  final Object? response;
  CloudOperationContract? operation;
  final List<CloudOperationInvocationContext> contexts =
      <CloudOperationInvocationContext>[];
  Map<String, String> queryParameters = const <String, String>{};
  Object? body;

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    this.operation = operation;
    contexts.add(context);
    final payload = requestEncoder();
    queryParameters = payload.queryParameters;
    body = payload.body;
    return responseDecoder(response);
  }
}

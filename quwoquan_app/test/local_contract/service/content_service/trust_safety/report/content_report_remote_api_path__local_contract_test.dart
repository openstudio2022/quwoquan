/// 对象级端云契约：Remote adapter 的 HTTP path 与 generated metadata 对齐。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/service/content_service/trust_safety/report/adapters/report_command_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../../support/runtime/remote_api_path_test_harness.dart';

http.Response _responseFor(http.Request request) {
  if (request.method == 'POST' &&
      request.url.path ==
          canonicalRemoteApiPath(
            AppCloudOperationIds.contentReportCreateReport,
          )) {
    return remoteApiPathJsonResponse({
      'id': 'report-path-contract-1',
      'version': 1,
      'status': 'pending',
      'replayed': false,
    });
  }
  return remoteApiPathJsonResponse('{}');
}

void main() {
  group('RemoteContentReportAdapter — generated operation 路径对齐', () {
    late List<CapturedRemoteApiPathRequest> log;
    late RemoteContentReportAdapter adapter;

    setUp(() {
      log = [];
      final client = buildRemoteApiPathOperationClient(
        log,
        responseFor: _responseFor,
      );
      adapter = RemoteContentReportAdapter(
        client: client,
        invocationContext: (clientPageId) {
          return CloudOperationInvocationContext(
            surfaceId: AppUiSurfaces.homeFeed.id,
            routeId: AppUiSurfaces.homeFeed.routeId,
            clientPageId: clientPageId,
            idempotencyKey: 'report-path-contract-idempotency-key',
            actor: const CloudOperationActorContext(personaId: 'persona-1'),
          );
        },
      );
    });

    test('createReport → POST /content/reports', () async {
      await adapter.createReport(
        CreateContentReportCommand(
          targetId: 'p1',
          targetType: ReportTargetType.post,
          reason: ReportReason.spam,
        ),
      );
      expect(log.last.method, 'POST');
      expect(
        log.last.path,
        canonicalRemoteApiPath(AppCloudOperationIds.contentReportCreateReport),
      );
      expect(
        log.last.headers['Idempotency-Key'],
        'report-path-contract-idempotency-key',
      );
      expectRemoteApiPathHeaders(
        log.last.headers,
        clientPageId: ContentRequestPageIds.createReport,
        surfaceId: AppUiSurfaces.homeFeed.id,
        operationId: AppCloudOperationIds.contentReportCreateReport,
      );
    });
  });
}

import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_status_report/application/public/homepage_status_report_command_writer.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_status_report/application/public/homepage_status_report_query_reader.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/entity/entity_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef HomepageStatusReportInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId,
      AppUiSurface surface, {
      String? idempotencyKey,
    });

/// HomepageStatusReport 的 production generated-client adapter。
final class RemoteHomepageStatusReportWriter
    implements HomepageStatusReportCommandWriter {
  const RemoteHomepageStatusReportWriter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final HomepageStatusReportInvocationContextFactory invocationContext;

  @override
  Future<HomepageStatusReportView> createStatusReport({
    required String homepageId,
    required HomepageStatusReportDraft draft,
    String? clientRequestId,
  }) => client.entityHomepageStatusReportCreateHomepageStatusReport(
    CreateHomepageStatusReportCommand(
      homepageId: homepageId,
      reason: draft.reason,
      description: draft.description,
      evidenceUrls: draft.evidenceUrls,
    ),
    context: invocationContext(
      EntityRequestPageIds.createHomepageStatusReport,
      AppUiSurfaces.homepageStatusReport,
      idempotencyKey: clientRequestId,
    ),
  );
}

/// HomepageStatusReport 本人待审记录的 production generated-client adapter。
final class RemoteHomepageStatusReportReader
    implements HomepageStatusReportQueryReader {
  const RemoteHomepageStatusReportReader({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final HomepageStatusReportInvocationContextFactory invocationContext;

  @override
  Future<HomepageStatusReportView> getMyPendingStatusReport({
    required String homepageId,
    required String reason,
  }) => client.entityHomepageStatusReportGetMyPendingHomepageStatusReport(
    GetMyPendingHomepageStatusReportQuery(
      homepageId: homepageId,
      reason: reason,
    ),
    context: invocationContext(
      EntityRequestPageIds.getMyPendingHomepageStatusReport,
      AppUiSurfaces.homepageStatusReport,
    ),
  );
}

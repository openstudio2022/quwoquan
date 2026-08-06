import 'package:quwoquan_app/service/content_service/trust_safety/report/application/public/content_report_ports.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Alpha/test 举报 adapter：本地记录，不发 HTTP。
final class InMemoryContentReportAdapter implements ContentReportWriter {
  final List<CreateContentReportCommand> submitted =
      <CreateContentReportCommand>[];

  @override
  Future<void> createReport(CreateContentReportCommand command) async {
    submitted.add(command);
  }
}

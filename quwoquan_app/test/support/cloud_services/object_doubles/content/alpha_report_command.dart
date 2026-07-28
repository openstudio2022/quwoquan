import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Alpha/test 举报 adapter：本地记录，不发 HTTP。
final class AlphaContentReportAdapter implements ContentReportCommandWriter {
  final List<CreateContentReportCommand> submitted =
      <CreateContentReportCommand>[];

  @override
  Future<void> createReport(CreateContentReportCommand command) async {
    submitted.add(command);
  }
}

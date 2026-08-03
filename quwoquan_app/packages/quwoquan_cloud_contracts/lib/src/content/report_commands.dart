import 'content_operation_contracts.g.dart';

abstract interface class ContentReportCommandWriter {
  Future<void> createReport(CreateContentReportCommand command);
}

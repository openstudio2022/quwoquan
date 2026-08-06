import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show ContentMyReportsQuery, CreateContentReportCommand, MyReportPageSlice;

abstract interface class ContentReportWriter {
  Future<void> createReport(CreateContentReportCommand command);
}

abstract interface class ContentMyReportsReader {
  Future<MyReportPageSlice> listMyReports(ContentMyReportsQuery query);
}
